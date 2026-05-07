#!/bin/bash
# install-docker-agent.sh
# Installe Docker CE + Portainer Agent sur une VM Debian 12
# Usage : bash install-docker-agent.sh
# Piloter depuis claude-code : ssh root@<IP-VM> 'bash -s' < install-docker-agent.sh
set -e

echo "=== Installation Docker CE ==="
apt-get update -qq
apt-get install -y ca-certificates curl gnupg

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | \
  gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/debian bookworm stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update -qq
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

systemctl enable docker
systemctl start docker
echo "Docker $(docker --version) installe"

echo "=== Déploiement Portainer Agent ==="
mkdir -p /opt/portainer-agent

cat > /opt/portainer-agent/docker-compose.yml << 'EOF'
services:
  portainer-agent:
    image: portainer/agent:latest
    container_name: portainer-agent
    restart: always
    ports:
      - "9001:9001"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - /var/lib/docker/volumes:/var/lib/docker/volumes
    environment:
      - AGENT_CLUSTER_ADDR=tasks.portainer-agent
EOF

docker compose -f /opt/portainer-agent/docker-compose.yml up -d

echo "=== Vérification ==="
sleep 3
docker ps | grep portainer-agent
echo ""
echo "Agent Portainer actif sur le port 9001"
echo "Ajouter dans Portainer (192.168.20.91:9443) :"
echo "  Environments → Add Environment → Agent → URL : $(hostname -I | awk '{print $1}'):9001"
