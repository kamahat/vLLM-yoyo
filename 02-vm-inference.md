# Runbook 02 — VM-1 : Inference (vLLM + DeepSeek)

## Prérequis

- VM apt-cache (103) opérationnelle sur `192.168.20.163:3142`
- Proxmox VE 8.x avec VFIO configuré (runbook 01 ✓)
- Pool ZFS `G4-ZFS-POOL` disponible

## Spécifications

| Paramètre | Valeur |
|-----------|--------|
| VMID | 100 |
| IP | 192.168.20.160 |
| Disque | 150 Go (G4-ZFS-POOL) |
| RAM | 16 Go |
| CPU | 8 cores (host) |
| GPU | RTX 5070 — slot `24:00.0` (IDs `10de:2f04` + `10de:2f80`) |
| LVM | vg-inference : lv-root 20 Go / lv-models 80 Go / lv-app 15 Go / lv-swap 4 Go (~29,5 Go libre = 20%) |

## 1. Génération de l'ISO

```bash
# Sur claude-code
scp /opt/vLLM-yoyo/configs/preseed-inference.cfg root@pve2.zalin.home:/tmp/

ssh root@pve2.zalin.home \
  'bash /tmp/remaster-iso.sh /tmp/preseed-inference.cfg debian-12-inference.iso'
```

Le preseed configure automatiquement :
- IP statique `192.168.20.160/24`, GW `.1`, DNS `.20`
- Proxy APT → `http://192.168.20.163:3142/`
- LVM avec ≥15% de marge dans le VG
- Clés SSH root injectées
- Docker CE + Portainer agent (port 9001)
- GRUB console série (`ttyS0,115200n8`)

## 2. Création de la VM

```bash
ssh root@pve2.zalin.home '
qm create 100 \
  --name inference \
  --memory 16384 \
  --cores 8 \
  --sockets 1 \
  --cpu host \
  --machine q35 \
  --bios ovmf \
  --efidisk0 G4-ZFS-POOL:1,efitype=4m,pre-enrolled-keys=0 \
  --scsi0 G4-ZFS-POOL:150,iothread=1 \
  --scsihw virtio-scsi-single \
  --ide2 local:iso/debian-12-inference.iso,media=cdrom \
  --boot order="ide2;scsi0" \
  --ostype l26 \
  --net0 virtio,bridge=OVSBridge,tag=20 \
  --agent enabled=1 \
  --vga std \
  --serial0 socket \
  --hostpci0 0000:24:00.0,pcie=1,x-vga=1 \
  --hostpci1 0000:24:00.1,pcie=1 \
  --numa 1 \
  --onboot 0
qm start 100
'
```

> `--vga std` : console graphique pendant installation (retirer après).  
> `--numa 1` : requis pour GPU passthrough stable.

## 3. Suivi installation + nettoyage automatique

```bash
# Sur claude-code
nohup bash /opt/vLLM-yoyo/scripts/wait-and-cleanup-vm.sh 100 192.168.20.160 \
  > /var/log/vm-cleanup-100.log 2>&1 &

tail -f /var/log/vm-cleanup-100.log
```

Après détection SSH, le script :
- Détache l'ISO : `qm set 100 --ide2 none`
- Fixe le boot : `qm set 100 --boot order=scsi0`
- Vérifie `efibootmgr` sur la VM

## 4. Accès console

```bash
# Console graphique : Proxmox → VM 100 → Console (noVNC)

# Console série
ssh root@pve2.zalin.home 'qm terminal 100'
# Quitter avec Ctrl+O

# SSH direct (après installation)
ssh root@192.168.20.160
```

## 5. Configuration post-installation

```bash
ssh root@192.168.20.160

# Vérifier le GPU
lspci | grep -i nvidia
nvidia-smi   # doit afficher la RTX 5070

# Mise à jour système
apt update && apt upgrade -y

# Paquets essentiels
apt install -y build-essential python3-pip python3-venv pciutils nvtop net-tools
```

## 6. Installation drivers NVIDIA + CUDA 12.8

> ⚠️ La RTX 5070 (architecture Blackwell) requiert les drivers **570+** et **CUDA 12.8 minimum**.
> Utiliser impérativement le paquet `nvidia-open` (module kernel open-source), seul supporté sur cette génération.

````bash
wget https://developer.download.nvidia.com/compute/cuda/repos/debian12/x86_64/cuda-keyring_1.1-1_all.deb
dpkg -i cuda-keyring_1.1-1_all.deb
apt update
apt install -y cuda-toolkit-12-8 nvidia-open

echo 'export PATH=/usr/local/cuda/bin:$PATH' >> /etc/profile.d/cuda.sh
echo 'export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH' >> /etc/profile.d/cuda.sh
reboot
````

## 7. Installation vLLM

```bash
python3 -m venv /opt/vllm-env
source /opt/vllm-env/bin/activate

pip install vllm

# Vérifier
python3 -c "import vllm; print(vllm.__version__)"
```

## 8. Téléchargement du modèle

```bash
source /opt/vllm-env/bin/activate
pip install huggingface_hub[cli]

# Télécharger DeepSeek-Coder-V2-Lite-Instruct (~32 Go)
huggingface-cli download deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct \
  --local-dir /opt/models/deepseek-coder-v2-lite
```

## 9. Lancement vLLM

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

## 10. Service systemd vLLM

```bash
cat > /etc/systemd/system/vllm.service << 'EOF'
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

## 11. Validation

```bash
# Test API OpenAI-compatible depuis claude-code
curl http://192.168.20.160:8000/v1/models

curl http://192.168.20.160:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-coder",
    "messages": [{"role": "user", "content": "Ecris un hello world en Python"}],
    "max_tokens": 200
  }'
```

## 12. Extension LVM

```bash
# Depuis PVE2 — agrandir le disque virtuel
qm resize 100 scsi0 +50G

# Dans la VM — étendre le LV voulu
pvresize /dev/sda3
lvextend -l +100%FREE /dev/vg-inference/lv-models
resize2fs /dev/vg-inference/lv-models
```

## Troubleshooting
````markdown
### nvidia-smi introuvable
```bash
dpkg -l | grep nvidia
lsmod | grep nvidia
```
````
### GPU non détecté
```bash
lspci -nnk | grep -A3 "NVIDIA"
# → doit afficher : Kernel driver in use: nvidia (pas vfio-pci)
nvidia-smi
```

### OOM (Out of Memory)
```bash
# Réduire la longueur de contexte
--max-model-len 4096

# Ou activer la quantification
--quantization bitsandbytes
```

### Enlever le VGA (après installation)
```bash
# Depuis PVE2, après installation terminée
qm set 100 --vga none
```
