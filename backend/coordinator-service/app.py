"""
Master Coordinator Service — Port 5007
Central brain: health monitoring, failover, priority scheduling, topology pub.
v3: reads live registry from Redis, publishes topology snapshot every 10 s.
"""
import sys, os, time, json, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS
from constants import (SERVICE_PRIORITY, REDIS_HOST, REDIS_PORT,
                        REDIS_TOPOLOGY_KEY, FAILOVER_MAP, get_service_url, PORTS)
from registry import get_all_services, register_self, start_heartbeat
from datetime import datetime, timezone

app = Flask(__name__)
CORS(app)

_cluster_state = {
    "services": {},
    "failovers": [],
    "high_load": False,
    "updated_at": None,
}
_lock = threading.Lock()
_active_endpoints = {}   # service → current active URL (may be failover)

try:
    import redis as redis_lib
    _rc = redis_lib.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0,
                          socket_connect_timeout=2, decode_responses=True)
    _rc.ping()
    REDIS_OK = True
except Exception:
    _rc = None
    REDIS_OK = False


def check_service_health(name: str, url: str) -> dict:
    try:
        resp = requests.get(f"{url}/health", timeout=3)
        if resp.status_code == 200:
            return {"status": "healthy",
                    "response_time": resp.elapsed.total_seconds() * 1000}
    except Exception:
        pass
    return {"status": "unreachable", "response_time": None}


def health_monitor_loop():
    """Poll all registered (and known) services every 10 s."""
    while True:
        now = datetime.now(timezone.utc).isoformat()
        # Merge static port map with live registry
        registry = get_all_services()
        service_map = {name: get_service_url(name) for name in PORTS}
        for svc_name, info in registry.items():
            service_map[svc_name] = f"http://{info['host']}:{info['port']}"

        with _lock:
            for name, url in service_map.items():
                result = check_service_health(name, url)
                prev = _cluster_state["services"].get(name, {})
                fail_count = prev.get("fail_count", 0)
                primary_url = url

                if result["status"] == "healthy":
                    fail_count = 0
                    if name in FAILOVER_MAP and _active_endpoints.get(name) != primary_url:
                        _active_endpoints[name] = primary_url
                        _cluster_state["failovers"].append({
                            "event": "restored", "service": name,
                            "restored_to": primary_url, "timestamp": now,
                        })
                else:
                    fail_count += 1
                    if fail_count >= 3 and name in FAILOVER_MAP:
                        backup_name = FAILOVER_MAP[name]
                        backup_url = get_service_url(backup_name)
                        if backup_url and _active_endpoints.get(name) != backup_url:
                            _active_endpoints[name] = backup_url
                            _cluster_state["failovers"].append({
                                "event": "failover", "service": name,
                                "switched_to": backup_url, "timestamp": now,
                            })

                _cluster_state["services"][name] = {
                    "status":        result["status"],
                    "last_seen":     now if result["status"] == "healthy" else prev.get("last_seen"),
                    "host":          url.split("//")[1].split(":")[0],
                    "port":          PORTS.get(name),
                    "priority":      SERVICE_PRIORITY.get(name, 99),
                    "fail_count":    fail_count,
                    "response_time": result.get("response_time"),
                    "active_url":    _active_endpoints.get(name, url),
                    "registry_info": registry.get(name),
                }

            if REDIS_OK and _rc:
                try:
                    q_len = _rc.llen("sdls:log_queue")
                    _cluster_state["high_load"] = q_len > 5000
                except Exception:
                    pass

            _cluster_state["updated_at"] = now

            if REDIS_OK and _rc:
                try:
                    _rc.set("cluster_state", json.dumps(_cluster_state), ex=60)
                    # Publish full topology for dashboard
                    topology = {
                        "nodes": [
                            {
                                "id": name,
                                "host": info.get("host"),
                                "port": info.get("port"),
                                "status": info.get("status"),
                                "role": info.get("registry_info", {}).get("role") if info.get("registry_info") else None,
                            }
                            for name, info in _cluster_state["services"].items()
                        ],
                        "updated_at": now,
                    }
                    _rc.set(REDIS_TOPOLOGY_KEY, json.dumps(topology), ex=30)
                except Exception:
                    pass

        time.sleep(10)


def get_paused_services() -> list:
    if not _cluster_state["high_load"]:
        return []
    return [name for name, p in SERVICE_PRIORITY.items() if p >= 4]


@app.route("/health")
def health():
    return jsonify({"service": "coordinator", "status": "healthy"}), 200


@app.route("/api/cluster/state")
def cluster_state():
    with _lock:
        state = dict(_cluster_state)
    state["paused_services"] = get_paused_services()
    state["active_endpoints"] = _active_endpoints
    return jsonify({"success": True, "data": state}), 200


@app.route("/api/cluster/services")
def service_list():
    with _lock:
        services = dict(_cluster_state["services"])
    return jsonify({"success": True, "data": services}), 200

@app.route("/api/cluster/registry")
def registry_snapshot():
    with _lock:
        services = dict(_cluster_state["services"])

    return jsonify({
        "success": True,
        "data": services
    }), 200

@app.route("/api/cluster/register", methods=["POST"])
def register_service():
    from flask import request

    data = request.json or {}

    service_name = data.get("service_name")
    url = data.get("url")

    if not service_name or not url:
        return jsonify({
            "success": False,
            "error": "Missing service_name or url"
        }), 400

    try:
        with _lock:
            _cluster_state["services"][service_name] = {
                "url": url,
                "registered_at": datetime.utcnow().isoformat()
            }

        print(f"[Registry] Registered {service_name} -> {url}")

        return jsonify({"success": True}), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/cluster/failovers")
def failover_history():
    with _lock:
        events = list(_cluster_state["failovers"][-20:])
    return jsonify({"success": True, "data": events}), 200


@app.route("/api/cluster/priority")
def priority_state():
    return jsonify({
        "success": True,
        "high_load": _cluster_state["high_load"],
        "priorities": SERVICE_PRIORITY,
        "paused_services": get_paused_services(),
    }), 200


@app.route("/api/cluster/endpoint/<service_name>")
def active_endpoint(service_name):
    url = _active_endpoints.get(service_name) or get_service_url(service_name)
    if not url:
        return jsonify({"success": False, "message": "Unknown service"}), 404
    return jsonify({"success": True, "service": service_name, "url": url}), 200


@app.route("/api/cluster/topology")
def topology():
    """Full topology for the dashboard — merges registry + health state."""
    with _lock:
        services = dict(_cluster_state["services"])
    registry = get_all_services()
    nodes = []
    for name, info in services.items():
        reg = registry.get(name, {})
        nodes.append({
            "id":            name,
            "host":          reg.get("host") or info.get("host"),
            "port":          reg.get("port") or PORTS.get(name),
            "status":        info.get("status"),
            "role":          reg.get("role"),
            "response_time": info.get("response_time"),
            "fail_count":    info.get("fail_count", 0),
            "active_url":    info.get("active_url"),
            "started_at":    reg.get("started_at"),
        })
    return jsonify({"success": True, "data": {"nodes": nodes,
                    "updated_at": _cluster_state.get("updated_at")}}), 200


if __name__ == "__main__":
    register_self("coordinator")
    start_heartbeat("coordinator")
    monitor = threading.Thread(target=health_monitor_loop, daemon=True)
    monitor.start()
    print("🎛️  Coordinator Service running on port 5007")
    app.run(host="0.0.0.0", port=5007, debug=False, threaded=True)
