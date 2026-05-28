"""
Redis Log Worker - Background async persistence worker.
Drains log_queue from Redis and batch-writes to MongoDB.
Implements: eventual consistency, retry logic, batched writes, queue overflow protection.

Run independently on System 3 alongside logging-service.
"""
import sys, os, json, time, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

from constants import (
    REDIS_HOST, REDIS_PORT, REDIS_LOG_QUEUE,
    MONGO_URI, MONGO_DB, LOGS_COLLECTION
)

import redis
from pymongo import MongoClient, InsertOne
from pymongo.errors import BulkWriteError
from datetime import datetime, timezone

BATCH_SIZE        = 50      # flush when queue reaches this
FLUSH_INTERVAL    = 2.0     # or every N seconds
MAX_QUEUE_SIZE    = 10_000  # overflow protection threshold
MAX_RETRY_ATTEMPTS = 3

print(f"[Worker] Connecting to Redis {REDIS_HOST}:{REDIS_PORT} ...")
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0,
                decode_responses=True, socket_timeout=5)

print(f"[Worker] Connecting to MongoDB {MONGO_URI} ...")
mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = mongo_client[MONGO_DB]
col = db[LOGS_COLLECTION]

# Ensure TTL + search indexes
col.create_index("trace_id")
col.create_index("service_name")
col.create_index("status")
col.create_index("timestamp")
col.create_index("expire_at", expireAfterSeconds=0)  # TTL index


def compute_expire_at(status: str) -> str:
    from datetime import timedelta
    retention = {"INFO": 7, "SUCCESS": 7, "WARNING": 30, "ERROR": 90}
    days = retention.get(status.upper(), 7)
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def flush_batch(batch: list) -> bool:
    """Write a batch to MongoDB with retry logic."""
    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        try:
            ops = []
            for doc in batch:
                doc["expire_at"] = compute_expire_at(doc.get("status", "INFO"))
                ops.append(InsertOne(doc))
            col.bulk_write(ops, ordered=False)
            return True
        except BulkWriteError as bwe:
            print(f"[Worker] BulkWriteError attempt {attempt}: {bwe.details}")
            time.sleep(0.5 * attempt)
        except Exception as e:
            print(f"[Worker] MongoDB error attempt {attempt}: {e}")
            time.sleep(1.0 * attempt)
    # After retries failed: put back into dead-letter key
    for doc in batch:
        r.lpush("log_queue_dead", json.dumps(doc))
    print(f"[Worker] {len(batch)} logs moved to dead-letter queue")
    return False


def worker_loop():
    print("[Worker] Redis log worker started ✓")
    buffer = []
    last_flush = time.time()

    while True:
        # Overflow protection: pause analytics if queue is too large
        queue_len = r.llen(REDIS_LOG_QUEUE)
        if queue_len > MAX_QUEUE_SIZE:
            r.set("high_load", "1", ex=30)
            print(f"[Worker] ⚠ Queue overflow: {queue_len} items, pausing low-priority tasks")

        # Pop items from queue (non-blocking with timeout)
        item = r.brpop(REDIS_LOG_QUEUE, timeout=1)
        if item:
            _, raw = item
            try:
                doc = json.loads(raw)
                buffer.append(doc)
            except json.JSONDecodeError:
                pass

        # Flush on batch size or time interval
        should_flush = (
            len(buffer) >= BATCH_SIZE or
            (buffer and time.time() - last_flush >= FLUSH_INTERVAL)
        )
        if should_flush:
            print(f"[Worker] Flushing {len(buffer)} logs to MongoDB ...")
            flush_batch(buffer)
            buffer.clear()
            last_flush = time.time()


def queue_stats_reporter():
    """Periodically report queue stats to Redis for dashboard monitoring."""
    while True:
        try:
            stats = {
                "queue_length":      r.llen(REDIS_LOG_QUEUE),
                "dead_letter_count": r.llen("log_queue_dead"),
                "high_load":         r.get("high_load") == "1",
                "reported_at":       datetime.now(timezone.utc).isoformat(),
            }
            r.set("queue_stats", json.dumps(stats), ex=60)
        except Exception as e:
            print(f"[Worker] Stats reporter error: {e}")
        time.sleep(5)


if __name__ == "__main__":
    stats_thread = threading.Thread(target=queue_stats_reporter, daemon=True)
    stats_thread.start()
    worker_loop()
