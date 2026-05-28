"""Notification Service - Port 5004 (System 3: 192.168.1.12)"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from registry import register_self, start_heartbeat
from flask import Flask
from flask_cors import CORS
from notification_routes import notification_bp

app = Flask(__name__)
CORS(app)
app.register_blueprint(notification_bp)

if __name__ == "__main__":
    register_self("notification-service")
    start_heartbeat("notification-service")
    print("🔔 Notification Service running on 0.0.0.0:5004")
    app.run(host="0.0.0.0", port=5004, debug=False, threaded=True)
