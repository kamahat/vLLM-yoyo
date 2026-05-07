# Hardware — PVE2.zalin.home

## Serveur

| Composant | Détail |
|-----------|--------|
| Modèle | HP DL380 Gen8 |
| CPU | 2× Intel E5-2673 (~24c / 48t total) |
| RAM | 128 Go ECC |
| Stockage | Pool ZFS NVMe `G4-ZFS-POOL` (~1 To disponible) |
| Hyperviseur | Proxmox VE 8.x |

## GPU

| Composant | Détail |
|-----------|--------|
| Modèle | KFA2 RTX 5070 1-Click OC |
| VRAM | 12 Go |
| PCI ID GPU | `10de:2f04` |
| PCI ID Audio | `10de:2f80` |
| Passthrough | PCIe exclusif (VFIO) |
| IOMMU | Configuré ✓ |

## Passthrough PCIe

Configuration Proxmox (`hostpci0`) :
```
hostpci0: <slot>,pcie=1,x-vga=0
```
> Le slot PCIe exact est à récupérer via `lspci -nn | grep 2f04` sur PVE2.

## Stockage VMs (G4-ZFS-POOL)

| VM | Usage | Taille |
|----|-------|--------|
| VM-1 inference | OS + modèle DeepSeek | ~100 Go |
| VM-2 frontend | OS + Docker | ~30 Go |
| VM-3 rag | OS + ChromaDB + index | ~150 Go |
| Réserve | Modèles additionnels | ~100 Go |
