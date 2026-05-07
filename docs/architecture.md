# Architecture — vLLM-yoyo

## Vue d'ensemble

```
[Client / Browser]
       |
       v
[VM-2 frontend] ── Nginx (80/443) ── Open WebUI
       |
       | API OpenAI-compatible (HTTP :8000)
       v
[VM-1 inference] ── vLLM ── RTX 5070 (GPU passthrough)
       |
       | API embedding + inférence
       v
[VM-3 rag] ── ChromaDB ── LlamaIndex
```

## VM-1 : inference

- **OS** : Debian 12 Bookworm (minimal)
- **GPU** : RTX 5070 12 Go VRAM — passthrough PCIe exclusif
- **Runtime** : vLLM (serving OpenAI-compatible API)
- **Modèle** : DeepSeek-Coder-V2-Lite 16B (bf16, ~10-11 Go VRAM)
- **Port exposé** : 8000 (réseau interne uniquement)
- **Stockage** : ~100 Go sur G4-ZFS-POOL

## VM-2 : frontend

- **OS** : Debian 12 Bookworm (minimal)
- **Stack** : Docker — Open WebUI + Nginx reverse proxy
- **Auth** : activée (comptes locaux)
- **Ports exposés** : 80/443 (réseau interne)
- **Stockage** : ~30 Go sur G4-ZFS-POOL

## VM-3 : rag (Phase 2)

- **OS** : Debian 12 Bookworm (minimal)
- **Stack** : Docker — ChromaDB + LlamaIndex/LangChain
- **Sources** : codebase Git locale + docs techniques
- **Port exposé** : API RAG consommée par Open WebUI
- **Stockage** : ~150 Go sur G4-ZFS-POOL

## Décisions techniques

| Décision | Choix | Raison |
|----------|-------|--------|
| Runtime inférence | vLLM | API OpenAI-compatible native, support bf16 |
| Modèle | DeepSeek-Coder-V2-Lite 16B | MoE, meilleur rapport qualité/VRAM (12 Go) |
| Frontend | Open WebUI | Ecosystème mature, plugin RAG natif |
| Vector DB | ChromaDB | Léger, Docker-ready, API simple |
| OS VM | Debian 12 | Stable, minimal, support CUDA officiel |
