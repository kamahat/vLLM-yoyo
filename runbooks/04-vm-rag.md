# Runbook 04 — VM-3 : RAG (ChromaDB + LlamaIndex)

> **Phase 2** — À déployer après validation de VM-1 et VM-2.

## Prérequis

- VM-1 inference opérationnelle
- VM-2 frontend opérationnelle
- Pool ZFS `G4-ZFS-POOL` disponible

## 1. Création de la VM dans Proxmox

```bash
qm create 103 \
  --name rag \
  --memory 8192 \
  --cores 4 \
  --cpu host \
  --scsihw virtio-scsi-pci \
  --scsi0 G4-ZFS-POOL:150 \
  --cdrom local:iso/debian-12-netinst.iso \
  --net0 virtio,bridge=vmbr0 \
  --ostype l26
```

## 2. Stack RAG (à détailler en Phase 2)

- ChromaDB (vector store)
- LlamaIndex (pipeline ingestion + query)
- Sources : repos Git locaux + docs techniques

## Sources d'ingestion prévues

- Codebase personnelle (repos Git locaux)
- Documentation ESPHome
- Documentation Home Assistant
- Documentation Proxmox
- Documentation OPNsense
