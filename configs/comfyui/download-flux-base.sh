#!/bin/bash
# Download Flux base models needed for ComfyUI (VAE + CLIP encoders)
set -e
LOG=/opt/models/comfyui-install.log
exec >> "$LOG" 2>&1

source /opt/vllm-env/comfyui-env/bin/activate

echo "=== $(date) — Downloading Flux base models ==="

mkdir -p /opt/models/comfyui-vae
mkdir -p /opt/models/comfyui-clip

# VAE: ae.safetensors (~335 MB)
echo "[VAE] Downloading ae.safetensors ..."
/opt/vllm-env/comfyui-env/bin/python3 -c "
from huggingface_hub import hf_hub_download
hf_hub_download(
    repo_id='black-forest-labs/FLUX.1-dev',
    filename='ae.safetensors',
    local_dir='/opt/models/comfyui-vae',
)
print('VAE downloaded')
" 2>/dev/null || \
/opt/vllm-env/comfyui-env/bin/python3 -c "
from huggingface_hub import hf_hub_download
# Fallback: use FLUX.1-schnell VAE (same ae.safetensors)
hf_hub_download(
    repo_id='black-forest-labs/FLUX.1-schnell',
    filename='ae.safetensors',
    local_dir='/opt/models/comfyui-vae',
)
print('VAE downloaded from schnell')
"

# CLIP: clip_l.safetensors (~246 MB)
echo "[CLIP] Downloading clip_l.safetensors ..."
/opt/vllm-env/comfyui-env/bin/python3 -c "
from huggingface_hub import hf_hub_download
hf_hub_download(
    repo_id='comfyanonymous/flux_text_encoders',
    filename='clip_l.safetensors',
    local_dir='/opt/models/comfyui-clip',
)
print('clip_l downloaded')
"

# T5: t5xxl_fp8_e4m3fn.safetensors (~4.9 GB, FP8 = uses half the VRAM of FP16)
echo "[T5] Downloading t5xxl_fp8_e4m3fn.safetensors ..."
/opt/vllm-env/comfyui-env/bin/python3 -c "
from huggingface_hub import hf_hub_download
hf_hub_download(
    repo_id='comfyanonymous/flux_text_encoders',
    filename='t5xxl_fp8_e4m3fn.safetensors',
    local_dir='/opt/models/comfyui-clip',
)
print('T5 FP8 downloaded')
"

echo "=== Base models DONE $(date) ==="
