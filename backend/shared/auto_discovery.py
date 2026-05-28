"""
Auto IP Discovery Service
=========================
Each machine runs this on startup. It:
  1. Detects its own LAN IP automatically
  2. Broadcasts its presence + role via UDP multicast
  3. Listens for other nodes broadcasting their IPs
  4. Once all 3 systems are discovered, writes a resolved .env file
  5. Notifies all services to reload their config

No manual IP editing required. Works over LAN/WiFi.

Usage:
  python auto_discovery.py --role system1   # on System 1
  python auto_discovery.py --role system2   # on System 2
  python auto_discovery.py --role system3   # on System 3
"""

import socket
import threading
import json
import time
import os
import sys
import argparse
import subprocess
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────────────────
DISCOVERY_PORT    = 47777          # UDP port used for peer discovery broadcasts
MULTICAST_GROUP   = "224.0.0.251"  # Link-local multicast (same as mDNS)
BROADCAST_INTERVAL = 3             # seconds between broadcasts
DISCOVERY_TIMEOUT  = 60            # seconds to wait for all peers
ENV_OUTPUT_PATH    = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
RESOLVED_ENV_PATH  = os.path.join(os.path.dirname(__file__), "..", "..", ".env.resolved")

VALID_ROLES = {"system1", "system2", "system3"}

# ── Discovered peers (thread-safe) ───────────────────────────────────────────
_peers = {}          # role → ip
_peers_lock = threading.Lock()
_discovery_done = threading.Event()


# ── IP Detection ──────────────────────────────────────────────────────────────

def get_local_lan_ip() -> str:
    """
    Reliably detect the machine's LAN IP (not 127.0.0.1).
    Uses a UDP connect trick — no packet is actually sent.
    Falls back through multiple strategies.
    """
    # Strategy 1: UDP connect trick (most reliable)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if not ip.startswith("127."):
            return ip
    except Exception:
        pass

    # Strategy 2: hostname resolution
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if not ip.startswith("127."):
            return ip
    except Exception:
        pass

    # Strategy 3: scan network interfaces
    try:
        import netifaces
        for iface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(iface)
            if netifaces.AF_INET in addrs:
                for addr in addrs[netifaces.AF_INET]:
                    ip = addr.get("addr", "")
                    if ip and not ip.startswith("127.") and not ip.startswith("169."):
                        return ip
    except ImportError:
        pass

    # Strategy 4: parse `ip addr` output (Linux)
    try:
        result = subprocess.run(
            ["ip", "-4", "addr", "show"], capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("inet ") and "127." not in line and "scope host" not in line:
                ip = line.split()[1].split("/")[0]
                return ip
    except Exception:
        pass

    return "127.0.0.1"  # last resort


# ── UDP Broadcaster ───────────────────────────────────────────────────────────

def broadcaster_loop(my_role: str, my_ip: str):
    """
    Continuously broadcast this node's role + IP via UDP multicast
    so other nodes can discover us.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

    payload = json.dumps({
        "role":      my_role,
        "ip":        my_ip,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version":   "sdls-v2",
    }).encode()

    print(f"[Discovery] Broadcasting {my_role} @ {my_ip} every {BROADCAST_INTERVAL}s ...")

    while not _discovery_done.is_set():
        try:
            sock.sendto(payload, (MULTICAST_GROUP, DISCOVERY_PORT))
        except Exception as e:
            # Fallback: use subnet broadcast if multicast fails
            try:
                sock2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock2.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock2.sendto(payload, ("<broadcast>", DISCOVERY_PORT))
                sock2.close()
            except Exception:
                pass
        time.sleep(BROADCAST_INTERVAL)

    sock.close()


# ── UDP Listener ──────────────────────────────────────────────────────────────

def listener_loop(my_role: str):
    """
    Listen for UDP broadcasts from peer nodes.
    Records their role → IP mapping.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except AttributeError:
        pass  # not available on Windows

    sock.bind(("", DISCOVERY_PORT))
    sock.settimeout(2.0)

    # Join multicast group
    try:
        mreq = socket.inet_aton(MULTICAST_GROUP) + socket.inet_aton("0.0.0.0")
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    except Exception:
        pass  # UDP broadcast fallback still works

    print(f"[Discovery] Listening on port {DISCOVERY_PORT} for peer broadcasts ...")

    while not _discovery_done.is_set():
        try:
            data, addr = sock.recvfrom(1024)
            msg = json.loads(data.decode())

            if msg.get("version") != "sdls-v2":
                continue

            role = msg.get("role")
            ip   = msg.get("ip")

            if role not in VALID_ROLES or not ip:
                continue

            with _peers_lock:
                if _peers.get(role) != ip:
                    print(f"[Discovery] ✅ Discovered {role} @ {ip}")
                    _peers[role] = ip
                    _check_all_discovered()

        except socket.timeout:
            continue
        except json.JSONDecodeError:
            continue
        except Exception as e:
            print(f"[Discovery] Listener error: {e}")

    sock.close()


def _check_all_discovered():
    """Called (under lock) when a new peer is recorded. Sets event if all 3 found."""
    if all(r in _peers for r in VALID_ROLES):
        print("\n[Discovery] 🎉 All 3 systems discovered!")
        _discovery_done.set()


# ── Config Writer ─────────────────────────────────────────────────────────────

def write_resolved_env(peers: dict):
    """
    Write a .env.resolved file with the discovered IPs.
    All services load this on startup.
    """
    sys1 = peers.get("system1", "127.0.0.1")
    sys2 = peers.get("system2", "127.0.0.1")
    sys3 = peers.get("system3", "127.0.0.1")

    content = f"""# AUTO-GENERATED by auto_discovery.py — DO NOT EDIT MANUALLY
# Generated at: {datetime.now(timezone.utc).isoformat()} UTC

SYSTEM_1_IP={sys1}
SYSTEM_2_IP={sys2}
SYSTEM_3_IP={sys3}

MONGO_URI=mongodb://{sys3}:27017
REDIS_HOST={sys3}
REDIS_PORT=6379

# Service URLs
API_GATEWAY_URL=http://{sys1}:5000
ORDER_SERVICE_URL=http://{sys1}:5001
PAYMENT_SERVICE_URL=http://{sys2}:5002
INVENTORY_SERVICE_URL=http://{sys2}:5003
NOTIFICATION_SERVICE_URL=http://{sys3}:5004
LOGGING_SERVICE_URL=http://{sys3}:5005
DASHBOARD_URL=http://{sys3}:5006
COORDINATOR_URL=http://{sys3}:5007
TIME_SYNC_URL=http://{sys3}:5008
BACKUP_PAYMENT_URL=http://{sys2}:5009
BACKUP_LOGGING_URL=http://{sys3}:5010

DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=admin123
SECRET_KEY=distributed-secret-key-change-in-production
"""

    # Write to project root
    project_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..")
    )
    env_path = os.path.join(project_root, ".env.resolved")
    with open(env_path, "w") as f:
        f.write(content)

    print(f"\n[Discovery] 📝 Written: {env_path}")
    print(f"  SYSTEM_1_IP = {sys1}")
    print(f"  SYSTEM_2_IP = {sys2}")
    print(f"  SYSTEM_3_IP = {sys3}")
    return env_path


