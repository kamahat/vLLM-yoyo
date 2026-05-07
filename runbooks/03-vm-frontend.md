# Runbook 03 — VM-2 : Frontend (Open WebUI + Nginx)

## Prérequis

- VM-1 inference opérationnelle (API vLLM sur port 8000)
- Pool ZFS `G4-ZFS-POOL` disponible

## 1. Création de la VM dans Proxmox

```bash
qm create 102 \
  --name frontend \
  --memory 4096 \
  --cores 4 \
  --cpu host \
  --scsihw virtio-scsi-pci \
  --scsi0 G4-ZFS-POOL:30 \
  --cdrom local:iso/debian-12-netinst.iso \
  --net0 virtio,bridge=vmbr0 \
  --ostype l26
```

## 2. Installation Debian 12 + Docker

```bash
apt update && apt upgrade -y
apt install -y curl ca-certificates gnupg

# Docker
curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker.gpg
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" \
  > /etc/apt/sources.list.d/docker.list
apt update && apt install -y docker-ce docker-compose-plugin
```

## 3. Déploiement Open WebUI

```bash
mkdir -p /opt/openwebui && cd /opt/openwebui

cat > docker-compose.yml << EOF
services:
  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: open-webui
    restart: unless-stopped
    ports:
      - "3000:8080"
    volumes:
      - open-webui:/app/backend/data
    environment:
      - OPENAI_API_BASE_URL=http://<IP-VM1>:8000/v1
      - OPENAI_API_KEY=not-required
      - WEBUI_AUTH=true
    extra_hosts:
      - "host.docker.internal:host-gateway"

volumes:
  open-webui:
EOF

docker compose up -d
```

## 4. Configuration Nginx

```bash
apt install -y nginx

cat > /etc/nginx/sites-available/openwebui << EOF
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_read_timeout 3600;
    }
}
EOF

ln -s /etc/nginx/sites-available/openwebui /etc/nginx/sites-enabled/
rm /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
```

## 5. Validation

- Accéder à `http://<IP-VM2>/`
- Créer le compte admin
- Vérifier la connexion au modèle DeepSeek dans les paramètres
- Tester un échange de vibe coding
