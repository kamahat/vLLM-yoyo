#!/bin/bash
# monitor-and-fix-vm.sh
# Attend que la VM passe en stopped (reboot converti en shutdown par -no-reboot),
# fixe le boot order, retire l'arg -no-reboot, puis relance la VM.
# Usage: ./monitor-and-fix-vm.sh <VMID> <IP>

VMID="${1:-103}"
IP="${2:-192.168.20.163}"
PVE="root@pve2.zalin.home"
MAX_WAIT=2400  # 40 min max
INTERVAL=5

echo "=== Monitor VM $VMID - attente shutdown post-installation ==="
echo "    IP cible : $IP"
echo "    Debut : $(date)"

elapsed=0
while [ $elapsed -lt $MAX_WAIT ]; do
    STATUS=$(ssh -o StrictHostKeyChecking=no $PVE "qm status $VMID 2>/dev/null" | awk '{print $2}')
    if [ "$STATUS" = "stopped" ]; then
        echo "$(date): VM $VMID stoppee - installation terminee!"
        echo "$(date): Correction du boot order..."
        ssh -o StrictHostKeyChecking=no $PVE "
            qm set $VMID --ide2 none
            qm set $VMID --boot order=scsi0
            qm set $VMID --delete args 2>/dev/null || true
            echo 'Boot order fixe: ide2=none, boot=scsi0, args supprime'
            qm config $VMID | grep -E '^boot|^ide2|^args'
        "
        echo "$(date): Redemarrage VM $VMID..."
        ssh -o StrictHostKeyChecking=no $PVE "qm start $VMID"
        echo "$(date): VM $VMID relancee - attente SSH sur $IP..."
        break
    fi
    echo "  $elapsed s / ${MAX_WAIT}s - status: $STATUS"
    sleep $INTERVAL
    elapsed=$((elapsed + INTERVAL))
done

if [ $elapsed -ge $MAX_WAIT ]; then
    echo "TIMEOUT: VM $VMID n'est pas passe en stopped apres ${MAX_WAIT}s"
    exit 1
fi

# Attente SSH disponible
echo "=== Attente SSH sur $IP ==="
ssh_elapsed=0
while [ $ssh_elapsed -lt 600 ]; do
    if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 root@$IP "echo ssh-ok" 2>/dev/null | grep -q ssh-ok; then
        echo "$(date): SSH disponible sur $IP"
        echo "=== VM $VMID operationnelle ==="
        exit 0
    fi
    sleep 10
    ssh_elapsed=$((ssh_elapsed + 10))
done

echo "TIMEOUT SSH sur $IP"
exit 1
