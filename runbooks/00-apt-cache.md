# Runbook 00 — VM apt-cache (apt-cacher-ng)

> **À déployer EN PREMIER** — Les autres VMs utilisent ce proxy pendant leur installation.

## Rôle

Proxy cache APT sur `192.168.20.163:3142`. Toutes les VMs du réseau pointent dessus via :
```
d-i mirror/http/proxy string http://192.168.20.163:3142/
```
Les paquets Debian sont téléchargés une seule fois et mis en cache localement.

## Spécifications

| Paramètre | Valeur |
|-----------|--------|
| VMID | 103 |
| IP | 192.168.20.163 |
| Disque | 25 Go (G4-ZFS-POOL) |
| RAM | 2 Go |
| CPU | 2 cores |
| LVM | vg-aptcache : lv-root 8 Go / lv-cache 10 Go / lv-swap 1 Go (~4,5 Go libre) |

## 1. Génération de l'ISO

```bash
# Sur claude-code (192.168.20.150)
scp /opt/vLLM-yoyo/configs/preseed-apt-cache.cfg root@pve2.zalin.home:/tmp/

ssh root@pve2.zalin.home \
  'bash /tmp/remaster-iso.sh /tmp/preseed-apt-cache.cfg debian-12-apt-cache.iso'
```

## 2. Création de la VM

```bash
ssh root@pve2.zalin.home '
qm create 103 \
  --name apt-cache \
  --memory 2048 \
  --cores 2 \
  --sockets 1 \
  --cpu host \
  --machine q35 \
  --bios ovmf \
  --efidisk0 G4-ZFS-POOL:1,efitype=4m,pre-enrolled-keys=0 \
  --scsi0 G4-ZFS-POOL:25,iothread=1 \
  --scsihw virtio-scsi-single \
  --ide2 local:iso/debian-12-apt-cache.iso,media=cdrom \
  --boot order="ide2;scsi0" \
  --ostype l26 \
  --net0 virtio,bridge=OVSBridge,tag=20 \
  --agent enabled=1 \
  --vga std \
  --serial0 socket \
  --onboot 1
qm start 103
'
```

> `--onboot 1` : la VM démarre automatiquement avec PVE2.

## 3. Suivi installation + nettoyage automatique

```bash
# Sur claude-code — lancer en background
nohup bash /opt/vLLM-yoyo/scripts/wait-and-cleanup-vm.sh 103 192.168.20.163 \
  > /var/log/vm-cleanup-103.log 2>&1 &

# Suivre les logs
tail -f /var/log/vm-cleanup-103.log
```

Le script détecte le reboot sur Debian (SSH disponible), puis :
- Détache l'ISO : `qm set 103 --ide2 none`
- Fixe le boot : `qm set 103 --boot order=scsi0`

## 4. Vérification

```bash
# Tester le proxy depuis claude-code
curl -v http://192.168.20.163:3142/

# Ou depuis une autre VM
curl http://192.168.20.163:3142/acng-report.html
```

## 5. Stack Docker (déployée automatiquement par le preseed)

Fichier `/opt/apt-cacher-ng/docker-compose.yml` sur la VM :

```yaml
services:
  apt-cacher-ng:
    image: sameersbn/apt-cacher-ng:latest
    container_name: apt-cacher-ng
    restart: always
    ports:
      - "3142:3142"
    volumes:
      - /var/cache/apt-cacher-ng:/var/cache/apt-cacher-ng
```

Le cache est persisté sur le LV dédié `lv-cache` monté sur `/var/cache/apt-cacher-ng`.

## 6. Accès console série

```bash
# Depuis PVE2
qm terminal 103

# Depuis claude-code
ssh root@pve2.zalin.home 'qm terminal 103'
```

## Troubleshooting

### Proxy non joignable depuis les VMs
```bash
# Vérifier le container
ssh root@192.168.20.163 'docker ps | grep apt-cacher'

# Relancer si nécessaire
ssh root@192.168.20.163 'cd /opt/apt-cacher-ng && docker compose up -d'
```

### Vider le cache
```bash
ssh root@192.168.20.163 'docker exec apt-cacher-ng find /var/cache/apt-cacher-ng -name "*.bin" -delete'
```
