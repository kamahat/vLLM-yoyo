#!/bin/bash
# portainer-register-envs.sh
# Enregistre les VMs inference/frontend/rag dans Portainer via API
# Piloter depuis claude-code : bash portainer-register-envs.sh
set -e

PORTAINER_URL="${PORTAINER_URL:-https://192.168.20.91:9443}"
API_KEY="${PORTAINER_TOKEN:?Variable PORTAINER_TOKEN non definie}"

declare -A VMS
VMS["inference"]="192.168.20.160"
VMS["frontend"]="192.168.20.161"
VMS["rag"]="192.168.20.162"

register_env() {
  local name=$1
  local ip=$2
  local url="${ip}:9001"

  echo "=== Enregistrement : $name ($url) ==="

  # Vérifier que l'agent répond
  if ! curl -sk --connect-timeout 5 "http://${ip}:9001" > /dev/null 2>&1; then
    echo "  WARN: agent non joignable sur $url — skip"
    return
  fi

  # Vérifier si l'environment existe déjà
  existing=$(curl -sk \
    -H "X-API-Key: ${API_KEY}" \
    "${PORTAINER_URL}/api/endpoints" \
    | python3 -c "
import sys, json
data = json.load(sys.stdin)
for e in data:
    if e.get('Name') == '${name}':
        print(e['Id'])
        break
" 2>/dev/null)

  if [ -n "$existing" ]; then
    echo "  INFO: environment '$name' existe deja (ID: $existing) — skip"
    return
  fi

  # Créer l'environment agent
  result=$(curl -sk -X POST \
    -H "X-API-Key: ${API_KEY}" \
    -H "Content-Type: multipart/form-data" \
    -F "Name=${name}" \
    -F "EndpointCreationType=2" \
    -F "URL=${url}" \
    -F "GroupID=1" \
    -F "TLS=false" \
    "${PORTAINER_URL}/api/endpoints")

  id=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('Id','ERR'))" 2>/dev/null)
  echo "  OK: environment '$name' cree (ID: $id)"
}

echo "=== Environments Portainer existants ==="
curl -sk -H "X-API-Key: ${API_KEY}" \
  "${PORTAINER_URL}/api/endpoints" \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
for e in data:
    print(f\"  ID {e['Id']:3d} | {e['Name']:20s} | type={e['Type']} | {e.get('URL','')}\")
"

echo ""
echo "=== Enregistrement des VMs ==="
for name in inference frontend rag; do
  register_env "$name" "${VMS[$name]}"
done

echo ""
echo "=== Environments apres enregistrement ==="
curl -sk -H "X-API-Key: ${API_KEY}" \
  "${PORTAINER_URL}/api/endpoints" \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
for e in data:
    status = 'UP' if e.get('Status') == 1 else 'DOWN'
    print(f\"  ID {e['Id']:3d} | {e['Name']:20s} | {status} | {e.get('URL','')}\")
"
