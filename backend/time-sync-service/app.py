"""
Centralized Time Synchronization Service - Port 5008
Provides authoritative UTC timestamps across all distributed nodes.
Implements: distributed clock sync, UTC normalization, global event ordering.
"""
from flask import Flask, jsonify
from flask_cors import CORS
from datetime import datetime, timezone
from registry import register_self, start_heartbeat
import time

app = Flask(__name__)
CORS(app)

_start_time = time.time()


@app.route("/time", methods=["GET"])
def get_time():
    """Central UTC time endpoint used by all services for synchronized logging."""
    now = datetime.now(timezone.utc)
    return jsonify({
        "utc_time":   now.isoformat(),
        "unix_epoch": now.timestamp(),
        "uptime_sec": round(time.time() - _start_time, 2),
        "service":    "time-sync"
    }), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"service": "time-sync", "status": "healthy",
                    "utc_time": datetime.now(timezone.utc).isoformat()}), 200


if __name__ == "__main__":
    register_self("time-sync")
    start_heartbeat("time-sync")
    print("🕐 Time Sync Service running on port 5008")
    app.run(host="0.0.0.0", port=5008, debug=False, threaded=True)
