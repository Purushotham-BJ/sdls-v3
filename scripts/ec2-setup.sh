#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# SDLS v3 — EC2 Instance Bootstrap Script
# Run once after launching an EC2 instance (all roles).
# Sets up Docker, Docker Compose, and the SDLS project directory.
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail

echo "📦 SDLS v3 EC2 Bootstrap"
echo "========================"

# Docker Engine
if ! command -v docker &>/dev/null; then
  echo "→ Installing Docker …"
  apt-get update -qq
  apt-get install -y -q ca-certificates curl gnupg
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | tee /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-compose-plugin
  systemctl enable --now docker
  usermod -aG docker ubuntu
  echo "✅ Docker installed"
else
  echo "✅ Docker already installed: $(docker --version)"
fi

# Docker Compose v2
if ! docker compose version &>/dev/null; then
  echo "→ Installing Docker Compose plugin …"
  apt-get install -y -q docker-compose-plugin
fi

# Project directory
mkdir -p /opt/sdls
chown ubuntu:ubuntu /opt/sdls
echo "✅ Project directory: /opt/sdls"

# EC2 private IP
PRIVATE_IP=$(curl -s --max-time 2 http://169.254.169.254/latest/meta-data/local-ipv4 || hostname -I | awk '{print $1}')
echo "✅ Private IP detected: $PRIVATE_IP"
echo "SYSTEM_IP=$PRIVATE_IP" >> /etc/environment

echo ""
echo "Bootstrap complete. Copy the SDLS project to /opt/sdls, then run:"
echo "  cd /opt/sdls"
echo "  # For System 3 (infra node):"
echo "    REDIS_HOST=\$SYSTEM_IP docker compose -f system3-compose.yml up -d"
echo "  # For System 1/2 nodes (set REDIS_HOST to System 3's private IP):"
echo "    REDIS_HOST=<system3_private_ip> docker compose -f system1-compose.yml up -d"
