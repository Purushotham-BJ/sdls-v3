"""Order Service - Port 5001 (System 1: 192.168.1.10)"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from registry import register_self, start_heartbeat
from flask import Flask
from flask_cors import CORS
from order_routes import order_bp

app = Flask(__name__)
CORS(app)
app.register_blueprint(order_bp)

if __name__ == "__main__":
    register_self("order-service")
    start_heartbeat("order-service")
    print("📦 Order Service running on 0.0.0.0:5001")
    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)
