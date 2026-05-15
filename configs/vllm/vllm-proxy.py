#!/usr/bin/env python3
"""
vLLM Model Proxy — port 8001

Expose tous les modeles texte dans /v1/models et declenche automatiquement
le switch quand Open WebUI selectionne un modele different de l'actif.

Cle : pendant le switch, des heartbeats SSE sont envoyes toutes les 2s pour
eviter que Open WebUI ferme la connexion (timeout idle).

Open WebUI OPENAI_API_BASE_URL = http://brain.zalin.home:8001/v1
"""
import asyncio, time, json, logging
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("vllm-proxy")

VLLM_URL     = "http://localhost:8000"
SWITCHER_URL = "http://localhost:8002"
SWITCH_TIMEOUT = 300   # secondes max pour le chargement

ALL_MODELS = [
    {"id": "qwen2.5-coder-7b", "label": "Qwen2.5-Coder-7B (AWQ)"},
    {"id": "unfilteredai-1b",  "label": "UnfilteredAI-1B"},
    {"id": "dan-qwen3.5-4b",  "label": "Dan-Qwen3.5-4B"},
]

MODEL_KEYS = {
    "qwen2.5-coder-7b": "qwen",
    "unfilteredai-1b":  "unfilteredai",
    "dan-qwen3.5-4b":  "dan-qwen",
}

app = FastAPI(title="vLLM Proxy")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])


async def get_status() -> dict:
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get(f"{SWITCHER_URL}/status")
            return r.json()
    except Exception:
        return {"active": None, "ready": False}


async def trigger_switch(key: str):
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            await c.get(f"{SWITCHER_URL}/switch/{key}")
    except Exception as e:
        log.warning(f"Switch trigger failed: {e}")


