#!/usr/bin/env bash
# EC2 User-Data for SYSTEM 1 (api-gateway, order-service)
# Reads REDIS_HOST from SSM Parameter Store set by System 3's bootstrap.
set -euo pipefail
exec > /var/log/sdls-userdata.log 2>&1

SDLS_S3_BUCKET="YOUR-BUCKET-NAME"          # ← change this
PROJECT_DIR="/opt/sdls"

echo "=== SDLS v3 User-Data: System 2 ==="
apt-get update -q
apt-get install -y -q ca-certificates curl gnupg unzip awscli

# Docker
if ! command -v docker &>/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | tee /etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-compose-plugin
  systemctl enable --now docker
fi
usermod -aG docker ubuntu

REGION=$(curl -sf http://169.254.169.254/latest/meta-data/placement/region || echo "us-east-1")
PRIVATE_IP=$(curl -sf http://169.254.169.254/latest/meta-data/local-ipv4 || hostname -I | awk '{print $1}')

# Wait for System 3 to register its Redis IP in SSM (retry up to 5 min)
REDIS_HOST=""
for i in $(seq 1 30); do
  REDIS_HOST=$(aws ssm get-parameter --name "/sdls/redis_host" \
    --region "$REGION" --query 'Parameter.Value' --output text 2>/dev/null || true)
  [[ -n "$REDIS_HOST" ]] && break
  echo "Waiting for System 3 Redis IP in SSM... ($i/30)"
  sleep 10
done
[[ -z "$REDIS_HOST" ]] && { echo "ERROR: Redis host not found in SSM after 5 min"; exit 1; }
echo "Redis host: $REDIS_HOST"

mkdir -p "$PROJECT_DIR"
aws s3 cp "s3://${SDLS_S3_BUCKET}/sdls-v3.zip" /tmp/sdls-v3.zip
unzip -q /tmp/sdls-v3.zip -d /tmp/sdls-extract
cp -r /tmp/sdls-extract/sdls-v3/. "$PROJECT_DIR/"
chmod +x "$PROJECT_DIR/scripts/"*.sh
chown -R ubuntu:ubuntu "$PROJECT_DIR"

cat > "$PROJECT_DIR/.env" << ENV
REDIS_HOST=${REDIS_HOST}
REDIS_PORT=6379
SYSTEM_ROLE=system2
SYSTEM_IP=${PRIVATE_IP}
ENV

cp "$PROJECT_DIR/systemd/sdls-system2.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable sdls-system2
systemctl start sdls-system2

echo "=== System 2 bootstrap complete: $(date -u) ==="
