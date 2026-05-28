"""
Order Service - Port 5001 (System 1: 192.168.1.10)
Orchestrates: inventory check → payment → deduct → notify.
Priority level: 3
"""
import sys, os, time, requests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

from flask import Blueprint, request, jsonify
from utils import send_log
from constants import (
    SERVICE_URLS, COORDINATOR_URL,
    STATUS_SUCCESS, STATUS_ERROR, STATUS_INFO, STATUS_WARNING,
    SERVICE_PRIORITY
)

order_bp = Blueprint("order", __name__)

PAYMENT_URL      = SERVICE_URLS["payment-service"]
INVENTORY_URL    = SERVICE_URLS["inventory-service"]
NOTIFICATION_URL = SERVICE_URLS["notification-service"]


def _get_active_url(service_name: str) -> str:
    """Resolve active endpoint via coordinator (failover-aware)."""
    try:
        r = requests.get(f"{COORDINATOR_URL}/api/cluster/endpoint/{service_name}", timeout=1)
        if r.status_code == 200:
            return r.json().get("url", SERVICE_URLS[service_name])
    except Exception:
        pass
    return SERVICE_URLS[service_name]


def _is_paused(service_name: str) -> bool:
    """Check if a low-priority service is paused due to high system load."""
    try:
        r = requests.get(f"{COORDINATOR_URL}/api/cluster/priority", timeout=1)
        if r.status_code == 200:
            return service_name in r.json().get("paused_services", [])
    except Exception:
        pass
    return False


@order_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"service": "order-service", "status": "healthy",
                    "priority": SERVICE_PRIORITY.get("order-service", 3),
                    "system": os.getenv("SYSTEM_IP", "192.168.1.10")}), 200


@order_bp.route("/api/order/create", methods=["POST"])
def create_order():
    data        = request.get_json(silent=True) or {}
    trace_id    = data.get("trace_id", "UNKNOWN")
    product_id  = data.get("product_id", "PROD-001")
    quantity    = data.get("quantity", 1)
    customer_id = data.get("customer_id", "CUST-0001")
    start       = time.time()

    send_log(trace_id, "order-service", STATUS_INFO,
             f"Order received for product {product_id}, qty={quantity}",
             0, {"product_id": product_id, "quantity": quantity, "customer_id": customer_id})

    # ── Step 1: Check inventory ──────────────────────────────────────────────
    inv_url = _get_active_url("inventory-service")
    try:
        inv_resp = requests.post(
            f"{inv_url}/api/inventory/check",
            json={"trace_id": trace_id, "product_id": product_id, "quantity": quantity},
            timeout=10
        )
        inv_data = inv_resp.json()
        if not inv_data.get("success"):
            elapsed = int((time.time() - start) * 1000)
            send_log(trace_id, "order-service", STATUS_ERROR,
                     f"Inventory check failed: {inv_data.get('message')}", elapsed)
            return jsonify({"success": False, "trace_id": trace_id,
                            "message": inv_data.get("message", "Inventory check failed")}), 400
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        send_log(trace_id, "order-service", STATUS_ERROR,
                 f"Inventory service unreachable: {e}", elapsed)
        return jsonify({"success": False, "trace_id": trace_id,
                        "message": "Inventory service unavailable"}), 503

    send_log(trace_id, "order-service", STATUS_SUCCESS,
             "Inventory verified successfully", int((time.time() - start) * 1000))

    # ── Step 2: Process payment (priority 1 - always executes) ──────────────
    pay_url = _get_active_url("payment-service")
    try:
        pay_resp = requests.post(
            f"{pay_url}/api/payment/process",
            json={"trace_id": trace_id, "product_id": product_id,
                  "quantity": quantity, "customer_id": customer_id},
            timeout=10
        )
        pay_data = pay_resp.json()
        if not pay_data.get("success"):
            elapsed = int((time.time() - start) * 1000)
            send_log(trace_id, "order-service", STATUS_ERROR,
                     f"Payment failed: {pay_data.get('message')}", elapsed)
            _notify(trace_id, customer_id, product_id, success=False,
                    reason=pay_data.get("message", "Payment declined"))
            return jsonify({"success": False, "trace_id": trace_id,
                            "message": pay_data.get("message", "Payment failed")}), 402
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        send_log(trace_id, "order-service", STATUS_ERROR,
                 f"Payment service unreachable: {e}", elapsed)
        return jsonify({"success": False, "trace_id": trace_id,
                        "message": "Payment service unavailable"}), 503

    send_log(trace_id, "order-service", STATUS_SUCCESS,
             "Payment processed successfully", int((time.time() - start) * 1000))

    # ── Step 3: Deduct inventory ─────────────────────────────────────────────
    try:
        requests.post(
            f"{inv_url}/api/inventory/deduct",
            json={"trace_id": trace_id, "product_id": product_id, "quantity": quantity},
            timeout=10
        )
    except Exception as e:
        send_log(trace_id, "order-service", STATUS_WARNING,
                 f"Inventory deduction failed (non-critical): {e}", 0)

    # ── Step 4: Notify customer ──────────────────────────────────────────────
    _notify(trace_id, customer_id, product_id, success=True)

    elapsed = int((time.time() - start) * 1000)
    send_log(trace_id, "order-service", STATUS_SUCCESS,
             "Order completed successfully", elapsed,
             {"product_id": product_id, "customer_id": customer_id})

    return jsonify({
        "success":  True,
        "trace_id": trace_id,
        "message":  "Order placed successfully",
        "order_id": f"ORD-{trace_id[:8]}"
    }), 200


def _notify(trace_id, customer_id, product_id, success, reason=""):
    try:
        notif_url = _get_active_url("notification-service")
        requests.post(
            f"{notif_url}/api/notification/send",
            json={"trace_id": trace_id, "customer_id": customer_id,
                  "product_id": product_id, "success": success, "reason": reason},
            timeout=5
        )
    except Exception:
        pass
