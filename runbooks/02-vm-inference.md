# Runbook 02 — VM-1 : Inference (vLLM + DeepSeek)

## Prérequis

- Proxmox VE 8.x avec VFIO configuré (runbook 01 ✓)
- ISO Debian 12 Bookworm disponible sur PVE2
- Pool ZFS `G4-ZFS-POOL` disponible

## 1. Création de la VM dans Proxmox

```bash
# Slot PCIe GPU réel sur PVE2
# 24:00.0 → GPU  (10de:2f04)
# 24:00.1 → Audio (10de:2f80)

# Créer la VM
qm create 100 \
  --name inference \
  --memory 32768 \
  --balloon 0 \
  --cores 8 \
  --cpu host \
  --scsihw virtio-scsi-pci \
  --scsi0 G4-ZFS-POOL:100 \
  --ide2 local:iso/debian-12.13.0-preseed.iso,media=cdrom \
  --net0 virtio,bridge=OVSBridge,tag=20 \
  --ostype l26 \
  --machine q35 \
  --bios ovmf \
  --efidisk0 G4-ZFS-POOL:1,efitype=4m \
  --hostpci0 0000:24:00.0,pcie=1,x-vga=0 \
  --hostpci1 0000:24:00.1,pcie=1 \
  --vga std \
  --serial0 socket \
  --boot order="ide2;scsi0" \
  --agent enabled=1

# > --vga std : permet de suivre l'install via noVNC (Proxmox console)
# > Supprimer après installation : qm set 100 --vga none
```

## 2. Installation Debian 12 (automatique via preseed)

L'ISO `debian-12.13.0-preseed.iso` contient le fichier preseed pré-configuré :
- IP statique : `192.168.20.160/24`, GW `192.168.20.1`, DNS `192.168.20.20`
- Paquets : `vim htop screen dnsutils curl wget git qemu-guest-agent`
- Clés SSH injectées dans `/root/.ssh/authorized_keys`
- `PermitRootLogin prohibit-password` activé

Suivre la progression via **noVNC** dans Proxmox (`https://pve2.zalin.home:8006`).

Après reboot :
```bash
# Supprimer la VGA temporaire
qm set 100 --vga none

# Détacher l'ISO
qm set 100 --ide2 none
```

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
