# Architecture — vLLM-yoyo

## Vue d'ensemble

```
[Client / Browser]
       |
       v
[VM-2 frontend :101] ── Nginx (80) ── Open WebUI
       |
       | API OpenAI-compatible (HTTP :8000)
       v
[VM-1 inference :100] ── vLLM ── RTX 5070 12Go (GPU passthrough PCIe 24:00.0)
       |
       | API embedding + inférence
       v
[VM-3 rag :102] ── ChromaDB ── LlamaIndex

[VM-0 apt-cache :103] ── apt-cacher-ng :3142
       ^
       |  proxy APT pendant installation et apt-get
       +-- inference + frontend + rag
```

## VM-0 : apt-cache (VMID 103)

- **IP** : `192.168.20.163`
- **OS** : Debian 12 Bookworm (minimal)
- **Rôle** : Proxy cache APT pour toutes les VMs du réseau
- **Stack** : Docker — `sameersbn/apt-cacher-ng` port 3142
- **Disque** : 25 Go sur G4-ZFS-POOL
- **LVM** : vg-aptcache → lv-root 8 Go / lv-cache 10 Go (`/var/cache/apt-cacher-ng`) / lv-swap 1 Go (~4,5 Go libre = 19%)
- **Démarrer en premier** : doit être opérationnel avant d'installer les autres VMs

## VM-1 : inference (VMID 100)

- **IP** : `192.168.20.160`
- **OS** : Debian 12 Bookworm (minimal)
- **GPU** : RTX 5070 12 Go VRAM — passthrough PCIe exclusif (slot 24:00.0, IDs 10de:2f04 + 10de:2f80)
- **RAM** : 16 Go
- **CPU** : 8 cores (host)
- **Runtime** : vLLM (serving OpenAI-compatible API)
- **Modèle** : DeepSeek-Coder-V2-Lite 16B (bf16, ~10-11 Go VRAM)
- **Port exposé** : 8000 (réseau interne uniquement)
- **Disque** : 150 Go sur G4-ZFS-POOL
- **LVM** : vg-inference → lv-root 20 Go / lv-models 80 Go (`/opt/models`) / lv-app 15 Go (`/opt/vllm-env`) / lv-swap 4 Go (~29,5 Go libre = 20%)

## VM-2 : frontend (VMID 101)

- **IP** : `192.168.20.161`
- **OS** : Debian 12 Bookworm (minimal)
- **RAM** : 4 Go
- **CPU** : 4 cores
- **Stack** : Docker — Open WebUI + Nginx reverse proxy
- **Auth** : activée (comptes locaux)
- **Ports exposés** : 80 (réseau interne)
- **Disque** : 50 Go sur G4-ZFS-POOL
- **LVM** : vg-frontend → lv-root 15 Go / lv-docker 20 Go (`/var/lib/docker`) / lv-swap 2 Go (~11,5 Go libre = 24%)

## VM-3 : rag (VMID 102)

- **IP** : `192.168.20.162`
- **OS** : Debian 12 Bookworm (minimal)
- **RAM** : 8 Go
- **CPU** : 4 cores
- **Stack** : Docker — ChromaDB + LlamaIndex/LangChain
- **Sources** : codebase Git locale + docs techniques
- **Port exposé** : API RAG consommée par Open WebUI
- **Disque** : 220 Go sur G4-ZFS-POOL
- **LVM** : vg-rag → lv-root 20 Go / lv-chromadb 100 Go (`/opt/chromadb`) / lv-models 50 Go (`/opt/models`) / lv-swap 4 Go (~44,5 Go libre = 20%)

## Infrastructure commune

### Réseau
- **Bridge** : OVSBridge, VLAN tag 20
- **Subnet** : `192.168.20.0/24`
- **Gateway** : `192.168.20.1` (PVE2)
- **DNS** : `192.168.20.20`

### Accès console
Chaque VM dispose de :
- `--vga std` : console graphique Proxmox noVNC (utilisée pendant installation)
- `--serial0 socket` : console série via `qm terminal <VMID>` ou xterm.js Proxmox

Après installation, retirer le VGA GPU :
```bash
qm set 100 --vga none   # inference uniquement (GPU passthrough)
```

### Gestion via Portainer
- **Portainer server** : `https://192.168.20.91:9443`
- **Agent** : déployé automatiquement sur chaque VM (port 9001)
- **Enregistrement** : `scripts/portainer-register-envs.sh`

### Extension LVM
```bash
# Depuis PVE2 — agrandir le disque virtuel
qm resize <VMID> scsi0 +<taille>G

# Dans la VM — étendre le LV voulu
pvresize /dev/sda3
lvextend -l +100%FREE /dev/vg-<nom>/lv-<nom>
resize2fs /dev/vg-<nom>/lv-<nom>   # ext4
```

## Décisions techniques

| Décision | Choix | Raison |
|----------|-------|--------|
| Runtime inférence | vLLM | API OpenAI-compatible native, support bf16 |
| Modèle | DeepSeek-Coder-V2-Lite 16B | MoE, meilleur rapport qualité/VRAM (12 Go) |
| Frontend | Open WebUI | Ecosystème mature, plugin RAG natif |
| Vector DB | ChromaDB | Léger, Docker-ready, API simple |
| OS VM | Debian 12 | Stable, minimal, support CUDA officiel |
| Proxy APT | apt-cacher-ng | Évite retéléchargements entre VMs |
| Partitionnement | LVM (expert_recipe) | Extensible sans réinstall, LVs dédiés par usage |
| Boot VM | UEFI/OVMF + efidisk | EFI NVRAM persistant → reboot correct post-install |
| Console | VGA std + serial0 socket | VGA pour install, série pour exploitation |
| Install réseau | Preseed dans ISO (xorriso) | 100% automatisé, piloté depuis claude-code |
