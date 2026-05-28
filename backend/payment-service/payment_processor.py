import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
"""
Payment Processor - Simulates real payment processing with ~30% failure rate.
"""
import random
import time

FAILURE_RATE = 0.05  # 30% of payments will fail

FAILURE_REASONS = [
    "Insufficient funds",
    "Card declined by issuing bank",
    "Transaction limit exceeded",
    "Invalid card number",
    "Payment gateway timeout",
]

SUCCESS_MESSAGES = [
    "Payment authorized",
    "Transaction approved",
    "Payment completed via UPI",
    "Net banking transaction successful",
]


def process_payment(trace_id, product_id, quantity, customer_id):
    """
    Simulate payment processing.
    Returns (success: bool, message: str, response_time_ms: int, transaction_id: str|None)
    """
    start = time.time()

    # Simulate network latency
    time.sleep(random.uniform(0.05, 0.25))

    elapsed = int((time.time() - start) * 1000)

    if random.random() < FAILURE_RATE:
        reason = random.choice(FAILURE_REASONS)
        return False, reason, elapsed, None

    txn_id = f"TXN-{trace_id[:6]}-{random.randint(1000, 9999)}"
    msg    = random.choice(SUCCESS_MESSAGES)
    return True, msg, elapsed, txn_id
