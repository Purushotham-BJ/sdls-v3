import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

from flask import Blueprint, request, jsonify
from utils import send_log
from constants import STATUS_SUCCESS, STATUS_ERROR, STATUS_INFO, STATUS_WARNING
from inventory_manager import check_availability, deduct_stock, get_all_stock

inventory_bp = Blueprint("inventory", __name__)


@inventory_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"service": "inventory-service", "status": "healthy"}), 200


@inventory_bp.route("/api/inventory/check", methods=["POST"])
def check():
    data       = request.get_json(silent=True) or {}
    trace_id   = data.get("trace_id", "UNKNOWN")
    product_id = data.get("product_id", "PROD-001")
    quantity   = int(data.get("quantity", 1))
    start      = time.time()

    send_log(trace_id, "inventory-service", STATUS_INFO,
             f"Checking stock for {product_id}, requested qty={quantity}")

    available, stock = check_availability(product_id, quantity)
    elapsed = int((time.time() - start) * 1000)

    if available:
        send_log(trace_id, "inventory-service", STATUS_SUCCESS,
                 f"Stock available: {stock} units of {product_id}", elapsed)
        return jsonify({"success": True, "message": f"Stock available ({stock} units)",
                        "stock": stock}), 200
    else:
        send_log(trace_id, "inventory-service", STATUS_ERROR,
                 f"Insufficient stock for {product_id}: need {quantity}, have {stock}", elapsed)
        return jsonify({"success": False,
                        "message": f"Insufficient stock: need {quantity}, have {stock}",
                        "stock": stock}), 400


@inventory_bp.route("/api/inventory/deduct", methods=["POST"])
def deduct():
    data       = request.get_json(silent=True) or {}
    trace_id   = data.get("trace_id", "UNKNOWN")
    product_id = data.get("product_id", "PROD-001")
    quantity   = int(data.get("quantity", 1))
    start      = time.time()

    success, remaining = deduct_stock(product_id, quantity)
    elapsed = int((time.time() - start) * 1000)

    if success:
        send_log(trace_id, "inventory-service", STATUS_SUCCESS,
                 f"Deducted {quantity} units of {product_id}, remaining={remaining}", elapsed)
        return jsonify({"success": True, "remaining": remaining}), 200
    else:
        send_log(trace_id, "inventory-service", STATUS_WARNING,
                 f"Could not deduct stock for {product_id}", elapsed)
        return jsonify({"success": False, "remaining": remaining}), 400


@inventory_bp.route("/api/inventory/stock", methods=["GET"])
def stock():
    return jsonify({"success": True, "stock": get_all_stock()}), 200
