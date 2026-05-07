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
| LVM | vg-inference : lv-root 20 Go / lv-models 80 Go / lv-app 35 Go / lv-swap 4 Go |

> ⚠️ **lv-app a été agrandi à 35 Go** (initialement 15 Go) — CUDA + vLLM + cache pip + tmp nécessitent ~30 Go.
> Prévoir au moins 35 Go pour `lv-app` lors d'un redéploiement.

## 1. Génération de l'ISO

```bash
# Sur claude-code
scp /opt/vLLM-yoyo/configs/preseed-inference.cfg root@pve2.zalin.home:/tmp/

ssh root@pve2.zalin.home \
  'bash /tmp/remaster-iso.sh /tmp/preseed-inference.cfg debian-12-inference.iso'
```

Le preseed configure automatiquement :
- IP statique `192.168.20.160/24`, GW `.1`, DNS `.20`
- Proxy APT → `http://192.168.20.163:3142/` (pendant installation ET post-install via `/etc/apt/apt.conf.d/01proxy`)
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

# Configurer le proxy apt-cacher-ng
echo 'Acquire::http::Proxy "http://192.168.20.163:3142/";' > /etc/apt/apt.conf.d/01proxy
echo 'Acquire::https::Proxy "DIRECT";' >> /etc/apt/apt.conf.d/01proxy
cat /etc/apt/apt.conf.d/01proxy

# Mise à jour système
apt update && apt upgrade -y

# Paquets essentiels
# Note: nvtop n'est pas disponible sur Debian 12 — nvidia-smi suffit après CUDA
apt install -y build-essential python3-pip python3-venv pciutils net-tools \
  linux-headers-$(uname -r) dkms
```

## 6. Installation drivers NVIDIA + CUDA 12.8

> ⚠️ La RTX 5070 (architecture Blackwell) requiert les drivers **570+** et **CUDA 12.8 minimum**.
> Utiliser impérativement le paquet `nvidia-open` (module kernel open-source), seul supporté sur cette génération.

```bash
wget https://developer.download.nvidia.com/compute/cuda/repos/debian12/x86_64/cuda-keyring_1.1-1_all.deb
dpkg -i cuda-keyring_1.1-1_all.deb
apt update
apt install -y cuda-toolkit-12-8 nvidia-open

# Créer le profil CUDA (ne pas oublier — le fichier n'est pas créé automatiquement)
cat > /etc/profile.d/cuda.sh << 'EOF'
export PATH=/usr/local/cuda/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH
export PIP_CACHE_DIR=/opt/vllm-env/pip-cache
export TMPDIR=/opt/vllm-env/tmp
EOF

source /etc/profile.d/cuda.sh
reboot
```

```bash
# Vérifier après reboot
nvidia-smi
nvcc --version
```

## 7. Installation vLLM

> ⚠️ CUDA + vLLM + cache pip + tmp nécessitent ~30 Go sur `lv-app`.
> Si `lv-app` est trop petit, l'agrandir avant de continuer (voir section Extension LVM).

```bash
# Vérifier l'espace disponible
df -h /opt/vllm-env
vgs  # vérifier le VFree dans le VG

# Agrandir lv-app si nécessaire (depuis la VM, sans passer par PVE2)
lvextend -L +20G /dev/vg-inference/lv-app
resize2fs /dev/vg-inference/lv-app

# Créer les répertoires pip/tmp sur lv-app
mkdir -p /opt/vllm-env/pip-cache /opt/vllm-env/tmp
source /etc/profile.d/cuda.sh

# Créer et activer le venv
python3 -m venv /opt/vllm-env
source /opt/vllm-env/bin/activate

# Installer vLLM (cache et tmp redirigés vers lv-app)
pip install vllm --cache-dir /opt/vllm-env/pip-cache

# Vérifier
pip show vllm
```

## 8. Téléchargement du modèle

```bash
source /opt/vllm-env/bin/activate
pip install huggingface_hub[cli] --cache-dir /opt/vllm-env/pip-cache

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
Environment="PATH=/usr/local/cuda/bin:/opt/vllm-env/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
Environment="LD_LIBRARY_PATH=/usr/local/cuda/lib64"
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
# Vérifier l'espace libre dans le VG
vgs

# Agrandir un LV depuis la VM (sans passer par PVE2 si le VG a de la place)
lvextend -L +20G /dev/vg-inference/lv-app
resize2fs /dev/vg-inference/lv-app

# Si le VG est plein — agrandir le disque virtuel depuis PVE2 d'abord
ssh root@pve2.zalin.home 'qm resize 100 scsi0 +50G'
# Puis dans la VM
pvresize /dev/sda3
lvextend -l +100%FREE /dev/vg-inference/lv-models
resize2fs /dev/vg-inference/lv-models
```

## Troubleshooting

### Proxy apt-cacher-ng absent ou mal configuré
```bash
cat /etc/apt/apt.conf.d/01proxy
echo 'Acquire::http::Proxy "http://192.168.20.163:3142/";' > /etc/apt/apt.conf.d/01proxy
echo 'Acquire::https::Proxy "DIRECT";' >> /etc/apt/apt.conf.d/01proxy
apt update
```

### Erreur "No space left" pendant pip install
```bash
# Vérifier les espaces
df -h
vgs
# Agrandir lv-app si VFree disponible dans le VG
lvextend -L +20G /dev/vg-inference/lv-app
resize2fs /dev/vg-inference/lv-app
# Relancer avec cache/tmp sur lv-app
export TMPDIR=/opt/vllm-env/tmp
mkdir -p $TMPDIR
pip install vllm --cache-dir /opt/vllm-env/pip-cache
```

### nvcc introuvable après reboot
```bash
source /etc/profile.d/cuda.sh
# ou vérifier que le fichier existe
ls /usr/local/cuda/bin/nvcc
cat /etc/profile.d/cuda.sh
```

### nvidia-smi introuvable
```bash
dpkg -l | grep nvidia
lsmod | grep nvidia
```

### GPU non détecté
```bash
lspci -nnk | grep -A3 "NVIDIA"
# → doit afficher : Kernel driver in use: nvidia (pas vfio-pci)
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
qm set 100 --vga none
```
