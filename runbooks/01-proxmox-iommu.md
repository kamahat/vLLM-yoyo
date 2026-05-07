# Runbook 01 — IOMMU / VFIO sur Proxmox

> **Statut : DÉJÀ CONFIGURÉ ✓** — Ce runbook est conservé pour référence et reproductibilité.

## Prérequis

- Proxmox VE 8.x installé
- GPU : KFA2 RTX 5070 (PCI IDs : `10de:2f04` + `10de:2f80`)

## 1. Activation IOMMU dans GRUB

```bash
# /etc/default/grub
GRUB_CMDLINE_LINUX_DEFAULT="quiet intel_iommu=on iommu=pt"

update-grub
```

## 2. Modules VFIO

```bash
# /etc/modules
vfio
vfio_iommu_type1
vfio_pci
vfio_virqfd
```

```bash
update-initramfs -u -k all
```

## 3. Blacklist drivers NVIDIA sur l'hôte

```bash
# /etc/modprobe.d/blacklist-nvidia.conf
blacklist nouveau
blacklist nvidia
blacklist nvidiafb
```

## 4. Liaison vfio-pci aux PCI IDs du GPU

```bash
# /etc/modprobe.d/vfio.conf
options vfio-pci ids=10de:2f04,10de:2f80
```

```bash
update-initramfs -u -k all
reboot
```

## 5. Vérification post-reboot

```bash
# Vérifier IOMMU actif
dmesg | grep -e DMAR -e IOMMU

# Vérifier que vfio-pci gère le GPU
lspci -nnk | grep -A3 "2f04"
# doit afficher : Kernel driver in use: vfio-pci
```

## Résultat attendu

```
10de:2f04 → Kernel driver in use: vfio-pci ✓
10de:2f80 → Kernel driver in use: vfio-pci ✓
```
