"""
API Gateway — Port 5000 (System 1)
v3: registers self, uses get_service_url() for dynamic routing.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from flask import Flask
from flask_cors import CORS
from registry import register_self, start_heartbeat

app = Flask(__name__)
CORS(app)

from routes import gateway_bp
app.register_blueprint(gateway_bp)

if __name__ == "__main__":
    register_self("api-gateway")
    start_heartbeat("api-gateway")
    print("⤇  API Gateway running on port 5000")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
