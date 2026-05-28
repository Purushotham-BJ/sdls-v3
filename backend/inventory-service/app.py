"""Inventory Service - Port 5003 (System 2: 192.168.1.11)"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from registry import register_self, start_heartbeat
from flask import Flask
from flask_cors import CORS
from inventory_routes import inventory_bp

app = Flask(__name__)
CORS(app)
app.register_blueprint(inventory_bp)

if __name__ == "__main__":
    register_self("inventory-service")
    start_heartbeat("inventory-service")
    print("🏭 Inventory Service running on 0.0.0.0:5003")
    app.run(host="0.0.0.0", port=5003, debug=False, threaded=True)
