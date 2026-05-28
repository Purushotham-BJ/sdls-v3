#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# SDLS v3 — Quick Status Check
# Queries Redis registry and reports all live services.
# ═══════════════════════════════════════════════════════════════════════
REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  SDLS v3 — Live Service Registry"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if command -v redis-cli &>/dev/null; then
  KEYS=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" KEYS "sdls:registry:*" 2>/dev/null)
  if [[ -z "$KEYS" ]]; then
    echo "⚠  No services registered in Redis at $REDIS_HOST:$REDIS_PORT"
    echo "   Is the system running? Try: ./scripts/deploy.sh"
    exit 0
  fi
  while read -r key; do
    name="${key#sdls:registry:}"
    val=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET "$key" 2>/dev/null)
    host=$(echo "$val" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('host','?'))" 2>/dev/null)
    port=$(echo "$val" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('port','?'))" 2>/dev/null)
    role=$(echo "$val" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('role','?'))" 2>/dev/null)
    printf "  %-28s  %-16s  :%-5s  [%s]\n" "$name" "$host" "$port" "$role"
  done <<< "$KEYS"
else
  # Fallback: curl the coordinator
  COORD_URL="${COORDINATOR_URL:-http://localhost:5007}"
  echo "  (redis-cli not found — querying coordinator at $COORD_URL)"
  curl -sf "$COORD_URL/api/cluster/registry" 2>/dev/null \
    | python3 -c "
import sys,json
d=json.load(sys.stdin).get('data',{})
for name,info in sorted(d.items()):
    print(f\"  {name:<28}  {info.get('host','?'):<16}  :{info.get('port','?'):<5}  [{info.get('role','?')}]\")
" 2>/dev/null || echo "  Could not reach coordinator"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
