"""
Payment Service Routes
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

from flask import Blueprint, request, jsonify
from utils import send_log
from constants import STATUS_SUCCESS, STATUS_ERROR, STATUS_INFO
from payment_processor import process_payment

payment_bp = Blueprint("payment", __name__)


@payment_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"service": "payment-service", "status": "healthy"}), 200


@payment_bp.route("/api/payment/process", methods=["POST"])
def process():
    data        = request.get_json(silent=True) or {}
    trace_id    = data.get("trace_id", "UNKNOWN")
    product_id  = data.get("product_id", "PROD-001")
    quantity    = data.get("quantity", 1)
    customer_id = data.get("customer_id", "CUST-0001")

    send_log(trace_id, "payment-service", STATUS_INFO,
             f"Processing payment for customer {customer_id}",
             0, {"product_id": product_id, "quantity": quantity})

    success, message, response_time, txn_id = process_payment(
        trace_id, product_id, quantity, customer_id
    )

    if success:
        send_log(trace_id, "payment-service", STATUS_SUCCESS,
                 message, response_time,
                 {"transaction_id": txn_id, "customer_id": customer_id})
        return jsonify({
            "success": True,
            "message": message,
            "transaction_id": txn_id,
            "trace_id": trace_id
        }), 200
    else:
        send_log(trace_id, "payment-service", STATUS_ERROR,
                 f"Payment failed: {message}", response_time,
                 {"customer_id": customer_id, "failure_reason": message})
        return jsonify({
            "success": False,
            "message": message,
            "transaction_id": None,
            "trace_id": trace_id
        }), 402
