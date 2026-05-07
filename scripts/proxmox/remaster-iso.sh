#!/bin/bash
# remaster-iso.sh — Génère une ISO Debian 12 avec preseed embarqué
# Usage: ./remaster-iso.sh <preseed.cfg> <output-name>
# Exemple: ./remaster-iso.sh /tmp/preseed-inference.cfg debian-12-inference.iso
set -e

ISO_SRC=/var/lib/vz/template/iso/debian-12.13.0-netinst.iso
PRESEED_FILE="${1:-/tmp/preseed.cfg}"
OUTPUT_NAME="${2:-debian-12-preseed.iso}"
ISO_DST="/var/lib/vz/template/iso/${OUTPUT_NAME}"

if [ ! -f "$PRESEED_FILE" ]; then
  echo "ERREUR: preseed introuvable: $PRESEED_FILE"; exit 1
fi
if [ ! -f "$ISO_SRC" ]; then
  echo "ERREUR: ISO source introuvable: $ISO_SRC"; exit 1
fi

echo "=== Preseed : $PRESEED_FILE ==="
echo "=== Destination : $ISO_DST ==="

# xorriso boot_image replay exige indev == outdev
# → on copie l'ISO source vers la destination, puis on modifie en place
echo "=== Copie ISO source → destination ==="
cp -f "$ISO_SRC" "$ISO_DST"

echo "=== grub.cfg avec auto-preseed ==="
cat > /tmp/grub-preseed.cfg << 'GRUBEOF'
set default=0
set timeout=5
menuentry "Debian 12 - Auto install" {
    linux /install.amd/vmlinuz auto=true priority=critical file=/cdrom/preseed.cfg quiet ---
    initrd /install.amd/initrd.gz
}
menuentry "Debian 12 - Manuel" {
    linux /install.amd/vmlinuz quiet ---
    initrd /install.amd/initrd.gz
}
GRUBEOF

echo "=== isolinux txt.cfg avec auto-preseed ==="
cat > /tmp/txt-preseed.cfg << 'TXTEOF'
default auto
label auto
    menu label ^Automated Install
    kernel /install.amd/vmlinuz
    append auto=true priority=critical file=/cdrom/preseed.cfg vga=788 initrd=/install.amd/initrd.gz quiet ---
label manual
    menu label ^Manual Install
    kernel /install.amd/vmlinuz
    append vga=788 initrd=/install.amd/initrd.gz quiet ---
TXTEOF

echo "=== Injection preseed dans l'ISO (in-place) ==="
xorriso -indev "$ISO_DST" \
  -outdev "$ISO_DST" \
  -map "$PRESEED_FILE" /preseed.cfg \
  -map /tmp/grub-preseed.cfg /boot/grub/grub.cfg \
  -map /tmp/txt-preseed.cfg /isolinux/txt.cfg \
  -boot_image any replay 2>&1 | grep -E "UPDATE|Written|WARN|FAIL|added"

ls -lh "$ISO_DST"
echo "=== ISO prete : $OUTPUT_NAME ==="
