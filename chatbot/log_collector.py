import json
import os
from pathlib import Path

LOG_DIR = Path(os.getenv("LOG_DIR", "/logs"))


def logs_for_trace(trace_id: str, limit: int = 40) -> list[str]:
    if not trace_id or trace_id == "unknown":
        return []
    matches: list[tuple[float, str]] = []
    if not LOG_DIR.exists():
        return []
    for log_file in LOG_DIR.rglob("*.log"):
        try:
            text = log_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            if trace_id not in line:
                continue
            matches.append((log_file.stat().st_mtime, line.strip()))
    matches.sort(key=lambda item: item[0])
    lines = [item[1] for item in matches][-limit:]
    pretty = []
    for line in lines:
        try:
            parsed = json.loads(line)
            pretty.append(json.dumps(parsed, indent=2))
        except json.JSONDecodeError:
            pretty.append(line)
    return pretty
