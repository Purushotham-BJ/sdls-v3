"""
Log Format - Uses centralized UTC time sync service for synchronized timestamps.
"""
import sys, os, requests
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from constants import TIME_SYNC_URL

_time_sync_available = True


def get_synchronized_utc_time() -> str:
    """
    Fetch UTC time from centralized Time Sync Service.
    Falls back to local UTC if service unavailable.
    Implements distributed clock synchronization.
    """
    global _time_sync_available
    if _time_sync_available:
        try:
            resp = requests.get(f"{TIME_SYNC_URL}/time", timeout=1)
            if resp.status_code == 200:
                return resp.json().get("utc_time", _local_utc())
        except Exception:
            _time_sync_available = False  # cache failure to avoid repeated timeouts
    return _local_utc()


def _local_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_log(trace_id, service_name, status, message,
               response_time=0, extra=None, system_ip=None):
    """
    Create a structured log entry with synchronized UTC timestamp.
    """
    log = {
        "trace_id":      trace_id,
        "service_name":  service_name,
        "timestamp":     get_synchronized_utc_time(),
        "status":        status.upper(),
        "message":       message,
        "response_time": response_time,
        "system_ip":     system_ip or os.getenv("SYSTEM_IP", "unknown"),
    }
    if extra:
        log.update(extra)
    return log
