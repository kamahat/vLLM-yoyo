# vLLM-yoyo — Stack IA locale pour Vibe Coding

Environnement d'IA générative auto-hébergé dédié au vibe coding,
avec une expérience proche de Claude Code.

## Architecture

| VM | Rôle | Stack |
|----|------|-------|
| VM-1 `inference` | GPU passthrough RTX 5070 | vLLM + DeepSeek-Coder |
| VM-2 `frontend` | Interface web | Open WebUI + Nginx |
| VM-3 `rag` | Recherche contextuelle | ChromaDB + LlamaIndex |

## Infrastructure

- **Hyperviseur** : Proxmox VE 8.x — `pve2.zalin.home`
- **Serveur** : HP DL380 Gen8 — 128 Go RAM, 2× E5-2673 (48t)
- **GPU** : KFA2 RTX 5070 1-Click OC — 12 Go VRAM
- **Stockage** : pool ZFS `G4-ZFS-POOL`

## Déploiement

Voir les runbooks dans `runbooks/` dans l'ordre numéroté :

1. [`01-proxmox-iommu.md`](runbooks/01-proxmox-iommu.md) — IOMMU/VFIO (déjà configuré ✓)
2. [`02-vm-inference.md`](runbooks/02-vm-inference.md) — VM-1 : vLLM + modèle
3. [`03-vm-frontend.md`](runbooks/03-vm-frontend.md) — VM-2 : Open WebUI
4. [`04-vm-rag.md`](runbooks/04-vm-rag.md) — VM-3 : RAG (Phase 2)

## Modèle retenu

**DeepSeek-Coder-V2-Lite 16B** (MoE, ~10–11 Go VRAM en bf16)
→ Meilleur rapport qualité/VRAM dans la contrainte 12 Go.

## Statut

- [x] IOMMU/VFIO configuré sur PVE2
- [x] GPU isolé via vfio-pci
- [x] Structure du repo initialisée
- [ ] VM-1 inference créée
- [ ] vLLM opérationnel
- [ ] VM-2 frontend déployée
- [ ] VM-3 RAG déployée