async def wait_for_model(model_id: str, timeout: int = SWITCH_TIMEOUT) -> bool:
    """Poll le switcher jusqu'a ce que le modele soit pret."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        await asyncio.sleep(3)
        s = await get_status()
        if s.get("active") == model_id and s.get("ready"):
            log.info(f"Modele {model_id} pret")
            return True
    log.error(f"Timeout ({timeout}s) en attendant {model_id}")
    return False


async def ensure_model_streaming(model_id: str):
    """
    Generateur : envoie des heartbeats SSE pendant le switch,
    puis yield None pour signaler que le modele est pret (ou False si echec).
    """
    key = MODEL_KEYS.get(model_id)
    if not key:
        yield False
        return

    # Verifier si deja actif
    status = await get_status()
    if status.get("active") == model_id and status.get("ready"):
        yield True
        return

    log.info(f"Switch -> {model_id} (actif: {status.get('active')})")
    await trigger_switch(key)

    # Attente avec heartbeats toutes les 2s
    deadline = time.monotonic() + SWITCH_TIMEOUT
    while time.monotonic() < deadline:
        await asyncio.sleep(2)
        s = await get_status()
        if s.get("active") == model_id and s.get("ready"):
            log.info(f"Modele {model_id} pret")
            yield True
            return
        # Heartbeat SSE : commentaire vide (invisible cote client)
        yield b": heartbeat\n\n"

    log.error(f"Timeout en attendant {model_id}")
    yield False


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "proxy": "vllm-proxy"}


@app.get("/v1/models")
async def list_models():
    ts = int(time.time())
    return {
        "object": "list",
        "data": [
            {
                "id": m["id"],
                "object": "model",
                "created": ts,
                "owned_by": "vllm",
                "root": m["id"],
                "parent": None,
                "max_model_len": None,
                "permission": [{
                    "id": f"modelperm-{m['id']}",
                    "object": "model_permission",
                    "created": ts,
                    "allow_create_engine": False,
                    "allow_sampling": True,
                    "allow_logprobs": True,
                    "allow_view": True,
                    "allow_fine_tuning": False,
                    "organization": "*",
                    "group": None,
                    "is_blocking": False,
                }],
            }
            for m in ALL_MODELS
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    model_id = body.get("model", "qwen2.5-coder-7b")

    if model_id not in MODEL_KEYS:
        return JSONResponse(
            {"error": {"message": f"Modele inconnu: {model_id}", "type": "invalid_request_error"}},
            status_code=400)

    # Toujours repondre en streaming pour maintenir la connexion vivante
    # (meme si le client n'a pas demande stream=True)
    client_wants_stream = body.get("stream", False)

    async def generate():
        # Phase 1 : switch avec heartbeats si necessaire
        ready = False
        async for item in ensure_model_streaming(model_id):
            if isinstance(item, bytes):
                yield item          # heartbeat SSE
            else:
                ready = item        # True ou False
                break

        if not ready:
            err = json.dumps({"error": {"message": f"Impossible de charger {model_id}",
                                        "type": "server_error"}})
            yield f"data: {err}\n\ndata: [DONE]\n\n".encode()
            return

        # Phase 2 : forwarder vers vLLM
        # Forcer stream=True cote vLLM pour des raisons de perf
        forward_body = {**body, "stream": True}
        async with httpx.AsyncClient(timeout=300) as c:
            async with c.stream("POST", f"{VLLM_URL}/v1/chat/completions",
                                json=forward_body,
                                headers={"Content-Type": "application/json"}) as r:
                if client_wants_stream:
                    # Le client veut du SSE : on pipe directement
                    async for chunk in r.aiter_bytes():
                        yield chunk
                else:
                    # Le client veut du JSON : on accumule les chunks SSE
                    # et on reconstitue la reponse complete
                    full_content = ""
                    finish_reason = "stop"
                    completion_id = None
                    created = int(time.time())
                    async for line in r.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            if not completion_id:
                                completion_id = chunk.get("id")
                            delta = chunk["choices"][0].get("delta", {})
                            full_content += delta.get("content", "")
                            fr = chunk["choices"][0].get("finish_reason")
                            if fr:
                                finish_reason = fr
                        except Exception:
                            pass
                    resp = {
                        "id": completion_id or "chatcmpl-proxy",
                        "object": "chat.completion",
                        "created": created,
                        "model": model_id,
                        "choices": [{
                            "index": 0,
                            "message": {"role": "assistant", "content": full_content},
                            "finish_reason": finish_reason
                        }],
                        "usage": {}
                    }
                    # Pour les reponses non-streaming on ne peut pas utiliser
                    # StreamingResponse — on yielde le JSON en une fois
                    yield json.dumps(resp).encode()

    if client_wants_stream:
        return StreamingResponse(generate(), media_type="text/event-stream")
    else:
        # Non-streaming : on doit quand meme utiliser le streaming interne
        # mais on retourne une Response JSON classique
        # On utilise un timeout long et on accumule
        async def collect():
            chunks = []
            async for c in generate():
                chunks.append(c)
            return b"".join(chunks)

        result = await asyncio.wait_for(collect(), timeout=SWITCH_TIMEOUT + 60)
        # Le dernier chunk est le JSON final
        return Response(content=result, media_type="application/json")


@app.post("/v1/completions")
async def completions(request: Request):
    body = await request.json()
    model_id = body.get("model", "qwen2.5-coder-7b")

    if model_id not in MODEL_KEYS:
        return JSONResponse({"error": {"message": f"Modele inconnu: {model_id}"}}, status_code=400)

    # Switch si necessaire (avec timeout long, pas de streaming ici)
    key = MODEL_KEYS[model_id]
    status = await get_status()
    if not (status.get("active") == model_id and status.get("ready")):
        await trigger_switch(key)
        await wait_for_model(model_id)

    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{VLLM_URL}/v1/completions", json=body)
        return Response(content=r.content, status_code=r.status_code,
                        media_type="application/json")


# ── Proxy transparent pour tout le reste ────────────────────────────────────

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy_all(path: str, request: Request):
    url = f"{VLLM_URL}/{path}"
    body = await request.body()
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ("host", "content-length")}
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.request(request.method, url, content=body, headers=headers)
    return Response(content=r.content, status_code=r.status_code,
                    media_type=r.headers.get("content-type", "application/json"))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")