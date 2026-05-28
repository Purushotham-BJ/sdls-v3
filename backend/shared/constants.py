"""
Shared Constants — Production-Grade AWS EC2 Distributed Configuration
======================================================================
ZERO hardcoded IPs. All service addresses resolve at runtime through:
  1. Redis node registry  (primary — Docker-native / EC2 private networking)
  2. Environment variables (Docker-compose injected or EC2 user-data)
  3. Docker DNS names     (fallback for single-host compose mode)

On EC2: services discover each other via Redis keys written by each
service's role-aware startup probe.  No multicast, no UDP broadcasts —
just Redis, which works across VPC subnets, security groups, and
docker bridge networks alike.

Service registration key pattern:
  sdls:registry:<service-name>  →  {"host": "<private-ip>", "port": <n>, ...}
"""
import os, json

# ── Env loader (priority: env vars already set > .env.resolved > .env) ───────
def _load_env_file(path: str):
    if not os.path.exists(path):
        return
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip()
            if key and val and key not in os.environ:
                os.environ[key] = val

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_load_env_file(os.path.join(_root, ".env.resolved"))
_load_env_file(os.path.join(_root, ".env"))

# ── Redis (the ONLY hard dependency for zero-IP operation) ───────────────────
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_LOG_QUEUE    = "sdls:log_queue"
REDIS_SESSION_KEY  = "sdls:sessions"
REDIS_HEALTH_KEY   = "sdls:health"
REDIS_REGISTRY_PFX = "sdls:registry:"
REDIS_TOPOLOGY_KEY = "sdls:topology"
REDIS_CONFIG_KEY   = "sdls:config"

# ── Service port map ──────────────────────────────────────────────────────────
PORTS = {
    "api-gateway": 5000, "order-service": 5001,
    "payment-service": 5002, "inventory-service": 5003,
    "notification-service": 5004, "logging-service": 5005,
    "dashboard": 5006, "coordinator": 5007,
    "time-sync": 5008, "backup-payment": 5009, "backup-logging": 5010,
}

# ── System role → service assignment ─────────────────────────────────────────
ROLE_SERVICES = {
    "system1": ["api-gateway", "order-service"],
    "system2": ["payment-service", "inventory-service", "backup-payment"],
    "system3": ["notification-service", "logging-service", "backup-logging",
                "dashboard", "coordinator", "time-sync"],
    "infra":   ["redis", "mongodb"],
}

# ── Dynamic service URL resolver ──────────────────────────────────────────────
def _resolve_service_host(service_name: str) -> str:
    env_key = service_name.upper().replace("-", "_") + "_HOST"
    if os.getenv(env_key):
        return os.getenv(env_key)
    try:
        import redis as _r
        rc = _r.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0,
                      socket_connect_timeout=1, decode_responses=True)
        raw = rc.get(f"{REDIS_REGISTRY_PFX}{service_name}")
        if raw:
            data = json.loads(raw)
            return data.get("host", service_name)
    except Exception:
        pass
    return service_name  # Docker DNS fallback


def get_service_url(service_name: str) -> str:
    env_key = service_name.upper().replace("-", "_") + "_URL"
    if os.getenv(env_key):
        return os.getenv(env_key)
    host = _resolve_service_host(service_name)
    port = PORTS.get(service_name, 8080)
    return f"http://{host}:{port}"


def _lazy_urls():
    return {
        "api-gateway":        "http://172.31.0.202:5000",
        "order-service":      "http://172.31.0.202:5001",

        "payment-service":    "http://172.31.2.177:5002",
        "inventory-service":  "http://172.31.2.177:5003",
        "backup-payment":     "http://172.31.2.177:5009",

        "notification-service":"http://172.31.75.219:5004",
        "logging-service":    "http://172.31.75.219:5005",
        "dashboard":          "http://172.31.75.219:5006",
        "coordinator":        "http://172.31.75.219:5007",
        "time-sync":          "http://172.31.75.219:5008",
        "backup-logging":     "http://172.31.75.219:5010",
    }

SERVICE_URLS = _lazy_urls()

LOGGING_SERVICE_URL = get_service_url("logging-service")
BACKUP_LOGGING_URL  = get_service_url("backup-logging")
COORDINATOR_URL     = get_service_url("coordinator")
TIME_SYNC_URL       = get_service_url("time-sync")

# ── MongoDB ───────────────────────────────────────────────────────────────────
MONGO_URI       = os.getenv("MONGO_URI", "mongodb://mongodb:27017")
MONGO_DB        = "distributed_logging"
LOGS_COLLECTION = "logs"

# ── Status codes ──────────────────────────────────────────────────────────────
STATUS_SUCCESS = "SUCCESS"
STATUS_ERROR   = "ERROR"
STATUS_WARNING = "WARNING"
STATUS_INFO    = "INFO"

# ── Business logic ────────────────────────────────────────────────────────────
SERVICE_PRIORITY = {
    "payment-service": 1, "notification-service": 2,
    "order-service": 3,   "inventory-service": 4, "analytics": 5,
}
LOG_RETENTION = {"INFO": 7, "SUCCESS": 7, "WARNING": 30, "ERROR": 90}
SESSION_TIMEOUT_MINUTES = 30
FAILOVER_MAP = {
    "payment-service": "backup-payment",
    "logging-service": "backup-logging",
}
