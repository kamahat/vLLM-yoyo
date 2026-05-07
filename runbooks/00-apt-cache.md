# Runbook 00 — VM apt-cache (apt-cacher-ng)

> **À déployer EN PREMIER** — Les autres VMs utilisent ce proxy pendant leur installation.

## Rôle

Proxy cache APT sur `192.168.20.163:3142`. Toutes les VMs du réseau pointent dessus via :
```
d-i mirror/http/proxy string http://192.168.20.163:3142/
```
Les paquets Debian sont téléchargés une seule fois et mis en cache localement.

> ⚠️ **HTTPS** : Par défaut apt-cacher-ng bloque les tunnels HTTPS (`CONNECT`). Il faut activer
> `PassThroughPattern: .*` dans la config pour permettre aux VMs d'accéder aux repos HTTPS
> (ex: repo NVIDIA CUDA). Voir étape 5.

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

L'option `--args "-no-reboot"` convertit le reboot de fin d'installation en shutdown QEMU,
permettant au script de monitoring de corriger le boot order avant de relancer la VM.

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
  --onboot 1 \
  --args "-no-reboot"
qm start 103
'
```

> `--onboot 1` : la VM démarre automatiquement avec PVE2.
> `--args "-no-reboot"` : converti le reboot guest en shutdown QEMU (retiré automatiquement par le script de monitoring).

## 3. Suivi installation + nettoyage automatique

```bash
# Sur claude-code — lancer en background
nohup bash /opt/vLLM-yoyo/scripts/monitor-and-fix-vm.sh 103 192.168.20.163 \
  > /var/log/vm-monitor-103.log 2>&1 &

# Suivre les logs
tail -f /var/log/vm-monitor-103.log
```

Le script détecte que la VM passe en `stopped` (reboot converti en shutdown par `-no-reboot`), puis :
- Détache l'ISO : `qm set 103 --ide2 none`
- Fixe le boot : `qm set 103 --boot order=scsi0`
- Supprime l'arg `-no-reboot` : `qm set 103 --delete args`
- Relance la VM : `qm start 103`
- Attend que SSH soit disponible sur `192.168.20.163`

## 4. Vérification

```bash
# Tester le proxy depuis claude-code
curl -v http://192.168.20.163:3142/

# Ou depuis une autre VM
curl http://192.168.20.163:3142/acng-report.html
```

## 5. Service apt-cacher-ng (installé nativement via preseed)

apt-cacher-ng est installé directement via `pkgsel/include` dans le preseed (pas de Docker).

| Paramètre | Valeur |
|-----------|--------|
| Service | `apt-cacher-ng` |
| Port | 3142 |
| Cache | `/var/cache/apt-cacher-ng` (sur `lv-cache`) |
| Config | `/etc/apt-cacher-ng/acng.conf` |

### Autoriser les tunnels HTTPS (PassThroughPattern)

Par défaut apt-cacher-ng refuse les tunnels HTTPS, ce qui bloque les repos comme NVIDIA CUDA.
À configurer après le premier démarrage de la VM :

```bash
ssh root@192.168.20.163

echo 'PassThroughPattern: .*' >> /etc/apt-cacher-ng/acng.conf
systemctl restart apt-cacher-ng
systemctl status apt-cacher-ng

# Vérifier
grep PassThrough /etc/apt-cacher-ng/acng.conf
```

> Cette configuration autorise le CONNECT vers tous les hôtes HTTPS.
> Pour restreindre uniquement au repo NVIDIA :
> `PassThroughPattern: developer\.download\.nvidia\.com:443$`

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
# Vérifier le service
ssh root@192.168.20.163 'systemctl status apt-cacher-ng'

# Relancer si nécessaire
ssh root@192.168.20.163 'systemctl restart apt-cacher-ng'

# Vérifier les logs
ssh root@192.168.20.163 'journalctl -u apt-cacher-ng -n 50'
```

### Repo HTTPS bloqué (erreur 403 CONNECT denied)
```bash
# Symptôme sur la VM cliente :
# W: Impossible de récupérer https://... Invalid response from proxy: HTTP/1.0 403 CONNECT denied

# Sur la VM apt-cache :
grep PassThrough /etc/apt-cacher-ng/acng.conf
# Si absent ou commenté :
echo 'PassThroughPattern: .*' >> /etc/apt-cacher-ng/acng.conf
systemctl restart apt-cacher-ng
```

### Vider le cache
```bash
ssh root@192.168.20.163 'find /var/cache/apt-cacher-ng -name "*.bin" -delete'
# Ou via le rapport web : http://192.168.20.163:3142/acng-report.html
```

### VM bloquée en reinstall (boot sur ISO au lieu du disque)
```bash
# Vérifier l'état de la VM
ssh root@pve2.zalin.home 'qm config 103 | grep -E "^boot|^ide2|^args"'

# Corriger manuellement si le script n'a pas tourné
ssh root@pve2.zalin.home '
  qm stop 103
  qm set 103 --ide2 none
  qm set 103 --boot order=scsi0
  qm set 103 --delete args 2>/dev/null || true
  qm start 103
'
```
