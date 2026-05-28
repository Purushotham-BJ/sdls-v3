#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# SDLS v3 — Smart Deploy Script
# Auto-detects SYSTEM_ROLE, discovers private IP, picks correct compose.
# Usage:
#   SYSTEM_ROLE=system3 ./scripts/deploy.sh          # Run System 3 services
#   REDIS_HOST=10.0.1.5 SYSTEM_ROLE=system1 ./scripts/deploy.sh
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# ── Detect private IP ────────────────────────────────────────────────
PRIVATE_IP="${SYSTEM_IP:-}"
if [[ -z "$PRIVATE_IP" ]]; then
  PRIVATE_IP=$(curl -sf --max-time 2 http://169.254.169.254/latest/meta-data/local-ipv4 2>/dev/null || true)
fi
if [[ -z "$PRIVATE_IP" ]]; then
  PRIVATE_IP=$(python3 -c "import socket; s=socket.socket(); s.connect(('8.8.8.8',80)); print(s.getsockname()[0]); s.close()" 2>/dev/null || hostname -I | awk '{print $1}')
fi
echo "🌐 Private IP: $PRIVATE_IP"

# ── Determine role ────────────────────────────────────────────────────
ROLE="${SYSTEM_ROLE:-}"
if [[ -z "$ROLE" ]]; then
  echo "⚠  SYSTEM_ROLE not set. Options: system1 | system2 | system3"
  echo "   Defaulting to single-host mode (docker-compose.yml)."
  ROLE="single"
fi

case "$ROLE" in
  system3)
    COMPOSE_FILE="system3-compose.yml"
    export REDIS_HOST="${REDIS_HOST:-redis}"   # redis is local on sys3
    ;;
  system2)
    COMPOSE_FILE="system2-compose.yml"
    if [[ -z "${REDIS_HOST:-}" ]]; then
      echo "❌ REDIS_HOST must be set for System 2 (point to System 3 private IP)"
      exit 1
    fi
    ;;
  system1)
    COMPOSE_FILE="system1-compose.yml"
    if [[ -z "${REDIS_HOST:-}" ]]; then
      echo "❌ REDIS_HOST must be set for System 1 (point to System 3 private IP)"
      exit 1
    fi
    ;;
  single)
    COMPOSE_FILE="docker-compose.yml"
    export REDIS_HOST="redis"
    ;;
  *)
    echo "❌ Unknown SYSTEM_ROLE: $ROLE"
    exit 1
    ;;
esac

echo "🎯 Role: $ROLE | Compose: $COMPOSE_FILE | Redis: ${REDIS_HOST:-local}"

# ── Write .env.resolved for Python services ──────────────────────────
cat > .env.resolved << ENV
REDIS_HOST=${REDIS_HOST:-redis}
REDIS_PORT=${REDIS_PORT:-6379}
SYSTEM_IP=${PRIVATE_IP}
SYSTEM_ROLE=${ROLE}
ENV
echo "✅ .env.resolved written"

# ── Build and start ───────────────────────────────────────────────────
echo "🔨 Building images …"
docker compose -f "$COMPOSE_FILE" build --parallel

echo "🚀 Starting services …"
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans

echo ""
echo "✅ SDLS v3 deployed — Role: $ROLE"
docker compose -f "$COMPOSE_FILE" ps
