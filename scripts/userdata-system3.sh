#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# SDLS v3 — EC2 User-Data script for SYSTEM 3 (infra node)
# Paste this verbatim into "Advanced → User data" when launching the EC2.
# The instance will fully bootstrap itself on first boot — no SSH needed.
#
# BEFORE USING:
#   1. Upload sdls-v3.zip to an S3 bucket you own
#   2. Replace SDLS_S3_BUCKET below with your actual bucket name
#   3. Attach an IAM role to the EC2 with s3:GetObject on that bucket
#      (or swap the aws s3 cp line for scp / wget from a pre-signed URL)
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail
exec > /var/log/sdls-userdata.log 2>&1

SDLS_S3_BUCKET="YOUR-BUCKET-NAME"          # ← change this
DASHBOARD_PASSWORD="$(openssl rand -hex 12)"
SECRET_KEY="$(openssl rand -hex 32)"
PROJECT_DIR="/opt/sdls"

echo "=== SDLS v3 User-Data Bootstrap: System 3 ==="
echo "Started: $(date -u)"

# ── 1. System updates ─────────────────────────────────────────────────
apt-get update -q
apt-get upgrade -y -q --no-install-recommends

# ── 2. Docker Engine ──────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
  apt-get install -y -q ca-certificates curl gnupg unzip awscli
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

# ── 3. Detect private IP ──────────────────────────────────────────────
PRIVATE_IP=$(curl -sf --max-time 3 \
  http://169.254.169.254/latest/meta-data/local-ipv4 || hostname -I | awk '{print $1}')
echo "Private IP: $PRIVATE_IP"

# ── 4. Download project from S3 ───────────────────────────────────────
mkdir -p "$PROJECT_DIR"
aws s3 cp "s3://${SDLS_S3_BUCKET}/sdls-v3.zip" /tmp/sdls-v3.zip
unzip -q /tmp/sdls-v3.zip -d /tmp/sdls-extract
cp -r /tmp/sdls-extract/sdls-v3/. "$PROJECT_DIR/"
chmod +x "$PROJECT_DIR/scripts/"*.sh
chown -R ubuntu:ubuntu "$PROJECT_DIR"

# ── 5. Write .env ─────────────────────────────────────────────────────
cat > "$PROJECT_DIR/.env" << ENV
REDIS_HOST=redis
REDIS_PORT=6379
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=${DASHBOARD_PASSWORD}
SECRET_KEY=${SECRET_KEY}
SYSTEM_ROLE=system3
SYSTEM_IP=${PRIVATE_IP}
ENV

# Store credentials in AWS SSM Parameter Store for retrieval
REGION=$(curl -sf http://169.254.169.254/latest/meta-data/placement/region || echo "us-east-1")
aws ssm put-parameter \
  --name "/sdls/dashboard_password" \
  --value "$DASHBOARD_PASSWORD" \
  --type SecureString --overwrite \
  --region "$REGION" || true
aws ssm put-parameter \
  --name "/sdls/redis_host" \
  --value "$PRIVATE_IP" \
  --type String --overwrite \
  --region "$REGION" || true

# ── 6. Install + enable systemd service ──────────────────────────────
cp "$PROJECT_DIR/systemd/sdls-system3.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable sdls-system3
systemctl start sdls-system3

echo "=== Bootstrap complete: $(date -u) ==="
echo "Dashboard: http://${PRIVATE_IP}:5006"
echo "Dashboard password stored in SSM: /sdls/dashboard_password"
echo "Redis IP stored in SSM: /sdls/redis_host (Systems 1+2 will read this)"
