# Runbook 02 — VM-1 : Inference (vLLM + DeepSeek)

## Prérequis

- Proxmox VE 8.x avec VFIO configuré (runbook 01 ✓)
- ISO Debian 12 Bookworm disponible sur PVE2
- Pool ZFS `G4-ZFS-POOL` disponible

## 1. Création de la VM dans Proxmox

```bash
# Récupérer le slot PCIe du GPU
lspci -nn | grep 2f04
# ex: 03:00.0 → slot = 0000:03:00.0

# Créer la VM (adapter VMID et slot PCIe)
qm create 101 \
  --name inference \
  --memory 32768 \
  --cores 8 \
  --cpu host \
  --scsihw virtio-scsi-pci \
  --scsi0 G4-ZFS-POOL:100 \
  --cdrom local:iso/debian-12-netinst.iso \
  --net0 virtio,bridge=vmbr0 \
  --ostype l26 \
  --machine q35 \
  --bios ovmf \
  --efidisk0 G4-ZFS-POOL:1 \
  --hostpci0 0000:03:00.0,pcie=1,x-vga=0

# Ajouter le device audio du GPU (même groupe IOMMU)
qm set 101 --hostpci1 0000:03:00.1,pcie=1
```

## 2. Installation Debian 12

- Boot sur l'ISO Debian 12 Bookworm
- Installation minimale (sans desktop, sans GUI)
- Partitionnement : tout sur le disque principal
- Paquets : SSH server uniquement

## 3. Configuration post-installation

```bash
# Mise à jour système
apt update && apt upgrade -y

# Paquets essentiels
apt install -y curl wget git build-essential python3-pip python3-venv \
               pciutils htop nvtop net-tools
```

## 4. Installation CUDA 12.x

```bash
# Ajouter le repo NVIDIA CUDA
wget https://developer.download.nvidia.com/compute/cuda/repos/debian12/x86_64/cuda-keyring_1.1-1_all.deb
dpkg -i cuda-keyring_1.1-1_all.deb
apt update

# Installer CUDA Toolkit 12.x
apt install -y cuda-toolkit-12-6

# Vérifier
nvidia-smi
nvcc --version
```

## 5. Installation vLLM

```bash
# Environnement Python
python3 -m venv /opt/vllm-env
source /opt/vllm-env/bin/activate

# Installer vLLM (avec support CUDA)
pip install vllm

# Vérifier
python3 -c "import vllm; print(vllm.__version__)"
```

## 6. Téléchargement du modèle

```bash
# Installer huggingface-cli
pip install huggingface_hub[cli]

# Télécharger DeepSeek-Coder-V2-Lite-Instruct
huggingface-cli download deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct \
  --local-dir /opt/models/deepseek-coder-v2-lite
```

## 7. Lancement vLLM

```bash
source /opt/vllm-env/bin/activate

vllm serve deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct \
  --model /opt/models/deepseek-coder-v2-lite \
  --dtype bfloat16 \
  --max-model-len 8192 \
  --host 0.0.0.0 \
  --port 8000 \
  --served-model-name deepseek-coder
```

## 8. Validation

```bash
# Test API OpenAI-compatible
curl http://localhost:8000/v1/models

curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-coder",
    "messages": [{"role": "user", "content": "Ecris un hello world en Python"}],
    "max_tokens": 200
  }'
```

## 9. Service systemd

```bash
cat > /etc/systemd/system/vllm.service << EOF
[Unit]
Description=vLLM Inference Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt
ExecStart=/opt/vllm-env/bin/vllm serve deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct \
  --model /opt/models/deepseek-coder-v2-lite \
  --dtype bfloat16 \
  --max-model-len 8192 \
  --host 0.0.0.0 \
  --port 8000 \
  --served-model-name deepseek-coder
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable vllm
systemctl start vllm
```

## Troubleshooting

### GPU non détecté
```bash
nvidia-smi  # si erreur → vérifier passthrough PCIe dans Proxmox
lspci | grep NVIDIA
```

### OOM (Out of Memory)
- Réduire `--max-model-len` à 4096
- Ou utiliser quantification Q8 : ajouter `--quantization bitsandbytes`
