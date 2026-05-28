"""
Backup Payment Service - Port 5009 (System 2: 192.168.1.11)
Identical to primary payment service. Activated automatically by coordinator on primary failure.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from registry import register_self, start_heartbeat
from flask import Flask
from flask_cors import CORS

# Reuse payment_routes from primary
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'payment-service'))
from payment_routes import payment_bp

app = Flask(__name__)
CORS(app)
app.register_blueprint(payment_bp)

if __name__ == "__main__":
    register_self("backup-payment-service")
    start_heartbeat("backup-payment-service")
    print("💳 BACKUP Payment Service running on 0.0.0.0:5009")
    app.run(host="0.0.0.0", port=5009, debug=False, threaded=True)
