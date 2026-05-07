# vLLM-yoyo — Stack IA locale pour Vibe Coding

Environnement d'IA générative auto-hébergé dédié au vibe coding,
avec une expérience proche de Claude Code.

## Architecture

| VM | VMID | IP | Rôle | Disque | Stack |
|----|------|----|------|--------|-------|
| `apt-cache` | 103 | 192.168.20.163 | Proxy cache APT | 25 Go | apt-cacher-ng (Docker) |
| `inference` | 100 | 192.168.20.160 | GPU passthrough RTX 5070 | 150 Go | vLLM + DeepSeek-Coder |
| `frontend`  | 101 | 192.168.20.161 | Interface web | 50 Go | Open WebUI + Nginx |
| `rag`       | 102 | 192.168.20.162 | Recherche contextuelle | 220 Go | ChromaDB + LlamaIndex |

> **Ordre de démarrage** : `apt-cache` → `inference` → `frontend` → `rag`

## Infrastructure

- **Hyperviseur** : Proxmox VE 8.x — `pve2.zalin.home`
- **Serveur** : HP DL380 Gen8 — 128 Go RAM, 2× E5-2673 (48t)
- **GPU** : KFA2 RTX 5070 12 Go VRAM — slot PCIe `24:00.0` (IDs `10de:2f04` + `10de:2f80`)
- **Stockage** : pool ZFS `G4-ZFS-POOL`
- **Réseau** : OVSBridge, VLAN 20 — `192.168.20.0/24`, GW `.1`, DNS `.20`
- **Portainer** : `https://192.168.20.91:9443` (agent sur port 9001 sur chaque VM)
- **Claude-code** : `192.168.20.150` (point de pilotage central)

## Déploiement

Voir les runbooks dans `runbooks/` dans l'ordre numéroté :

0. [`00-apt-cache.md`](runbooks/00-apt-cache.md) — VM apt-cache : proxy APT (**à démarrer en premier**)
1. [`01-proxmox-iommu.md`](runbooks/01-proxmox-iommu.md) — IOMMU/VFIO (déjà configuré ✓)
2. [`02-vm-inference.md`](runbooks/02-vm-inference.md) — VM-1 : vLLM + modèle
3. [`03-vm-frontend.md`](runbooks/03-vm-frontend.md) — VM-2 : Open WebUI
4. [`04-vm-rag.md`](runbooks/04-vm-rag.md) — VM-3 : RAG (Phase 2)

## Modèle retenu

**DeepSeek-Coder-V2-Lite 16B** (MoE, ~10–11 Go VRAM en bf16)
→ Meilleur rapport qualité/VRAM dans la contrainte 12 Go.

## Workflow de déploiement des VMs

Toutes les VMs sont installées via **ISO Debian 12 remastered avec preseed** :

```
Windows (claude-code) → pscp → claude-code (192.168.20.150)
                             → scp → pve2
                                   → remaster-iso.sh (xorriso)
                                   → qm create + qm start
```

Chaque ISO contient :
- Partitionnement LVM automatique (≥15% de marge dans le VG)
- Proxy APT → `http://192.168.20.163:3142/`
- Clés SSH root injectées
- Docker CE + Portainer agent (port 9001) installés automatiquement
- Console série `ttyS0` configurée dans GRUB

Après installation, le script `wait-and-cleanup-vm.sh` détache l'ISO et fixe l'ordre de boot automatiquement.

## Statut

- [x] IOMMU/VFIO configuré sur PVE2
- [x] GPU isolé via vfio-pci (`24:00.0`)
- [x] Structure du repo initialisée
- [x] Preseeds créés pour les 4 VMs (avec proxy APT, serial console, LVM avec marge)
- [x] ISOs remastered sur PVE2
- [x] Script wait-and-cleanup-vm.sh
- [ ] VM apt-cache opérationnelle
- [ ] VM inference installée
- [ ] CUDA + vLLM opérationnel
- [ ] VM frontend déployée
- [ ] VM rag déployée
