"""
Distributed Utils — Redis-based async log dispatch with live failover.
Services push logs into Redis queue instead of directly to MongoDB.
Updated for v3: uses get_service_url() for zero-hardcoded-IP routing.
"""
import time, json, os, sys, requests
sys.path.insert(0, os.path.dirname(__file__))

from constants import (
    REDIS_LOG_QUEUE, REDIS_HOST, REDIS_PORT,
    get_service_url,
)
from log_format import create_log

try:
    import redis as redis_lib
    _redis_client = redis_lib.Redis(
        host=REDIS_HOST, port=REDIS_PORT, db=0,
        socket_connect_timeout=2, socket_timeout=2, decode_responses=True
    )
    _redis_client.ping()
    REDIS_AVAILABLE = True
except Exception:
    _redis_client = None
    REDIS_AVAILABLE = False


def send_log(trace_id, service_name, status, message,
             response_time=0, extra=None):
    """
    Push log to Redis queue (async) or fall back to direct HTTP.
    Dual-path: Redis queue → background worker → MongoDB.
    """
    log_entry = create_log(trace_id, service_name, status, message,
                           response_time, extra)
    if REDIS_AVAILABLE and _redis_client:
        try:
            _redis_client.lpush(REDIS_LOG_QUEUE, json.dumps(log_entry))
            return log_entry
        except Exception:
            pass

    _http_log(log_entry)
    return log_entry


def _http_log(log_entry):
    """Send log via HTTP with automatic failover to backup logging service."""
    for svc in ["logging-service", "backup-logging"]:
        try:
            url = get_service_url(svc)
            requests.post(f"{url}/api/logs", json=log_entry, timeout=2)
            return
        except Exception:
            continue
    print(f"[LOG-FALLBACK] {json.dumps(log_entry)}")


def measure_time(func, *args, **kwargs):
    start = time.time()
    result = func(*args, **kwargs)
    elapsed = int((time.time() - start) * 1000)
    return result, elapsed


def success_response(data, message="OK", status_code=200):
    return {"success": True, "message": message, "data": data}, status_code


def error_response(message, status_code=500):
    return {"success": False, "message": message, "data": None}, status_code


def get_redis_client():
    return _redis_client if REDIS_AVAILABLE else None
