"""
Backup Logging Service - Port 5010 (System 3: 192.168.1.12)
Identical to primary logging service.
Activated automatically when primary fails (coordinator-driven failover).
Shares the same MongoDB collection so logs are not lost.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from registry import register_self, start_heartbeat
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'logging-service'))

from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO
from log_routes import log_bp

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
app.socketio = socketio
app.register_blueprint(log_bp)

if __name__ == "__main__":
    register_self("backup-logging")
    start_heartbeat("backup-logging")
    print("📋 BACKUP Logging Service running on 0.0.0.0:5010")
    socketio.run(app, host="0.0.0.0", port=5010, debug=False, allow_unsafe_werkzeug=True)
