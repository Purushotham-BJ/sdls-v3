import uuid
from datetime import datetime, timezone


def generate_trace_id() -> str:
    return str(uuid.uuid4()).replace("-", "")[:16].upper()


def generate_span_id() -> str:
    return str(uuid.uuid4()).replace("-", "")[:8].upper()


def get_current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
