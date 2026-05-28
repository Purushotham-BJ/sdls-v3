"""Payment Service - Port 5002 (System 2: 192.168.1.11)"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from registry import register_self, start_heartbeat
from flask import Flask
from flask_cors import CORS
from payment_routes import payment_bp

app = Flask(__name__)
CORS(app)
app.register_blueprint(payment_bp)

if __name__ == "__main__":
    register_self("payment-service")
    start_heartbeat("payment-service")
    print("💳 Payment Service running on 0.0.0.0:5002")
    app.run(host="0.0.0.0", port=5002, debug=False, threaded=True)
