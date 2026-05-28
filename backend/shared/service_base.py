"""
Service Base — Role-Aware Startup with Redis Registry
======================================================
Every microservice calls init_service() on startup.  It:
  1. Registers the service in the Redis node registry
  2. Starts the background heartbeat
  3. Emits a startup log to the logging pipeline
  4. Wires graceful shutdown (SIGTERM / SIGINT)

Usage in any service app.py:
  from service_base import init_service
  init_service(app, "payment-service")
"""
import os, sys, signal, threading, time
sys.path.insert(0, os.path.dirname(__file__))

from registry import register_self, start_heartbeat, deregister
from constants import get_service_url, PORTS


def _graceful_exit(service_name: str, signum, frame):
    print(f"\n[{service_name}] Received signal {signum} — deregistering …")
    deregister(service_name)
    sys.exit(0)


def init_service(app, service_name: str, extra_meta: dict = None):
    """
    Call once after creating the Flask app object.
    Registers, starts heartbeat, wires SIGTERM handler.
    Returns (host, port) tuple.
    """
    # Wait a moment for Redis to be ready (retry up to 30 s)
    from registry import _get_redis
    for attempt in range(15):
        try:
            _get_redis().ping()
            break
        except Exception:
            if attempt == 0:
                print(f"[{service_name}] Waiting for Redis …")
            time.sleep(2)

    register_self(service_name, extra_meta)
    start_heartbeat(service_name)

    # Graceful shutdown
    signal.signal(signal.SIGTERM, lambda s, f: _graceful_exit(service_name, s, f))
    signal.signal(signal.SIGINT,  lambda s, f: _graceful_exit(service_name, s, f))

    host = "0.0.0.0"
    port = PORTS.get(service_name, 5000)

    print(f"[{service_name}] ✅ Initialized — listening on {host}:{port}")
    return host, port
