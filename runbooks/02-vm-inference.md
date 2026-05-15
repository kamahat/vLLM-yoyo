# Runbook 02 — VM-100 : Inference (vLLM + multi-modeles)

> **Statut : OK** — Switcher API actif sur http://brain.zalin.home:8002
> **Modele par defaut** : Qwen2.5-Coder-7B-Instruct-AWQ (AWQ_Marlin INT4)

> WARNING **Blackwell (compute 12.0 / RTX 5070)** : FP8 dynamique produit des sorties incorrectes.
> Solution : modeles AWQ pre-quantifies (INT4) ou float16 (stables).

## Specifications

| Parametre | Valeur |
|-----------|--------|
| VMID | 100 |
| IP | brain.zalin.home |
| RAM | 48 Go |
| CPU | 8 cores (host) |
| GPU | RTX 5070 12 Go VRAM driver 595.71.05 compute 12.0 (Blackwell) |
| OS | Debian 12.x |
| CUDA | 12.9 |
| PyTorch | 2.11.0+cu130 |
| vLLM | 0.20.1 |
| Switcher API | port 8002 (toujours actif) |

## Layout disque (LVM vg-inference)

| LV | Taille | Point de montage |
|----|--------|-----------------|
| lv-root | 29 Go | / |
| lv-app | 34 Go | /opt/vllm-env |
| lv-models | 181 Go | /opt/models (120 Go libres) |
| lv-swap | 3.8 Go | swap |

Disque scsi0 etendu 150G -> 250G (online, sans reboot).

## Modeles disponibles

| Modele | Taille | Type | Service | Port | Status |
|--------|--------|------|---------|------|--------|
| Qwen2.5-Coder-7B-Instruct-AWQ | 5.2 Go | Texte coding | vllm-qwen | 8000 | defaut autostart |
| UnfilteredAI-1B | 2.0 Go | Texte generaliste | vllm-unfilteredai | 8000 | installe |
| BADMISTRAL-1.5B | 2.9 Go | Texte Mistral | vllm-badmistral | 8000 | installe |
| NSFW-gen-v2 | 25 Go | Image SDXL txt2img | vllm-imagegen | 8003 | installe |
| Qwen2.5-Coder-7B BF16 | 15 Go | - | - | - | SKIP 14 GiB VRAM requis |

1 seul modele texte actif a la fois (port 8000).
NSFW-gen-v2 sur port 8003 (pipeline SDXL independant).

## Switching des modeles

### Via frontend (recommande)
http://ia.zalin.home:8080 -> boutons Qwen / UnfilteredAI / BADMISTRAL / NSFW-gen-v2

### Via API
```
curl http://brain.zalin.home:8002/switch/qwen
curl http://brain.zalin.home:8002/switch/unfilteredai
curl http://brain.zalin.home:8002/switch/badmistral
curl http://brain.zalin.home:8002/switch/imagegen
```

### Via CLI (sur la VM inference)
```bash
vllm-switch qwen
vllm-switch unfilteredai
vllm-switch badmistral
vllm-switch imagegen
```

## Services systemd

| Service | Role | Port | Autostart |
|---------|------|------|-----------|
| vllm-switcher | Pilote les autres, HTTP API | 8002 | oui |
| vllm-qwen | Qwen2.5-Coder AWQ_Marlin | 8000 | oui |
| vllm-unfilteredai | UnfilteredAI-1B float16 | 8000 | non |
| vllm-badmistral | BADMISTRAL-1.5B float16 | 8000 | non |
| vllm-imagegen | NSFW-gen-v2 SDXL FastAPI | 8003 | non |

```bash
systemctl status vllm-switcher
journalctl -u vllm-qwen -f
journalctl -u vllm-imagegen -f
```

## Configuration des services

### vllm-qwen.service (awq_marlin, pas awq)
```
--quantization awq_marlin --dtype float16
--gpu-memory-utilization 0.90 --max-model-len 8192 --max-num-seqs 32
```

### vllm-badmistral.service
```
--dtype float16 --gpu-memory-utilization 0.90
--max-model-len 4096 --max-num-seqs 16
```

### vllm-imagegen.service
```
ExecStart=/opt/vllm-env/bin/python3 /usr/local/bin/image-gen-api.py
```
FastAPI port 8003. Pipeline SDXL charge en lazy (premier appel 2-3 min).
Compatible AUTOMATIC1111 API.

## APIs disponibles

### Texte (LLM) port 8000
```
GET  http://brain.zalin.home:8000/health
GET  http://brain.zalin.home:8000/v1/models
POST http://brain.zalin.home:8000/v1/chat/completions
POST http://brain.zalin.home:8000/v1/completions
```

### Image (SDXL) port 8003
```
GET  http://brain.zalin.home:8003/health
GET  http://brain.zalin.home:8003/sdapi/v1/sd-models
POST http://brain.zalin.home:8003/sdapi/v1/txt2img
```
Open WebUI -> Settings -> Images -> A1111 -> http://brain.zalin.home:8003
(configure via AUTOMATIC1111_BASE_URL dans la stack Portainer open-webui)

### Switcher port 8002
```
GET /status           -> {active, ready}
GET /switch/{model}   -> demarre le switch en arriere-plan
```

## Python venv (/opt/vllm-env)

Packages supplementaires :
- diffusers==0.38.0 (pipeline SDXL)
- accelerate (optimisation diffusers)
- fastapi, uvicorn (API image-gen port 8003)
- Pillow (encodage PNG base64)

## Post-installation (reconstruction VM)

```bash
qm set 100 --hookscript local:snippets/post-provision.sh

python3 -m venv /opt/vllm-env
/opt/vllm-env/bin/pip install vllm==0.20.1
/opt/vllm-env/bin/pip install diffusers==0.38.0 accelerate fastapi uvicorn Pillow

cp /opt/vLLM-yoyo/configs/vllm/*.service /etc/systemd/system/
cp /opt/vLLM-yoyo/configs/vllm/image-gen-api.py /usr/local/bin/
cp /opt/vLLM-yoyo/scripts/inference/vllm-switch /usr/local/bin/
cp /opt/vLLM-yoyo/scripts/inference/vllm-switcher-api.py /usr/local/bin/
chmod +x /usr/local/bin/vllm-switch /usr/local/bin/vllm-switcher-api.py
systemctl daemon-reload
systemctl enable --now vllm-qwen vllm-switcher
```

## Troubleshooting

### GPU non detecte
```bash
nvidia-smi
lspci -nnk | grep -A3 NVIDIA
# Kernel driver in use: nvidia (pas vfio-pci)
```

### Deux services sur le meme port
```bash
ss -tlnp | grep 8000
systemctl stop vllm-qwen vllm-unfilteredai vllm-badmistral vllm-imagegen
vllm-switch qwen
```

### Espace disque root
```bash
df -h /
# Si > 85% : nettoyer le cache torch (peut faire 2-3 Go)
rm -rf /root/.cache/vllm/torch_compile_cache
```

### Extension LVM (online, sans reboot)
```bash
# Depuis PVE2 :
qm resize 100 scsi0 +50G
# Dans la VM :
apt install cloud-guest-utils
growpart /dev/sda 3
pvresize /dev/sda3
lvextend -l +100%FREE /dev/vg-inference/lv-models
resize2fs /dev/vg-inference/lv-models
```