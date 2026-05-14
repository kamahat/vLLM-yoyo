# Runbook 04 — VM-3 : RAG (ChromaDB + LlamaIndex)

> **Statut : 🔄 Installation en cours** — VM 102, Debian 12 preseed en cours d'installation.

## Spécifications réelles déployées

| Paramètre | Valeur |
|-----------|--------|
| VMID | 102 |
| IP | 192.168.20.162 |
| RAM | 4 Go |
| CPU | 4 cores (host) |
| Disque | 30 Go (G4-ZFS-POOL) |
| OS | Debian 12.x (installation en cours) |

## Layout disque (LVM vg-rag)

| LV | Taille | Point de montage |
|----|--------|-----------------|
| lv-root | 12 Go | `/` |
| lv-docker | 12 Go | `/var/lib/docker` |
| lv-swap | 2 Go | swap |

> ⚠️ Disque plus petit que prévu initialement (220 Go → 30 Go).  
> À étendre si besoin avec `qm resize 102 scsi0 +XXG` + `lvextend`.

## Hookscript Proxmox

Le hookscript `post-provision.sh` est attaché à cette VM :
```bash
qm config 102 | grep hookscript
# hookscript: local:snippets/post-provision.sh
```

Il configurera automatiquement au premier démarrage :
- Clés SSH root (ecdsa-key-20241218 + claude-mgmt)
- Proxy APT → `http://192.168.20.35:3142`
- CA interne zalin.home
- Packages de base

## Suivi installation

```bash
# Monitor en cours sur PVE2 (log)
ssh root@pve2.zalin.home 'cat /var/log/vm-monitor-102.log'

# Statut VM
ssh root@pve2.zalin.home 'qm status 102'
```

Une fois l'installation terminée, le monitor :
1. Détecte le `stopped` (reboot → shutdown via `-no-reboot`)
2. Supprime l'ISO, fixe `boot=scsi0`, retire `-no-reboot`
3. Redémarre la VM → Debian démarre
4. Le hookscript configure SSH/proxy automatiquement

## Déploiement ChromaDB (post-installation)

```bash
ssh root@192.168.20.162

mkdir -p /opt/chromadb-stack && cd /opt/chromadb-stack

cat > docker-compose.yml << 'EOF'
services:
  chromadb:
    image: chromadb/chroma:latest
    container_name: chromadb
    restart: unless-stopped
    ports:
      - "8001:8000"
    volumes:
      - chromadb-data:/chroma/chroma
    environment:
      - IS_PERSISTENT=TRUE
      - ANONYMIZED_TELEMETRY=FALSE

  portainer-agent:
    image: portainer/agent:latest
    container_name: portainer-agent
    restart: always
    ports:
      - "9001:9001"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - /var/lib/docker/volumes:/var/lib/docker/volumes

volumes:
  chromadb-data:
EOF

docker compose up -d
```

## Sources d'ingestion prévues

- Codebase personnelle (repos Git locaux)
- Documentation ESPHome
- Documentation Home Assistant
- Documentation Proxmox
- Documentation OPNsense

## Extension LVM si nécessaire

```bash
# Depuis PVE2 — agrandir le disque virtuel
qm resize 102 scsi0 +20G

# Dans la VM
pvresize /dev/sda3
lvextend -l +100%FREE /dev/vg-rag/lv-docker
resize2fs /dev/vg-rag/lv-docker
```

## Reconstruction depuis zéro

### 1. Génération de l'ISO

```bash
# preseed-rag.cfg est sur PVE2 dans /tmp/
ssh root@pve2.zalin.home 'bash /tmp/remaster-iso.sh /tmp/preseed-rag.cfg debian-12-rag.iso'
```

### 2. Création de la VM

```bash
ssh root@pve2.zalin.home '
qm create 102 \
  --name rag \
  --memory 4096 \
  --cores 4 \
  --cpu host \
  --machine q35 \
  --bios ovmf \
  --efidisk0 G4-ZFS-POOL:1,efitype=4m,pre-enrolled-keys=0 \
  --scsi0 G4-ZFS-POOL:30 \
  --scsihw virtio-scsi-pci \
  --ide2 local:iso/debian-12-rag.iso,media=cdrom \
  --boot order="ide2;scsi0" \
  --net0 virtio,bridge=OVSBridge,tag=20 \
  --vga std \
  --serial0 socket \
  --ostype l26 \
  --agent enabled=1 \
  --onboot 0 \
  --args "-no-reboot"
'
```

### 3. Installation automatique

```bash
nohup bash /opt/vLLM-yoyo/scripts/monitor-and-fix-vm.sh 102 192.168.20.162 \
  > /var/log/vm-monitor-102.log 2>&1 &

qm start 102
qm set 102 --hookscript local:snippets/post-provision.sh
tail -f /var/log/vm-monitor-102.log
```

## Troubleshooting

### VM bloquée en reinstall
```bash
ssh root@pve2.zalin.home 'qm config 102 | grep -E "^boot|^ide2|^args"'

# Correction manuelle
ssh root@pve2.zalin.home '
  qm stop 102
  qm set 102 --ide2 none
  qm set 102 --boot order=scsi0
  qm set 102 --delete args 2>/dev/null || true
  qm start 102
'
```
