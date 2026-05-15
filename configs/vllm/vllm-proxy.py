#!/usr/bin/env python3
"""
vLLM Model Proxy — port 8001

Expose tous les modeles texte dans /v1/models et declenche automatiquement
le switch quand Open WebUI selectionne un modele different de l'actif.

Open WebUI OPENAI_API_BASE_URL doit pointer sur http://192.168.20.160:8001/v1
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
SWITCH_TIMEOUT = 300   # secondes max pour attendre le chargement

# Catalogue complet des modeles texte (dans l'ordre du sélecteur)
ALL_MODELS = [
    {"id": "qwen2.5-coder-7b", "label": "Qwen2.5-Coder-7B (AWQ)"},
    {"id": "unfilteredai-1b",  "label": "UnfilteredAI-1B"},
    {"id": "badmistral-1.5b",  "label": "BADMISTRAL-1.5B"},
]

# Mapping model_id -> cle vllm-switch
MODEL_KEYS = {
    "qwen2.5-coder-7b": "qwen",
    "unfilteredai-1b":  "unfilteredai",
    "badmistral-1.5b":  "badmistral",
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


async def ensure_model(model_id: str) -> bool:
    """Si le modele n'est pas actif, declenche le switch et attend qu'il soit pret."""
    key = MODEL_KEYS.get(model_id)
    if not key:
        return False

    status = await get_status()
    if status.get("active") == model_id and status.get("ready"):
        return True

    log.info(f"Switch -> {model_id} (actif: {status.get('active')})")
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            await c.get(f"{SWITCHER_URL}/switch/{key}")
    except Exception as e:
        log.warning(f"Switch trigger failed: {e}")

    deadline = time.monotonic() + SWITCH_TIMEOUT
    while time.monotonic() < deadline:
        await asyncio.sleep(4)
        s = await get_status()
        if s.get("active") == model_id and s.get("ready"):
            log.info(f"Modele {model_id} pret")
            return True
        log.debug(f"En attente... actif={s.get('active')} ready={s.get('ready')}")

    log.error(f"Timeout ({SWITCH_TIMEOUT}s) en attendant {model_id}")
    return False


# ── Endpoints speciaux ────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "proxy": "vllm-proxy"}


@app.get("/v1/models")
async def list_models():
    """Retourne toujours la liste complete, quel que soit le modele actif."""
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


async def _forward_stream(url: str, body: dict):
    """Stream SSE depuis vLLM vers le client."""
    async def generate():
        async with httpx.AsyncClient(timeout=300) as c:
            async with c.stream("POST", url, json=body,
                                headers={"Content-Type": "application/json"}) as r:
                async for chunk in r.aiter_bytes():
                    yield chunk
    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    model_id = body.get("model", "qwen2.5-coder-7b")

    if model_id not in MODEL_KEYS:
        return JSONResponse({"error": {"message": f"Modele inconnu: {model_id}",
                                       "type": "invalid_request_error"}}, status_code=400)

    ready = await ensure_model(model_id)
    if not ready:
        return JSONResponse({"error": {"message": f"Impossible de charger {model_id}",
                                       "type": "server_error"}}, status_code=503)

    if body.get("stream"):
        return await _forward_stream(f"{VLLM_URL}/v1/chat/completions", body)

    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{VLLM_URL}/v1/chat/completions", json=body)
        return Response(content=r.content, status_code=r.status_code,
                        media_type="application/json")


@app.post("/v1/completions")
async def completions(request: Request):
    body = await request.json()
    model_id = body.get("model", "qwen2.5-coder-7b")

    ready = await ensure_model(model_id)
    if not ready:
        return JSONResponse({"error": {"message": f"Impossible de charger {model_id}"}},
                            status_code=503)

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