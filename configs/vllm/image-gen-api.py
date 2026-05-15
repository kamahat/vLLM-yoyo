#!/usr/bin/env python3
"""
Image generation API — AUTOMATIC1111-compatible
Sert NSFW-gen-v2 (SDXL) sur le port 8003.
Open WebUI → Settings → Images → A1111 backend → http://192.168.20.160:8003
"""
import base64, io, os, logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
import uvicorn

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("image-gen")

MODEL_DIR = "/opt/models/nsfw-gen-v2"
pipe = None

def load_pipeline():
    global pipe
    if pipe is not None:
        return
    log.info("Chargement du pipeline SDXL...")
    import torch
    from diffusers import StableDiffusionXLPipeline
    pipe = StableDiffusionXLPipeline.from_pretrained(
        MODEL_DIR,
        torch_dtype=torch.float16,
        use_safetensors=True,
        local_files_only=True,
    ).to("cuda")
    pipe.enable_attention_slicing()
    log.info("Pipeline prêt.")

app = FastAPI(title="Image Gen API (NSFW-gen-v2 SDXL)")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class Txt2ImgRequest(BaseModel):
    prompt: str = ""
    negative_prompt: str = ""
    steps: int = Field(default=25, ge=1, le=80)
    width: int = Field(default=1024, ge=64, le=2048)
    height: int = Field(default=1024, ge=64, le=2048)
    cfg_scale: float = Field(default=7.0, ge=1.0, le=30.0)
    seed: int = -1
    n_iter: int = 1
    batch_size: int = 1

@app.get("/health")
def health():
    return {"status": "ok", "model": "NSFW-gen-v2 (SDXL)", "loaded": pipe is not None}

@app.get("/sdapi/v1/sd-models")
def sd_models():
    return [{"title": "nsfw-gen-v2", "model_name": "nsfw-gen-v2", "filename": MODEL_DIR}]

@app.get("/sdapi/v1/options")
def options():
    return {"sd_model_checkpoint": "nsfw-gen-v2", "sd_backend": "diffusers"}

@app.post("/sdapi/v1/txt2img")
def txt2img(req: Txt2ImgRequest):
    import torch
    load_pipeline()
    gen = None
    if req.seed >= 0:
        gen = torch.Generator("cuda").manual_seed(req.seed)
    log.info(f"Génération: {req.prompt[:80]}...")
    images = []
    for _ in range(max(1, req.n_iter)):
        result = pipe(
            prompt=req.prompt,
            negative_prompt=req.negative_prompt or None,
            num_inference_steps=req.steps,
            guidance_scale=req.cfg_scale,
            width=req.width,
            height=req.height,
            num_images_per_prompt=max(1, req.batch_size),
            generator=gen,
        )
        for img in result.images:
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            images.append(base64.b64encode(buf.getvalue()).decode())
    log.info(f"{len(images)} image(s) générée(s)")
    return {"images": images, "parameters": req.dict(), "info": ""}

@app.get("/sdapi/v1/samplers")
def samplers():
    return [{"name": "DPM++ 2M", "aliases": [], "options": {}}]

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8003, log_level="info")
