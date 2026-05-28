"""
Alert Engine - detect anomaly conditions from MongoDB logs.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

from mongo_handler import get_stats_by_service, get_recent_errors
from datetime import datetime, timezone


def get_active_alerts() -> list:
    alerts = []
    now    = datetime.now(timezone.utc).isoformat()

    try:
        services = get_stats_by_service()
        for svc in services:
            total  = svc.get("total", 0)
            errors = svc.get("errors", 0)
            if total < 5:
                continue
            rate = errors / total * 100
            if rate > 50:
                alerts.append({
                    "severity":  "CRITICAL",
                    "service":   svc["_id"],
                    "message":   f"Error rate {rate:.1f}% — {errors}/{total} requests failed",
                    "timestamp": now,
                })
            elif rate > 20:
                alerts.append({
                    "severity":  "WARNING",
                    "service":   svc["_id"],
                    "message":   f"Elevated error rate {rate:.1f}%",
                    "timestamp": now,
                })
    except Exception:
        pass

    try:
        recent_errors = get_recent_errors(limit=5)
        if len(recent_errors) >= 5:
            alerts.append({
                "severity":  "WARNING",
                "service":   "cluster",
                "message":   "High error frequency detected in last 20 logs",
                "timestamp": now,
            })
    except Exception:
        pass

    return alerts
