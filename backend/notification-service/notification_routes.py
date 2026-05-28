import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

from flask import Blueprint, request, jsonify
from utils import send_log
from constants import STATUS_SUCCESS, STATUS_ERROR, STATUS_INFO

notification_bp = Blueprint("notification", __name__)


@notification_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"service": "notification-service", "status": "healthy"}), 200


@notification_bp.route("/api/notification/send", methods=["POST"])
def send_notification():
    data        = request.get_json(silent=True) or {}
    trace_id    = data.get("trace_id", "UNKNOWN")
    customer_id = data.get("customer_id", "CUST-0001")
    product_id  = data.get("product_id", "PROD-001")
    success     = data.get("success", True)
    reason      = data.get("reason", "")
    start       = time.time()

    if success:
        msg = f"Order confirmation sent to {customer_id} for {product_id}"
        status = STATUS_SUCCESS
    else:
        msg = f"Failure notification sent to {customer_id}: {reason}"
        status = STATUS_ERROR

    # Simulate notification latency
    time.sleep(0.02)
    elapsed = int((time.time() - start) * 1000)

    send_log(trace_id, "notification-service", status, msg, elapsed,
             {"customer_id": customer_id, "product_id": product_id})

    return jsonify({"success": True, "message": msg, "trace_id": trace_id}), 200
