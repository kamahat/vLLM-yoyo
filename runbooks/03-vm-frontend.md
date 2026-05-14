# Runbook 03 — VM-2 : Frontend (Open WebUI + Nginx)

## Prérequis

- VM apt-cache (103) opérationnelle sur `192.168.20.163:3142`
- VM inference (100) opérationnelle — API vLLM sur `192.168.20.160:8000`
- Pool ZFS `G4-ZFS-POOL` disponible

## Spécifications

| Paramètre | Valeur |
|-----------|--------|
| VMID | 105 |
| IP | 192.168.20.161 |
| Disque | 50 Go (G4-ZFS-POOL) |
| RAM | 4 Go |
| CPU | 4 cores (host) |
| LVM | vg-frontend : lv-root 15 Go / lv-docker 20 Go (`/var/lib/docker`) / lv-swap 2 Go (~11,5 Go libre = 24%) |

## 1. Génération de l'ISO

```bash
# Sur claude-code
scp /opt/vLLM-yoyo/configs/preseed-frontend.cfg root@pve2.zalin.home:/tmp/

ssh root@pve2.zalin.home \
  'bash /tmp/remaster-iso.sh /tmp/preseed-frontend.cfg debian-12-frontend.iso'
```

Le preseed configure automatiquement :
- IP statique `192.168.20.161/24`
- Proxy APT → `http://192.168.20.163:3142/`
- LVM avec ≥15% de marge dans le VG
- Docker CE + Portainer agent (port 9001)
- GRUB console série

## 2. Création de la VM

L'option `--args "-no-reboot"` convertit le reboot de fin d'installation en shutdown QEMU,
permettant au script de monitoring de corriger le boot order avant de relancer la VM.

```bash
ssh root@pve2.zalin.home '
qm create 105 \
  --name frontend \
  --memory 4096 \
  --cores 4 \
  --sockets 1 \
  --cpu host \
  --machine q35 \
  --bios ovmf \
  --efidisk0 G4-ZFS-POOL:1,efitype=4m,pre-enrolled-keys=0 \
  --scsi0 G4-ZFS-POOL:50,iothread=1 \
  --scsihw virtio-scsi-single \
  --ide2 local:iso/debian-12-frontend.iso,media=cdrom \
  --boot order="ide2;scsi0" \
  --ostype l26 \
  --net0 virtio,bridge=OVSBridge,tag=20 \
  --agent enabled=1 \
  --vga std \
  --serial0 socket \
  --onboot 1 \
  --args "-no-reboot"
qm start 101
'
```

> `--args "-no-reboot"` : converti le reboot guest en shutdown QEMU (retiré automatiquement par le script de monitoring).

## 3. Suivi installation + nettoyage automatique

```bash
# Sur claude-code
nohup bash /opt/vLLM-yoyo/scripts/monitor-and-fix-vm.sh 105 192.168.20.161 \
  > /var/log/vm-monitor-101.log 2>&1 &

tail -f /var/log/vm-monitor-101.log
```

Le script détecte que la VM passe en `stopped` (reboot converti en shutdown par `-no-reboot`), puis :
- Détache l'ISO : `qm set 101 --ide2 none`
- Fixe le boot : `qm set 101 --boot order=scsi0`
- Supprime l'arg `-no-reboot` : `qm set 101 --delete args`
- Relance la VM : `qm start 101`
- Attend que SSH soit disponible sur `192.168.20.161`

## 4. Déploiement Open WebUI via Portainer

Déployer le stack `configs/openwebui/stack-frontend.yml` via Portainer (`https://192.168.20.91:9443`).

Ou manuellement :

```bash
ssh root@192.168.20.161

mkdir -p /opt/openwebui && cd /opt/openwebui

cat > docker-compose.yml << 'EOF'
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
      - OPENAI_API_BASE_URL=http://192.168.20.160:8000/v1
      - OPENAI_API_KEY=not-required
      - WEBUI_AUTH=true

volumes:
  open-webui:
EOF

docker compose up -d
```

## 5. Configuration Nginx

```bash
apt install -y nginx

cat > /etc/nginx/sites-available/openwebui << 'EOF'
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 3600s;
    }
}
EOF

ln -s /etc/nginx/sites-available/openwebui /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
```

## 6. Validation

```bash
# Depuis le réseau interne
curl http://192.168.20.161/

# Ou depuis un navigateur
# http://192.168.20.161/
```

- Créer le compte admin au premier accès
- Vérifier la connexion au modèle DeepSeek dans Paramètres → Connexions
- Tester un échange de vibe coding

## 7. Extension LVM

```bash
# Depuis PVE2
qm resize 101 scsi0 +20G

# Dans la VM
pvresize /dev/sda3
lvextend -l +100%FREE /dev/vg-frontend/lv-docker
resize2fs /dev/vg-frontend/lv-docker
```

## Troubleshooting

### VM bloquée en reinstall (boot sur ISO au lieu du disque)
```bash
# Vérifier l'état de la VM
ssh root@pve2.zalin.home 'qm config 101 | grep -E "^boot|^ide2|^args"'

# Corriger manuellement si le script n'a pas tourné
ssh root@pve2.zalin.home '
  qm stop 101
  qm set 101 --ide2 none
  qm set 101 --boot order=scsi0
  qm set 101 --delete args 2>/dev/null || true
  qm start 101
'
```
