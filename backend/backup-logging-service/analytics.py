"""
Analytics - aggregated metrics from MongoDB for dashboard.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

from mongo_handler import (
    get_total_count, get_error_count, get_stats_by_service,
    get_hourly_counts, get_logs_by_trace
)


def get_overview() -> dict:
    total   = get_total_count()
    errors  = get_error_count()
    success = max(0, total - errors)
    rate    = round((errors / total * 100), 1) if total else 0
    svcs    = get_stats_by_service()
    return {
        "total_requests":  total,
        "total_errors":    errors,
        "success_count":   success,
        "error_rate":      rate,
        "active_services": len(svcs),
    }


def get_service_breakdown() -> list:
    return get_stats_by_service()


def get_timeline(hours: int = 24) -> list:
    return get_hourly_counts(hours)


def get_trace_summary(trace_id: str) -> dict:
    logs     = get_logs_by_trace(trace_id)
    services = list(dict.fromkeys(l.get("service_name", "") for l in logs))
    statuses = [l.get("status", "") for l in logs]
    return {
        "trace_id":   trace_id,
        "total_logs": len(logs),
        "services":   services,
        "status":     "ERROR" if "ERROR" in statuses else "SUCCESS",
        "logs":       logs,
    }
