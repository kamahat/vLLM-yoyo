# Runbook 04 — VM-3 : RAG (ChromaDB + LlamaIndex)

> **Phase 2** — À déployer après validation de VM-1 et VM-2.

## Prérequis

- VM apt-cache (103) opérationnelle sur `192.168.20.163:3142`
- VM inference (100) opérationnelle
- VM frontend (101) opérationnelle
- Pool ZFS `G4-ZFS-POOL` disponible

## Spécifications

| Paramètre | Valeur |
|-----------|--------|
| VMID | 102 |
| IP | 192.168.20.162 |
| Disque | 220 Go (G4-ZFS-POOL) |
| RAM | 8 Go |
| CPU | 4 cores (host) |
| LVM | vg-rag : lv-root 20 Go / lv-chromadb 100 Go (`/opt/chromadb`) / lv-models 50 Go (`/opt/models`) / lv-swap 4 Go (~44,5 Go libre = 20%) |

## 1. Génération de l'ISO

```bash
# Sur claude-code
scp /opt/vLLM-yoyo/configs/preseed-rag.cfg root@pve2.zalin.home:/tmp/

ssh root@pve2.zalin.home \
  'bash /tmp/remaster-iso.sh /tmp/preseed-rag.cfg debian-12-rag.iso'
```

## 2. Création de la VM

```bash
ssh root@pve2.zalin.home '
qm create 102 \
  --name rag \
  --memory 8192 \
  --cores 4 \
  --sockets 1 \
  --cpu host \
  --machine q35 \
  --bios ovmf \
  --efidisk0 G4-ZFS-POOL:1,efitype=4m,pre-enrolled-keys=0 \
  --scsi0 G4-ZFS-POOL:220,iothread=1 \
  --scsihw virtio-scsi-single \
  --ide2 local:iso/debian-12-rag.iso,media=cdrom \
  --boot order="ide2;scsi0" \
  --ostype l26 \
  --net0 virtio,bridge=OVSBridge,tag=20 \
  --agent enabled=1 \
  --vga std \
  --serial0 socket \
  --onboot 1
qm start 102
'
```

## 3. Suivi installation + nettoyage automatique

```bash
# Sur claude-code
nohup bash /opt/vLLM-yoyo/scripts/wait-and-cleanup-vm.sh 102 192.168.20.162 \
  > /var/log/vm-cleanup-102.log 2>&1 &

tail -f /var/log/vm-cleanup-102.log
```

## 4. Déploiement ChromaDB via Portainer

Déployer le stack `configs/openwebui/stack-rag.yml` via Portainer (`https://192.168.20.91:9443`).

Ou manuellement :

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
      - /opt/chromadb:/chroma/chroma
    environment:
      - IS_PERSISTENT=TRUE
      - ANONYMIZED_TELEMETRY=FALSE

  rag-api:
    image: python:3.11-slim
    container_name: rag-api
    restart: unless-stopped
    ports:
      - "8080:8080"
    volumes:
      - /opt/models:/models
      - ./rag:/app
    working_dir: /app
    command: python -m uvicorn main:app --host 0.0.0.0 --port 8080
    depends_on:
      - chromadb
    environment:
      - CHROMA_HOST=chromadb
      - CHROMA_PORT=8000
      - INFERENCE_URL=http://192.168.20.160:8000/v1
EOF

docker compose up -d
```

## 5. Sources d'ingestion prévues

- Codebase personnelle (repos Git locaux)
- Documentation ESPHome
- Documentation Home Assistant
- Documentation Proxmox
- Documentation OPNsense

## 6. Extension LVM

```bash
# Depuis PVE2
qm resize 102 scsi0 +50G

# Dans la VM — étendre ChromaDB ou models
pvresize /dev/sda3
lvextend -l +100%FREE /dev/vg-rag/lv-chromadb
resize2fs /dev/vg-rag/lv-chromadb
```
