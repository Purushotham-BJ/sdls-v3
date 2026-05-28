"""
Central Logging Service Routes
Ingest logs → Redis queue, query MongoDB, analytics, alerts, retention.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

from flask import Blueprint, request, jsonify, current_app
from mongo_handler import (
    insert_log, get_logs, get_logs_by_trace, get_retention_stats
)
from analytics   import get_overview, get_service_breakdown, get_timeline, get_trace_summary
from alert_engine import get_active_alerts
from constants import REDIS_LOG_QUEUE, REDIS_HOST, REDIS_PORT

try:
    import redis as redis_lib
    _rc = redis_lib.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0,
                          socket_connect_timeout=2, socket_timeout=2,
                          decode_responses=True)
    _rc.ping()
    REDIS_OK = True
except Exception:
    _rc = None
    REDIS_OK = False

log_bp = Blueprint("logs", __name__)


# ── Ingest ───────────────────────────────────────────────────────────────────

@log_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"service": "logging-service", "status": "healthy",
                    "redis": REDIS_OK}), 200


@log_bp.route("/api/logs", methods=["POST"])
def ingest_log():
    """
    Receive a log entry from any service.
    Stores directly to MongoDB (Redis worker handles async path separately).
    Emits Socket.IO event for live dashboard.
    """
    doc = request.get_json(silent=True)
    if not doc:
        return jsonify({"success": False, "message": "Empty body"}), 400
    try:
        insert_log(doc)
        current_app.socketio.emit("new_log", doc)
        return jsonify({"success": True, "message": "Log stored"}), 201
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# ── Query ────────────────────────────────────────────────────────────────────

@log_bp.route("/api/logs", methods=["GET"])
def query_logs():
    service   = request.args.get("service")
    status    = request.args.get("status")
    trace_id  = request.args.get("trace_id")
    system_ip = request.args.get("system_ip")
    limit     = int(request.args.get("limit", 100))
    logs = get_logs(limit=limit, service=service, status=status,
                    trace_id=trace_id, system_ip=system_ip)
    return jsonify({"success": True, "count": len(logs), "logs": logs}), 200


@log_bp.route("/api/logs/trace/<trace_id>", methods=["GET"])
def trace_detail(trace_id):
    summary = get_trace_summary(trace_id)
    return jsonify({"success": True, "data": summary}), 200


# ── Analytics ────────────────────────────────────────────────────────────────

@log_bp.route("/api/analytics/overview", methods=["GET"])
def overview():
    try:
        return jsonify({"success": True, "data": get_overview()}), 200
    except Exception as e:
        return jsonify({"success": False, "data": {
            "total_requests": 0, "total_errors": 0,
            "success_count": 0, "error_rate": 0, "active_services": 0
        }}), 200


@log_bp.route("/api/analytics/services", methods=["GET"])
def services():
    try:
        return jsonify({"success": True, "data": get_service_breakdown()}), 200
    except Exception as e:
        return jsonify({"success": False, "data": []}), 200


@log_bp.route("/api/analytics/timeline", methods=["GET"])
def timeline():
    hours = int(request.args.get("hours", 24))
    try:
        return jsonify({"success": True, "data": get_timeline(hours)}), 200
    except Exception as e:
        return jsonify({"success": False, "data": []}), 200


# ── Alerts ───────────────────────────────────────────────────────────────────

@log_bp.route("/api/alerts", methods=["GET"])
def alerts():
    try:
        data = get_active_alerts()
        return jsonify({"success": True, "count": len(data), "alerts": data}), 200
    except Exception as e:
        return jsonify({"success": False, "alerts": []}), 200


# ── Queue Monitoring ─────────────────────────────────────────────────────────

@log_bp.route("/api/queue/stats", methods=["GET"])
def queue_stats():
    if not REDIS_OK or not _rc:
        return jsonify({"success": False, "message": "Redis unavailable"}), 503
    try:
        raw = _rc.get("queue_stats")
        stats = json.loads(raw) if raw else {
            "queue_length": _rc.llen(REDIS_LOG_QUEUE),
            "dead_letter_count": _rc.llen("log_queue_dead"),
            "high_load": _rc.get("high_load") == "1",
        }
        return jsonify({"success": True, "data": stats}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# ── Retention ────────────────────────────────────────────────────────────────

@log_bp.route("/api/retention/stats", methods=["GET"])
def retention_stats():
    try:
        return jsonify({"success": True, "data": get_retention_stats()}), 200
    except Exception as e:
        return jsonify({"success": False, "data": []}), 200
