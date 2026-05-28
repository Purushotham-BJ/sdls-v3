import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
"""
In-memory inventory for demo purposes.
In production this would use a database.
"""
import threading

_lock = threading.Lock()

# Default stock: product_id -> quantity
STOCK = {
    "PROD-001": 100,
    "PROD-002": 50,
    "PROD-003": 75,
    "PROD-004": 30,
    "PROD-005": 200,
}


def check_availability(product_id: str, quantity: int):
    """Returns (available: bool, stock: int)"""
    with _lock:
        stock = STOCK.get(product_id, 20)   # default 20 for unknown products
        return stock >= quantity, stock


def deduct_stock(product_id: str, quantity: int):
    """Deducts stock; returns (success: bool, remaining: int)"""
    with _lock:
        current = STOCK.get(product_id, 20)
        if current >= quantity:
            STOCK[product_id] = current - quantity
            return True, STOCK[product_id]
        return False, current


def get_all_stock():
    with _lock:
        return dict(STOCK)