def patch_constants_py(peers: dict):
    """
    Patch backend/shared/constants.py in-place with discovered IPs.
    This makes the change persistent for non-Docker runs.
    """
    constants_path = os.path.join(
        os.path.dirname(__file__), "..", "shared", "constants.py"
    )
    if not os.path.exists(constants_path):
        print(f"[Discovery] ⚠ constants.py not found at {constants_path}")
        return

    with open(constants_path, "r") as f:
        content = f.read()

    import re
    for role, ip in peers.items():
        num = role.replace("system", "")
        pattern = rf'(SYSTEM_{num}_IP\s*=\s*os\.getenv\("[^"]+",\s*")[^"]*(")'
        replacement = rf'\g<1>{ip}\g<2>'
        content = re.sub(pattern, replacement, content)

    with open(constants_path, "w") as f:
        f.write(content)

    print(f"[Discovery] 📝 Patched constants.py with discovered IPs")


def patch_dashboard_templates(peers: dict):
    """
    Patch hardcoded IPs in all dashboard HTML/JS template files.
    """
    import re

    # Old placeholder IPs to replace
    OLD_IPS = {
        "system1": "192.168.1.10",
        "system2": "192.168.1.11",
        "system3": "192.168.1.12",
    }

    templates_dir = os.path.join(
        os.path.dirname(__file__), "..", "..", "frontend", "dashboard", "templates"
    )
    js_dir = os.path.join(
        os.path.dirname(__file__), "..", "..", "frontend", "dashboard", "static", "js"
    )

    dirs_to_patch = [templates_dir, js_dir]

    patched_files = 0
    for d in dirs_to_patch:
        if not os.path.isdir(d):
            continue
        for fname in os.listdir(d):
            if not (fname.endswith(".html") or fname.endswith(".js")):
                continue
            fpath = os.path.join(d, fname)
            with open(fpath, "r") as f:
                content = f.read()
            original = content
            for role, new_ip in peers.items():
                old_ip = OLD_IPS.get(role, "")
                if old_ip:
                    content = content.replace(old_ip, new_ip)
            if content != original:
                with open(fpath, "w") as f:
                    f.write(content)
                patched_files += 1

    print(f"[Discovery] 📝 Patched {patched_files} template/JS files with discovered IPs")


