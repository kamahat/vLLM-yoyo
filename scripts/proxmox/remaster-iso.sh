#!/bin/bash
set -e
ISO_SRC=/var/lib/vz/template/iso/debian-12.13.0-netinst.iso
ISO_DST=/var/lib/vz/template/iso/debian-12.13.0-preseed.iso

echo "=== grub-preseed.cfg ==="
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

echo "=== txt-preseed.cfg ==="
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

echo "=== Clone ISO avec preseed ==="
xorriso -indev "$ISO_SRC" \
  -outdev "$ISO_DST" \
  -map /tmp/preseed.cfg /preseed.cfg \
  -map /tmp/grub-preseed.cfg /boot/grub/grub.cfg \
  -map /tmp/txt-preseed.cfg /isolinux/txt.cfg \
  -boot_image any replay 2>&1 | tail -8

ls -lh "$ISO_DST"
echo "=== ISO preseed prete ==="
