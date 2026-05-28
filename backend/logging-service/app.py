"""
Central Logging Service — Port 5005
Receives logs, pushes to Redis queue, emits Socket.IO events.
v3: registers self on startup, uses service_base init.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO
from registry import register_self, start_heartbeat

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
app.socketio = socketio

from log_routes import log_bp
app.register_blueprint(log_bp)

if __name__ == "__main__":
    register_self("logging-service")
    start_heartbeat("logging-service")
    print("📋 Central Logging Service running on port 5005")
    socketio.run(app, host="0.0.0.0", port=5005, debug=False, allow_unsafe_werkzeug=True)