# ── Main ──────────────────────────────────────────────────────────────────────

def run_discovery(my_role: str, timeout: int = DISCOVERY_TIMEOUT) -> dict:
    """
    Full discovery flow. Returns dict of role → IP once all peers found.
    """
    my_ip = get_local_lan_ip()
    print(f"\n{'='*55}")
    print(f"  SDLS Auto IP Discovery")
    print(f"  This machine: {my_role} @ {my_ip}")
    print(f"{'='*55}\n")

    # Register ourselves immediately
    with _peers_lock:
        _peers[my_role] = my_ip
        _check_all_discovered()

    if _discovery_done.is_set():
        # All roles on one machine (dev mode)
        return dict(_peers)

    # Start broadcaster + listener threads
    broadcast_thread = threading.Thread(
        target=broadcaster_loop, args=(my_role, my_ip), daemon=True
    )
    listener_thread = threading.Thread(
        target=listener_loop, args=(my_role,), daemon=True
    )
    broadcast_thread.start()
    listener_thread.start()

    # Wait for all peers with progress indicator
    deadline = time.time() + timeout
    while not _discovery_done.is_set():
        remaining = int(deadline - time.time())
        if remaining <= 0:
            print(f"\n[Discovery] ⏰ Timeout after {timeout}s")
            break
        with _peers_lock:
            found  = list(_peers.keys())
            missing = [r for r in VALID_ROLES if r not in _peers]
        print(f"[Discovery] Found: {found}  |  Waiting for: {missing}  ({remaining}s left)", end="\r")
        time.sleep(1)

    _discovery_done.set()  # signal threads to stop

    with _peers_lock:
        result = dict(_peers)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="SDLS Auto IP Discovery — detects and configures LAN IPs automatically"
    )
    parser.add_argument(
        "--role",
        required=True,
        choices=list(VALID_ROLES),
        help="Role of THIS machine: system1, system2, or system3"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DISCOVERY_TIMEOUT,
        help=f"Seconds to wait for all peers (default: {DISCOVERY_TIMEOUT})"
    )
    parser.add_argument(
        "--patch-only",
        action="store_true",
        help="Skip discovery, just patch configs using existing .env.resolved"
    )
    args = parser.parse_args()

    if args.patch_only:
        # Re-apply patches from existing resolved env
        env_path = os.path.join(
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
            ".env.resolved"
        )
        if not os.path.exists(env_path):
            print("[Discovery] ❌ No .env.resolved found. Run without --patch-only first.")
            sys.exit(1)
        peers = {}
        with open(env_path) as f:
            for line in f:
                for i in range(1, 4):
                    if line.startswith(f"SYSTEM_{i}_IP="):
                        peers[f"system{i}"] = line.strip().split("=", 1)[1]
        patch_constants_py(peers)
        patch_dashboard_templates(peers)
        return

    # Run full discovery
    peers = run_discovery(args.role, args.timeout)

    if len(peers) < 3:
        missing = [r for r in VALID_ROLES if r not in peers]
        print(f"\n[Discovery] ⚠ Only found {len(peers)}/3 systems: {peers}")
        print(f"  Missing: {missing}")
        print(f"  Using discovered IPs anyway (missing ones default to 127.0.0.1)")
        for r in missing:
            peers[r] = "127.0.0.1"

    print(f"\n[Discovery] Final IP map:")
    for role, ip in sorted(peers.items()):
        print(f"   {role:10s} → {ip}")

    # Write resolved env
    write_resolved_env(peers)

    # Patch source files in-place
    patch_constants_py(peers)
    patch_dashboard_templates(peers)

    print("\n[Discovery] ✅ Configuration complete. You can now start services.")
    print(f"  System 3 first:  ./start_system3.sh")
    print(f"  Then System 2:   ./start_system2.sh")
    print(f"  Then System 1:   ./start_system1.sh")


if __name__ == "__main__":
    main()
