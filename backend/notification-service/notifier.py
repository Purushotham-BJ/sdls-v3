import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
"""
Notification dispatch logic.
Simulates email/SMS/push delivery.
"""
import time, random

CHANNELS = ["email", "sms", "push"]

def dispatch(customer_id: str, message: str, success: bool) -> dict:
    channel = random.choice(CHANNELS)
    time.sleep(0.01)
    return {
        "channel":     channel,
        "customer_id": customer_id,
        "message":     message,
        "success":     success,
        "delivered":   True,
    }
