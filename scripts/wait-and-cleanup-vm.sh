#!/bin/bash
# wait-and-cleanup-vm.sh
# Attend qu'une VM soit joignable en SSH puis détache l'ISO et fixe le boot order
# Usage: bash wait-and-cleanup-vm.sh <VMID> <IP>
# Exemple: bash wait-and-cleanup-vm.sh 100 192.168.20.160

set -e

VMID="${1:?VMID requis}"
IP="${2:?IP requise}"
PVE_HOST="pve2.zalin.home"
MAX_WAIT=1800   # 30 minutes max
INTERVAL=15

echo "=== Attente de la VM ${VMID} (${IP}) ==="
elapsed=0

while true; do
  if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -o BatchMode=yes \
       root@"${IP}" 'uname -r' >/dev/null 2>&1; then
    echo "  OK: SSH disponible sur ${IP} après ${elapsed}s"
    break
  fi

  if [ "$elapsed" -ge "$MAX_WAIT" ]; then
    echo "  TIMEOUT: VM non joignable après ${MAX_WAIT}s"
    exit 1
  fi

  echo "  Attente... (${elapsed}s / ${MAX_WAIT}s)"
  sleep "$INTERVAL"
  elapsed=$((elapsed + INTERVAL))
done

echo ""
echo "=== Nettoyage VM ${VMID} sur ${PVE_HOST} ==="

# Détacher l'ISO
ssh -o StrictHostKeyChecking=no root@"${PVE_HOST}" \
  "qm set ${VMID} --ide2 none && echo '  ISO détachée'"

# Corriger l'ordre de boot : scsi0 uniquement
ssh -o StrictHostKeyChecking=no root@"${PVE_HOST}" \
  "qm set ${VMID} --boot order=scsi0 && echo '  Boot order -> scsi0'"

# Vérifier efibootmgr sur la VM
echo ""
echo "=== Entrées EFI sur la VM ${IP} ==="
ssh -o StrictHostKeyChecking=no root@"${IP}" 'efibootmgr -v 2>/dev/null || echo "efibootmgr non disponible"'

echo ""
echo "=== Config finale VM ${VMID} ==="
ssh -o StrictHostKeyChecking=no root@"${PVE_HOST}" \
  "qm config ${VMID} | grep -E 'boot|ide|scsi|serial|vga'"

echo ""
echo "=== Done : VM ${VMID} prête ==="
