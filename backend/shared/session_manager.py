"""
Distributed Session Manager — Redis-backed, EC2-safe
30-min sliding TTL, duplicate-login prevention, cross-node validity.
v3: uses namespaced keys (sdls:session:<username>) for clean Redis hygiene.
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(__file__))
from constants import REDIS_HOST, REDIS_PORT, SESSION_TIMEOUT_MINUTES
from datetime import datetime, timezone

SESSION_TTL = SESSION_TIMEOUT_MINUTES * 60
_SESSION_PFX = "sdls:session:"

try:
    import redis as redis_lib
    _rc = redis_lib.Redis(host=REDIS_HOST, port=REDIS_PORT, db=1,
                          socket_connect_timeout=2, decode_responses=True)
    _rc.ping()
    REDIS_OK = True
except Exception:
    _rc = None
    REDIS_OK = False

_mem_sessions = {}   # fallback: {username: {payload, expires}}


def _key(username: str) -> str:
    return f"{_SESSION_PFX}{username}"


def create_session(username: str, session_token: str) -> bool:
    now = datetime.now(timezone.utc).isoformat()
    payload = json.dumps({
        "username": username, "token": session_token,
        "created_at": now, "last_seen": now,
    })
    if REDIS_OK and _rc:
        result = _rc.set(_key(username), payload, ex=SESSION_TTL, nx=True)
        return result is not None
    if username in _mem_sessions:
        return False
    _mem_sessions[username] = {"payload": payload, "expires": time.time() + SESSION_TTL}
    return True


def validate_session(username: str, session_token: str) -> bool:
    if REDIS_OK and _rc:
        raw = _rc.get(_key(username))
        if not raw:
            return False
        data = json.loads(raw)
        if data.get("token") != session_token:
            return False
        data["last_seen"] = datetime.now(timezone.utc).isoformat()
        _rc.set(_key(username), json.dumps(data), ex=SESSION_TTL)
        return True
    entry = _mem_sessions.get(username)
    if not entry or time.time() > entry["expires"]:
        _mem_sessions.pop(username, None)
        return False
    return json.loads(entry["payload"]).get("token") == session_token


def destroy_session(username: str):
    if REDIS_OK and _rc:
        _rc.delete(_key(username))
    else:
        _mem_sessions.pop(username, None)


def get_active_sessions() -> list:
    sessions = []
    if REDIS_OK and _rc:
        for k in _rc.keys(f"{_SESSION_PFX}*"):
            raw = _rc.get(k)
            if raw:
                d = json.loads(raw)
                sessions.append({
                    "username":   d.get("username"),
                    "created_at": d.get("created_at"),
                    "last_seen":  d.get("last_seen"),
                })
    else:
        now = time.time()
        for username, entry in list(_mem_sessions.items()):
            if now < entry["expires"]:
                d = json.loads(entry["payload"])
                sessions.append({"username": d.get("username"),
                                  "created_at": d.get("created_at"),
                                  "last_seen":  d.get("last_seen")})
            else:
                del _mem_sessions[username]
    return sessions
