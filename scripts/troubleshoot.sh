#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# SDLS v3 — Troubleshooting & Diagnostics Script
# Run on any EC2 instance to get a full health picture.
# Usage: ./scripts/troubleshoot.sh
# ═══════════════════════════════════════════════════════════════════════════
set -uo pipefail

RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[0;33m'
BLU='\033[0;34m'; CYN='\033[0;36m'; RST='\033[0m'
BOLD='\033[1m'

pass() { echo -e "  ${GRN}✓${RST} $1"; }
fail() { echo -e "  ${RED}✗${RST} $1"; }
warn() { echo -e "  ${YLW}⚠${RST} $1"; }
info() { echo -e "  ${BLU}→${RST} $1"; }
section() { echo -e "\n${BOLD}${CYN}── $1 ──${RST}"; }

REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"
SYSTEM_ROLE="${SYSTEM_ROLE:-unknown}"
PRIVATE_IP=$(curl -sf --max-time 2 http://169.254.169.254/latest/meta-data/local-ipv4 \
             || hostname -I | awk '{print $1}')

echo -e "${BOLD}SDLS v3 — Diagnostics Report${RST}"
echo "Generated: $(date -u)"
echo "Hostname:  $(hostname)  |  Private IP: $PRIVATE_IP"
echo "Role:      $SYSTEM_ROLE  |  Redis Host: $REDIS_HOST:$REDIS_PORT"
echo "────────────────────────────────────────────"

# ── 1. Docker ──────────────────────────────────────────────────────────
section "Docker"
if command -v docker &>/dev/null; then
  pass "Docker installed: $(docker --version | cut -d' ' -f3 | tr -d ',')"
else
  fail "Docker NOT installed — run: ./scripts/ec2-setup.sh"
fi
if docker compose version &>/dev/null; then
  pass "Docker Compose: $(docker compose version --short)"
else
  fail "Docker Compose plugin NOT found"
fi
if docker info &>/dev/null; then
  pass "Docker daemon running"
else
  fail "Docker daemon NOT running — run: sudo systemctl start docker"
fi

# ── 2. Containers ──────────────────────────────────────────────────────
section "Containers"
RUNNING=$(docker ps --format '{{.Names}}' 2>/dev/null | grep sdls || true)
if [[ -z "$RUNNING" ]]; then
  fail "No SDLS containers running"
  info "Try: ./scripts/deploy.sh"
else
  while read -r name; do
    STATUS=$(docker inspect --format '{{.State.Status}}' "$name" 2>/dev/null || echo "unknown")
    [[ "$STATUS" == "running" ]] && pass "$name ($STATUS)" || fail "$name ($STATUS)"
  done <<< "$RUNNING"
fi

# ── 3. Redis ───────────────────────────────────────────────────────────
section "Redis ($REDIS_HOST:$REDIS_PORT)"
if docker exec sdls-redis redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping \
   2>/dev/null | grep -q PONG; then
  pass "Redis PONG received"
  # Queue depth
  QLEN=$(docker exec sdls-redis redis-cli LLEN sdls:log_queue 2>/dev/null || echo "?")
  info "Log queue depth: $QLEN"
  # Registry keys
  KEYS=$(docker exec sdls-redis redis-cli KEYS "sdls:registry:*" 2>/dev/null | wc -l || echo 0)
  info "Registered services: $KEYS / 11"
  if [[ "$KEYS" -lt 3 ]]; then
    warn "Low service count — some nodes may not have started yet"
  fi
elif command -v redis-cli &>/dev/null && redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
   ping 2>/dev/null | grep -q PONG; then
  pass "Redis PONG (via host redis-cli)"
else
  fail "Cannot reach Redis at $REDIS_HOST:$REDIS_PORT"
  info "Check: REDIS_HOST env var, Security Group port 6379, System 3 running"
fi

# ── 4. Service ports ───────────────────────────────────────────────────
section "Local Service Ports"
declare -A PORTS=(
  [5000]="api-gateway"    [5001]="order-service"
  [5002]="payment"        [5003]="inventory"
  [5004]="notification"   [5005]="logging"
  [5006]="dashboard"      [5007]="coordinator"
  [5008]="time-sync"      [5009]="backup-payment"
  [5010]="backup-logging"
)
for port in "${!PORTS[@]}"; do
  svc="${PORTS[$port]}"
  if ss -tlnp "sport = :$port" 2>/dev/null | grep -q LISTEN; then
    pass ":$port $svc — LISTENING"
  else
    # Only warn for services expected on this role
    case "$SYSTEM_ROLE" in
      system1) [[ "$port" =~ ^500[01]$ ]] && warn ":$port $svc — NOT listening" ;;
      system2) [[ "$port" =~ ^500[239]$ ]] && warn ":$port $svc — NOT listening" ;;
      system3) [[ "$port" =~ ^500[4-8]$|^5010$ ]] && warn ":$port $svc — NOT listening" ;;
    esac
  fi
done

# ── 5. HTTP health checks ──────────────────────────────────────────────
section "HTTP Health Endpoints"
for entry in "5007:coordinator" "5005:logging" "5006:dashboard"; do
  port="${entry%%:*}"; svc="${entry##*:}"
  CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 \
    "http://localhost:$port/health" 2>/dev/null || echo "ERR")
  [[ "$CODE" == "200" ]] && pass "/$svc/health → $CODE" \
    || info "/$svc/health → $CODE (may not run on this node)"
done

# ── 6. Disk + memory ──────────────────────────────────────────────────
section "Resources"
DISK_PCT=$(df -h / | awk 'NR==2{print $5}' | tr -d '%')
[[ "$DISK_PCT" -lt 80 ]] && pass "Disk: $DISK_PCT% used" \
  || warn "Disk: $DISK_PCT% used — consider pruning Docker images"
FREE_MB=$(free -m | awk 'NR==2{print $7}')
[[ "$FREE_MB" -gt 200 ]] && pass "Free RAM: ${FREE_MB}MB" \
  || warn "Low RAM: ${FREE_MB}MB free"

# ── 7. Network connectivity ────────────────────────────────────────────
section "Network"
if curl -sf --max-time 3 https://registry-1.docker.io >/dev/null; then
  pass "Docker Hub reachable (Internet OK)"
else
  fail "Cannot reach Docker Hub — check IGW / security group egress"
fi
if [[ "$REDIS_HOST" != "redis" ]]; then
  if ping -c1 -W2 "$REDIS_HOST" &>/dev/null; then
    pass "System 3 ($REDIS_HOST) reachable"
  else
    fail "Cannot ping System 3 at $REDIS_HOST — check VPC/SG"
  fi
fi

# ── 8. Recent errors ──────────────────────────────────────────────────
section "Recent Container Errors (last 20 lines each)"
for cname in $(docker ps --format '{{.Names}}' 2>/dev/null | grep sdls); do
  ERRS=$(docker logs "$cname" --tail 5 2>&1 | grep -i "error\|traceback\|exception" | head -3 || true)
  if [[ -n "$ERRS" ]]; then
    warn "$cname:"
    echo "$ERRS" | while read -r l; do echo "    $l"; done
  fi
done

echo -e "\n${BOLD}Diagnostics complete.${RST}"
echo "For live log stream: docker compose -f system${SYSTEM_ROLE#system}-compose.yml logs -f"
