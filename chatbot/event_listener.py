import json
import os
import threading
import time
from datetime import datetime, timezone

import redis

from display_flag import is_display_allowed
from log_collector import logs_for_trace

CHANNEL = os.getenv("FAILURE_CHANNEL", "system-failures")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
INCIDENT_KEY = "sre:incidents"

_started = False
_start_lock = threading.Lock()


def _client() -> redis.Redis:
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


NOISE_TYPES = {
    "NoResourceFoundException",
    "NoHandlerFoundException",
}
NOISE_SNIPPETS = (
    "favicon",
    "no static resource",
    "actuator/health",
    "actuator/info",
)


def list_incidents() -> list[dict]:
    try:
        raw_items = _client().lrange(INCIDENT_KEY, 0, 199)
    except Exception:
        return []
    seen_traces: set[str] = set()
    incidents: list[dict] = []
    for raw in raw_items:
        try:
            incident = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if _is_noise(incident):
            continue
        trace_id = incident.get("traceId") or incident.get("id")
        if not trace_id or trace_id in seen_traces:
            continue
        seen_traces.add(trace_id)
        incidents.append(incident)
    return incidents


def clear_incidents() -> None:
    try:
        _client().delete(INCIDENT_KEY)
    except Exception:
        pass


def _is_noise(incident: dict) -> bool:
    error_type = str(incident.get("errorType") or "")
    message = str(incident.get("message") or "").lower()
    if error_type in NOISE_TYPES:
        return True
    return any(snippet in message for snippet in NOISE_SNIPPETS)


def _build_incident(event: dict) -> dict:
    trace_id = event.get("traceId") or "unknown"
    logs = logs_for_trace(trace_id)
    stamp = event.get("timestamp") or datetime.now(timezone.utc).isoformat()
    service = event.get("serviceName") or "unknown"
    error_type = event.get("errorType") or "UnknownError"
    return {
        "id": trace_id,
        "receivedAt": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "logs": logs,
        "serviceName": service,
        "traceId": trace_id,
        "shortTrace": (trace_id or "????????")[:8],
        "errorType": error_type,
        "message": event.get("message") or "No message",
        "correlationId": event.get("correlationId") or "unknown",
        "timestamp": stamp,
    }


def _store(incident: dict) -> None:
    if _is_noise(incident):
        return
    client = _client()
    trace_id = incident.get("traceId")
    existing = client.lrange(INCIDENT_KEY, 0, 199)
    for raw in existing:
        try:
            previous = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if previous.get("traceId") == trace_id or previous.get("id") == incident.get("id"):
            return
    client.lpush(INCIDENT_KEY, json.dumps(incident))
    client.ltrim(INCIDENT_KEY, 0, 199)


def _listen() -> None:
    while True:
        try:
            pubsub = _client().pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(CHANNEL)
            for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                if not is_display_allowed():
                    continue
                raw = message.get("data") or ""
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    event = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "serviceName": "unknown",
                        "traceId": "unknown",
                        "correlationId": "unknown",
                        "errorType": "UnparseableEvent",
                        "message": str(raw)[:240],
                    }
                _store(_build_incident(event))
        except Exception:
            time.sleep(2)


def start_listener() -> None:
    global _started
    with _start_lock:
        if _started:
            return
        for thread in threading.enumerate():
            if thread.name == "failure-listener":
                _started = True
                return
        thread = threading.Thread(target=_listen, name="failure-listener", daemon=True)
        thread.start()
        _started = True
