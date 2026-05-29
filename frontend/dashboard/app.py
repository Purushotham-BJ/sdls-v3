"""
Dashboard Frontend — Port 5006
v3: Redis node registry sidebar, theme support, dynamic service map,
    Socket.IO live feed, distributed session management.
"""
import sys, os, uuid, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'shared'))

from flask import (Flask, render_template, request, redirect,
                   url_for, session, jsonify, Response)
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

try:
    from session_manager import create_session, validate_session, destroy_session, get_active_sessions
    DISTRIBUTED_SESSIONS = True
except ImportError:
    DISTRIBUTED_SESSIONS = False

try:
    from registry import get_all_services, register_self, start_heartbeat
    from constants import REDIS_HOST, REDIS_PORT, REDIS_TOPOLOGY_KEY, get_service_url, PORTS
    HAS_REGISTRY = True
except ImportError:
    HAS_REGISTRY = False

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)
app.secret_key = os.getenv("SECRET_KEY", "sdls-v3-change-in-production")

USERNAME = os.getenv("DASHBOARD_USERNAME", "admin")
PASSWORD = os.getenv("DASHBOARD_PASSWORD", "admin123")


def is_logged_in() -> bool:
    if not session.get("logged_in"):
        return False
    if DISTRIBUTED_SESSIONS:
        token    = session.get("session_token")
        username = session.get("username")
        if not token or not username:
            return False
        return validate_session(username, token)
    return True


def _require_login(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not is_logged_in():
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == USERNAME and password == PASSWORD:
            token = str(uuid.uuid4())
            if DISTRIBUTED_SESSIONS:
                if not create_session(username, token):
                    error = "Session already active. Wait 30 min or ask admin to clear it."
                else:
                    session.update({"logged_in": True, "username": username, "session_token": token})
                    return redirect(url_for("index"))
            else:
                session.update({"logged_in": True, "username": username})
                return redirect(url_for("index"))
        else:
            error = "Invalid credentials"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    if DISTRIBUTED_SESSIONS and session.get("username"):
        destroy_session(session["username"])
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@app.route("/dashboard")
@_require_login
def index():
    return render_template("index.html", active="home")

@app.route("/logs")
@_require_login
def logs():
    return render_template("logs.html", active="logs")

@app.route("/analytics")
@_require_login
def analytics():
    return render_template("analytics.html", active="analytics")

@app.route("/errors")
@_require_login
def errors():
    return render_template("errors.html", active="errors")

@app.route("/topology")
@_require_login
def topology():
    return render_template("topology.html", active="topology")


# ── API Endpoints used by JS ──────────────────────────────────────────────────

@app.route("/api/sessions")
@_require_login
def sessions_api():
    if DISTRIBUTED_SESSIONS:
        return jsonify({"success": True, "sessions": get_active_sessions()})
    return jsonify({"success": True, "sessions": []})


@app.route("/api/registry")
@_require_login
def registry_api():
    """Live service registry snapshot for the sidebar and topology."""
    if HAS_REGISTRY:
        data = get_all_services()
        return jsonify({"success": True, "data": data})
    return jsonify({"success": False, "data": {}})


@app.route("/api/service-map")
@_require_login
def service_map():
    if HAS_REGISTRY:
        registry = get_all_services()
        svc_map = {}

        PUBLIC_IP = "98.93.32.45"

        for name in PORTS:
            info = registry.get(name)

            if info:
                if name in [
                    "logging-service",
                    "coordinator",
                    "dashboard",
                    "notification-service",
                    "time-sync",
                    "backup-logging"
                ]:
                    svc_map[name] = f"http://{PUBLIC_IP}:{info['port']}"
                else:
                    svc_map[name] = f"http://{info['host']}:{info['port']}"
            else:
                svc_map[name] = get_service_url(name)

        return jsonify({"success": True, "services": svc_map})

    return jsonify({"success": False, "services": {}})

@app.route("/health")
def health():
    return jsonify({"service": "dashboard", "status": "healthy"}), 200


@app.route("/favicon.ico")
def favicon():
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" rx="18" fill="#0f172a"/><polygon points="50,14 82,72 18,72" fill="#3b82f6" opacity=".9"/><circle cx="50" cy="28" r="6" fill="#ef4444"/></svg>'
    return Response(svg, mimetype="image/svg+xml")


if __name__ == "__main__":
    if HAS_REGISTRY:
        register_self("dashboard")
        start_heartbeat("dashboard")
    print("🖥️  Dashboard running on 0.0.0.0:5006")
    app.run(host="0.0.0.0", port=5006, debug=False, threaded=True)
