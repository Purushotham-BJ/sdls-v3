"""
Redis Node Registry
===================
Each service calls register_self() on startup.  The coordinator and
dashboard read the registry to build the live topology map.

Key schema  (Redis hash):
  sdls:registry:<service>  →  {host, port, role, system, pid, started_at, version}

Heartbeat:
  Every 30 s each service refreshes its TTL.  If a service dies its key
  expires in 90 s and the coordinator marks it unreachable.
"""
import os, json, socket, threading, time
from datetime import datetime, timezone

try:
    import redis as redis_lib
    from constants import REDIS_HOST, REDIS_PORT, REDIS_REGISTRY_PFX, PORTS, ROLE_SERVICES
except ImportError:
    import sys; sys.path.insert(0, os.path.dirname(__file__))
    import redis as redis_lib
    from constants import REDIS_HOST, REDIS_PORT, REDIS_REGISTRY_PFX, PORTS, ROLE_SERVICES

REGISTRY_TTL   = 90   # seconds — service considered dead if not refreshed
HEARTBEAT_INTERVAL = 30  # seconds between TTL refreshes

_rc = None


def _get_redis():
    global _rc
    if _rc is None:
        _rc = redis_lib.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0,
                              socket_connect_timeout=2, decode_responses=True)
    return _rc


def _detect_own_host() -> str:
    """
    Detect private IP visible to other containers / EC2 instances.
    Uses the same UDP connect trick as auto_discovery.py.
    """
    # Env override (set by compose or EC2 user-data)
    explicit = os.getenv("SERVICE_HOST") or os.getenv("SYSTEM_IP")
    if explicit:
        return explicit
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if not ip.startswith("127."):
            return ip
    except Exception:
        pass
    return socket.gethostname()   # Docker: returns container hostname / ID


def _detect_role(service_name: str) -> str:
    for role, services in ROLE_SERVICES.items():
        if service_name in services:
            return role
    return "unknown"


def register_self(service_name: str, extra: dict = None) -> bool:
    """
    Write this service's presence to Redis with a TTL.
    Call once on startup; use start_heartbeat() for the background refresh.
    """
    host = _detect_own_host()
    port = PORTS.get(service_name, 0)
    payload = {
        "host":       host,
        "port":       port,
        "service":    service_name,
        "role":       _detect_role(service_name),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "pid":        os.getpid(),
        "version":    "v3",
    }
    if extra:
        payload.update(extra)
    try:
        rc = _get_redis()
        key = f"{REDIS_REGISTRY_PFX}{service_name}"
        rc.set(key, json.dumps(payload), ex=REGISTRY_TTL)
        print(f"[Registry] ✅ Registered {service_name} @ {host}:{port}")
        return True
    except Exception as e:
        print(f"[Registry] ⚠  Could not register {service_name}: {e}")
        return False


def refresh_ttl(service_name: str):
    """Refresh TTL without changing value — keeps the service alive in registry."""
    try:
        rc = _get_redis()
        rc.expire(f"{REDIS_REGISTRY_PFX}{service_name}", REGISTRY_TTL)
    except Exception:
        pass


def start_heartbeat(service_name: str):
    """Launch background thread that refreshes TTL every HEARTBEAT_INTERVAL seconds."""
    def _beat():
        while True:
            time.sleep(HEARTBEAT_INTERVAL)
            refresh_ttl(service_name)
    t = threading.Thread(target=_beat, daemon=True, name=f"hb-{service_name}")
    t.start()
    return t


def get_all_services() -> dict:
    """Return full registry snapshot: {service_name: {host, port, ...}}"""
    result = {}
    try:
        rc = _get_redis()
        pfx = REDIS_REGISTRY_PFX
        keys = rc.keys(f"{pfx}*")
        for k in keys:
            raw = rc.get(k)
            if raw:
                name = k[len(pfx):]
                try:
                    result[name] = json.loads(raw)
                except Exception:
                    pass
    except Exception as e:
        print(f"[Registry] get_all_services error: {e}")
    return result


def get_service(service_name: str) -> dict | None:
    """Return registration info for one service, or None if not registered."""
    try:
        rc = _get_redis()
        raw = rc.get(f"{REDIS_REGISTRY_PFX}{service_name}")
        return json.loads(raw) if raw else None
    except Exception:
        return None


def deregister(service_name: str):
    """Remove a service from the registry (called on graceful shutdown)."""
    try:
        _get_redis().delete(f"{REDIS_REGISTRY_PFX}{service_name}")
    except Exception:
        pass
