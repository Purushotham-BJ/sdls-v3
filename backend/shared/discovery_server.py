"""
Discovery HTTP Server - Port 47778
===================================
Lightweight REST companion to auto_discovery.py.
Each machine runs this so others can query its resolved IP map.

GET /whoami          → {"role": "system2", "ip": "10.0.0.5"}
GET /peers           → {"system1": "10.0.0.4", "system2": "10.0.0.5", ...}
GET /ready           → {"ready": true/false, "peers_found": 2}
POST /register       → register a peer manually: {"role": "system1", "ip": "10.0.0.4"}
"""

import sys, os, json, threading, time, argparse
sys.path.insert(0, os.path.dirname(__file__))

from http.server import HTTPServer, BaseHTTPRequestHandler
from auto_discovery import get_local_lan_ip, run_discovery, write_resolved_env, \
    patch_constants_py, patch_dashboard_templates, _peers, _peers_lock, VALID_ROLES

DISCOVERY_HTTP_PORT = 47778
_my_role = None
_my_ip   = None


class DiscoveryHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress default request logs

    def _json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/whoami":
            self._json({"role": _my_role, "ip": _my_ip})

        elif self.path == "/peers":
            with _peers_lock:
                self._json(dict(_peers))

        elif self.path == "/ready":
            with _peers_lock:
                count = len(_peers)
                ready = all(r in _peers for r in VALID_ROLES)
            self._json({"ready": ready, "peers_found": count, "total_needed": 3})

        elif self.path == "/health":
            self._json({"status": "ok", "service": "discovery"})

        else:
            self._json({"error": "Not found"}, 404)

    def do_POST(self):
        if self.path == "/register":
            length = int(self.headers.get("Content-Length", 0))
            body   = json.loads(self.rfile.read(length))
            role   = body.get("role")
            ip     = body.get("ip")
            if role in VALID_ROLES and ip:
                with _peers_lock:
                    _peers[role] = ip
                self._json({"registered": True, "role": role, "ip": ip})
            else:
                self._json({"error": "Invalid role or ip"}, 400)
        else:
            self._json({"error": "Not found"}, 404)


def start_http_server():
    server = HTTPServer(("0.0.0.0", DISCOVERY_HTTP_PORT), DiscoveryHandler)
    print(f"[DiscoveryHTTP] REST API on port {DISCOVERY_HTTP_PORT}")
    server.serve_forever()


def main():
    global _my_role, _my_ip

    parser = argparse.ArgumentParser()
    parser.add_argument("--role", required=True, choices=list(VALID_ROLES))
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    _my_role = args.role
    _my_ip   = get_local_lan_ip()

    # Start HTTP REST server in background
    http_thread = threading.Thread(target=start_http_server, daemon=True)
    http_thread.start()

    # Run UDP discovery
    peers = run_discovery(args.role, args.timeout)

    # Write configs
    write_resolved_env(peers)
    patch_constants_py(peers)
    patch_dashboard_templates(peers)

    print("\n[DiscoveryHTTP] Keeping REST server alive. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        print("\n[DiscoveryHTTP] Stopped.")


if __name__ == "__main__":
    main()
