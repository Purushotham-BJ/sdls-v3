"""
API Gateway - Port 5000 (System 1: 192.168.1.10)
Entry point for all client requests.
Features: circuit breaker, coordinator-aware routing, distributed tracing.
"""
import sys, os, time, requests, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

from flask import Blueprint, request, jsonify
from trace_generator import generate_trace_id
from utils import send_log
from constants import SERVICE_URLS, COORDINATOR_URL, STATUS_SUCCESS, STATUS_ERROR, STATUS_INFO, get_service_url

gateway_bp = Blueprint("gateway", __name__)

# ── Circuit Breaker State ─────────────────────────────────────────────────────
_cb_state    = {}   # service → {open, fail_count, open_until}
_cb_lock     = threading.Lock()
CB_THRESHOLD = 5
CB_TIMEOUT   = 30   # seconds


def _get_active_url(service_name: str) -> str:
    """Ask coordinator for active endpoint (handles failover transparently)."""
    try:
        r = requests.get(f"{COORDINATOR_URL}/api/cluster/endpoint/{service_name}", timeout=1)
        if r.status_code == 200:
            return r.json().get("url", SERVICE_URLS.get(service_name))
    except Exception:
        pass
    return get_service_url(service_name)


def _cb_check(service: str) -> bool:
    """Returns True if circuit is CLOSED (request allowed)."""
    with _cb_lock:
        state = _cb_state.get(service, {"open": False, "fail_count": 0, "open_until": 0})
        if state["open"] and time.time() < state["open_until"]:
            return False   # circuit open, reject
        if state["open"]:
            state["open"] = False   # half-open: allow one probe
        return True


def _cb_record_failure(service: str):
    with _cb_lock:
        state = _cb_state.get(service, {"open": False, "fail_count": 0, "open_until": 0})
        state["fail_count"] += 1
        if state["fail_count"] >= CB_THRESHOLD:
            state["open"]       = True
            state["open_until"] = time.time() + CB_TIMEOUT
            state["fail_count"] = 0
        _cb_state[service] = state


def _cb_record_success(service: str):
    with _cb_lock:
        _cb_state[service] = {"open": False, "fail_count": 0, "open_until": 0}


# ── Routes ────────────────────────────────────────────────────────────────────

@gateway_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"service": "api-gateway", "status": "healthy",
                    "system": os.getenv("SYSTEM_IP", "192.168.1.10")}), 200


@gateway_bp.route("/api/order", methods=["POST"])
def place_order():
    trace_id = generate_trace_id()
    start    = time.time()

    send_log(trace_id, "api-gateway", STATUS_INFO,
             "Incoming order request received", 0,
             {"endpoint": "/api/order", "method": "POST"})

    if not _cb_check("order-service"):
        send_log(trace_id, "api-gateway", STATUS_ERROR,
                 "Circuit breaker OPEN for order-service", 0)
        return jsonify({"success": False, "trace_id": trace_id,
                        "message": "Order service temporarily unavailable (circuit open)"}), 503

    payload = request.get_json(silent=True) or {}
    payload["trace_id"] = trace_id

    order_url = _get_active_url("order-service")
    try:
        resp    = requests.post(f"{order_url}/api/order/create", json=payload, timeout=40)
        elapsed = int((time.time() - start) * 1000)
        result  = resp.json()

        if resp.status_code == 200:
            _cb_record_success("order-service")
            send_log(trace_id, "api-gateway", STATUS_SUCCESS,
                     "Order pipeline completed successfully", elapsed)
        else:
            _cb_record_failure("order-service")
            send_log(trace_id, "api-gateway", STATUS_ERROR,
                     f"Order pipeline failed: {result.get('message', 'unknown')}", elapsed)

        return jsonify({**result, "trace_id": trace_id}), resp.status_code

    except requests.exceptions.ConnectionError:
        _cb_record_failure("order-service")
        elapsed = int((time.time() - start) * 1000)
        send_log(trace_id, "api-gateway", STATUS_ERROR, "Order service unreachable", elapsed)
        return jsonify({"success": False, "trace_id": trace_id,
                        "message": "Order service is unreachable"}), 503

    except Exception as e:
        _cb_record_failure("order-service")
        elapsed = int((time.time() - start) * 1000)
        send_log(trace_id, "api-gateway", STATUS_ERROR,
                 f"Unexpected gateway error: {str(e)}", elapsed)
        return jsonify({"success": False, "trace_id": trace_id, "message": str(e)}), 500


@gateway_bp.route("/api/simulate/bulk", methods=["POST"])
def bulk_simulate():
    data    = request.get_json(silent=True) or {}
    count   = int(data.get("count", 5))
    results = []
    order_url = _get_active_url("order-service")

    for i in range(count):
        trace_id = generate_trace_id()
        payload  = {
            "trace_id":    trace_id,
            "product_id":  f"PROD-{(i % 5) + 1:03d}",
            "quantity":    (i % 3) + 1,
            "customer_id": f"CUST-{(i % 10) + 1:04d}"
        }
        try:
            resp = requests.post(f"{order_url}/api/order/create",
                                 json=payload, timeout=40)
            results.append({"trace_id": trace_id, "status": resp.status_code})
        except Exception as e:
            results.append({"trace_id": trace_id, "status": "error", "detail": str(e)})

    return jsonify({"simulated": count, "results": results}), 200


@gateway_bp.route("/api/circuit-breaker/status", methods=["GET"])
def circuit_breaker_status():
    with _cb_lock:
        status = {s: {"open": v["open"], "fail_count": v["fail_count"]}
                  for s, v in _cb_state.items()}
    return jsonify({"success": True, "data": status}), 200
