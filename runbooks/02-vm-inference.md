# Runbook 02 — VM-1 : Inference (vLLM + Qwen2.5-Coder-7B)

> **Statut : ✅ Opérationnelle** — vLLM 0.20.1 actif sur http://192.168.20.160:8000

> ⚠️ **Blackwell (compute 12.0 / RTX 5070)** : FP8 dynamique produit des sorties incorrectes sur cette architecture. Solution : modèle **AWQ pré-quantifié** (INT4), stable et performant.

## Spécifications réelles

| Paramètre | Valeur |
|-----------|--------|
| VMID | 100 |
| IP | 192.168.20.160 |
| RAM | 48 Go |
| CPU | 8 cores (host) |
| GPU | RTX 5070 — 12 Go VRAM — driver 595.71.05 — compute 12.0 (Blackwell) |
| OS | Debian 12.x |
| CUDA | 12.9 |
| PyTorch | 2.11.0+cu130 |
| vLLM | 0.20.1 |
| Modèle actif | Qwen2.5-Coder-7B-Instruct-AWQ (INT4) |

## Layout disque (LVM vg-inference)

| LV | Taille | Point de montage |
|----|--------|-----------------|
| lv-root | 29 Go | `/` |
| lv-app | 34 Go | `/opt/vllm-env` (venv Python) |
| lv-models | 76 Go | `/opt/models` |
| lv-swap | 3,8 Go | swap |
| **VG libre** | ~5 Go | — |

## Modèles disponibles

| Modèle | Taille | Status |
|--------|--------|--------|
| Qwen2.5-Coder-7B-Instruct-AWQ | 5.2 Go | ✅ actif (AWQ INT4, ~4 GiB VRAM) |
| Qwen2.5-Coder-7B (BF16) | 15 Go | ❌ 14 GiB requis > 12 GiB VRAM |
| Qwen2.5-Coder-7B (FP8) | 15 Go | ❌ garbage output sur Blackwell compute 12.0 |
| DeepSeek-Coder-V2-Lite | 30 Go | ❌ trop grand pour 12 Go VRAM |

## Service vLLM

Le service systemd `vllm-qwen` est configuré pour démarrer automatiquement.

```bash
# Statut
systemctl status vllm-qwen

# Logs
journalctl -u vllm-qwen -f

# Restart
systemctl restart vllm-qwen
```

### Configuration du service (`/etc/systemd/system/vllm-qwen.service`)

```ini
[Unit]
Description=vLLM OpenAI-compatible API - Qwen2.5-Coder-7B-Instruct-AWQ
After=network.target
Wants=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/vllm-env
Environment="CUDA_VISIBLE_DEVICES=0"
Environment="HF_HUB_OFFLINE=1"
Environment="VLLM_WORKER_MULTIPROC_METHOD=spawn"
ExecStart=/opt/vllm-env/bin/vllm serve /opt/models/qwen2.5-coder-7b-awq \
    --host 0.0.0.0 \
    --port 8000 \
    --served-model-name qwen2.5-coder-7b \
    --quantization awq \
    --dtype float16 \
    --gpu-memory-utilization 0.90 \
    --max-model-len 8192 \
    --max-num-seqs 32 \
    --trust-remote-code
Restart=on-failure
RestartSec=30
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
SyslogIdentifier=vllm-qwen

[Install]
WantedBy=multi-user.target
```

### Paramètres de chargement

- **Quantization** : AWQ INT4 pré-calibré (stable sur Blackwell compute 12.0)
- **Attention** : FlashAttention v2
- **Compilation** : torch.compile (inductor) + CUDA graphs
- **Temps de démarrage** : ~2-3 min (compile mis en cache après le 1er démarrage)

## API OpenAI-compatible

### Endpoints disponibles

```
GET  http://192.168.20.160:8000/health
GET  http://192.168.20.160:8000/v1/models
POST http://192.168.20.160:8000/v1/chat/completions
POST http://192.168.20.160:8000/v1/completions
GET  http://192.168.20.160:8000/metrics
```

### Tests rapides

```bash
# Santé
curl http://192.168.20.160:8000/health

# Modèles
curl http://192.168.20.160:8000/v1/models

# Inférence
curl http://192.168.20.160:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5-coder-7b",
    "messages": [{"role": "user", "content": "Ecris un hello world en Python"}],
    "max_tokens": 200
  }'
```

## Hookscript Proxmox

Le hookscript `post-provision.sh` est attaché à cette VM :
```bash
qm config 100 | grep hookscript
# hookscript: local:snippets/post-provision.sh
```

Il s'exécute à chaque `post-start` et configure automatiquement :
- Clés SSH root (ecdsa-key-20241218 + claude-mgmt)
- Proxy APT → `http://192.168.20.35:3142`
- CA interne zalin.home
- Packages de base (net-tools, vim, htop, screen)

## Reconstruction de la VM

Si la VM doit être reconstruite depuis zéro :

### 1. Génération de l'ISO

```bash
# Sur PVE2
scp /opt/vLLM-yoyo/configs/preseed-inference.cfg root@pve2.zalin.home:/tmp/
ssh root@pve2.zalin.home 'bash /tmp/remaster-iso.sh /tmp/preseed-inference.cfg debian-12-inference.iso'
```

### 2. Création de la VM

```bash
ssh root@pve2.zalin.home '
qm create 100 \
  --name inference \
  --memory 49152 \
  --cores 8 \
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
  --onboot 0 \
  --args "-no-reboot"
'
```

### 3. Installation automatique

```bash
# Lancer le monitor AVANT de démarrer la VM
nohup bash /opt/vLLM-yoyo/scripts/monitor-and-fix-vm.sh 100 192.168.20.160 \
  > /var/log/vm-monitor-100.log 2>&1 &

qm start 100
tail -f /var/log/vm-monitor-100.log
```

Le monitor détecte le `stopped` post-install, corrige le boot order et relance la VM.

### 4. Post-installation

```bash
# Attacher le hookscript
qm set 100 --hookscript local:snippets/post-provision.sh

# Réinstaller vLLM
python3 -m venv /opt/vllm-env
/opt/vllm-env/bin/pip install vllm==0.20.1

# Installer le service
cp /opt/vLLM-yoyo/configs/vllm-qwen.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now vllm-qwen
```

## Troubleshooting

### GPU non détecté
```bash
nvidia-smi
lspci -nnk | grep -A3 NVIDIA
# Kernel driver in use: nvidia (pas vfio-pci)
```

### OOM au chargement
```bash
# Réduire le contexte
--max-model-len 4096
# Ou augmenter la quantification
--quantization bitsandbytes
```

### Espace disque root (lv-root)
```bash
df -h /
# Si > 85% : nettoyer /root/.cache/vllm/torch_compile_cache (peut faire 2-3 Go)
du -sh /root/.cache/vllm/
```

### Extension LVM
```bash
# Depuis PVE2
qm resize 100 scsi0 +50G

# Dans la VM
pvresize /dev/sda3
lvextend -l +100%FREE /dev/vg-inference/lv-models
resize2fs /dev/vg-inference/lv-models
```
