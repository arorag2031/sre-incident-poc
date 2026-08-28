import os
from pathlib import Path

from log_collector import logs_for_trace

CODE_ROOTS = [
    Path(part)
    for part in os.getenv("CODE_ROOTS", "/code/service-a:/code/service-b").split(":")
    if part.strip()
]
MAX_CODE_CHARS = 90_000
MAX_LOG_CHARS = 12_000
SOURCE_GLOBS = ("**/*.java", "**/*.yml", "**/*.yaml", "**/*.xml")


def _with_line_numbers(text: str) -> str:
    lines = text.splitlines()
    width = max(4, len(str(len(lines))))
    return "\n".join(f"{index:>{width}}| {line}" for index, line in enumerate(lines, 1))


def _rel_path(root: Path, path: Path) -> str:
    try:
        inner = path.relative_to(root)
    except ValueError:
        inner = path.name
    return f"{root.name}/{inner.as_posix()}"


def _read_source_files() -> list[tuple[str, str]]:
    files: list[tuple[str, str]] = []
    seen: set[str] = set()
    for root in CODE_ROOTS:
        src = root / "src" if (root / "src").is_dir() else root
        if not src.exists():
            continue
        for pattern in SOURCE_GLOBS:
            for path in sorted(src.glob(pattern)):
                if not path.is_file():
                    continue
                if "target" in path.parts or "test" in path.parts:
                    continue
                rel = _rel_path(root if root.name.startswith("service-") else src, path)
                if root.name in {"service-a", "service-b"}:
                    try:
                        rel = f"{root.name}/{path.relative_to(root).as_posix()}"
                    except ValueError:
                        rel = f"{root.name}/{path.name}"
                if rel in seen:
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                seen.add(rel)
                files.append((rel, text))
    return files


def _score(path: str, source: str, needles: list[str]) -> int:
    blob = (path + "\n" + source).lower()
    score = 0
    for needle in needles:
        n = (needle or "").lower().strip()
        if n and n in blob:
            score += 4
    name = path.lower()
    if any(token in name for token in ("fail", "simulate", "exception", "crash")):
        score += 8
    if "controller" in name or "handler" in name:
        score += 3
    if name.endswith(".java"):
        score += 1
    return score


def code_bundle(incident: dict | None) -> str:
    files = _read_source_files()
    if not files:
        return "(No microservice source is mounted. Chatbot cannot read Java files.)"
    needles: list[str] = []
    if incident:
        message = str(incident.get("message") or "")
        needles.extend(
            [
                str(incident.get("errorType") or ""),
                str(incident.get("serviceName") or ""),
                message[:120],
                "NullPointerException",
                "toUpperCase",
                "loadCustomerProfile",
                "simulate-crash",
                "FailureController",
                "SimulateCrashController",
            ]
        )
    ranked = sorted(files, key=lambda item: _score(item[0], item[1], needles), reverse=True)
    chunks: list[str] = []
    used = 0
    for path, source in ranked:
        numbered = _with_line_numbers(source)
        piece = f"\n===== FILE: {path} =====\n{numbered}\n"
        if used + len(piece) > MAX_CODE_CHARS:
            remain = MAX_CODE_CHARS - used
            if remain > 500:
                chunks.append(piece[:remain] + "\n... [truncated]")
            break
        chunks.append(piece)
        used += len(piece)
    return "".join(chunks) if chunks else "(Source files were empty.)"


def log_bundle(incident: dict | None) -> str:
    if not incident:
        return "(No incident selected.)"
    trace_id = str(incident.get("traceId") or "")
    lines = logs_for_trace(trace_id, limit=60)
    if not lines:
        lines = incident.get("logs") or []
    text = "\n---\n".join(lines)
    if len(text) > MAX_LOG_CHARS:
        return text[-MAX_LOG_CHARS:]
    return text or "(No JSON log lines matched this traceId in ./logs.)"


def investigation_context(incident: dict | None) -> str:
    return (
        "Ground truth: numbered microservice source plus container JSON logs.\n"
        "When asked which file to change, answer with: (1) exact FILE path, "
        "(2) class and method, (3) line numbers from the numbered listing, "
        "(4) a short before/after or what to edit, (5) related files if the "
        "gateway proxies to the processor.\n"
        "Never invent a path that is not in the FILE listings.\n\n"
        f"{_incident_line(incident)}\n\n"
        "### JSON logs for this traceId (./logs)\n"
        f"{log_bundle(incident)}\n\n"
        "### Source listings (paths are repo-relative; lines are N| code)\n"
        f"{code_bundle(incident)}"
    )


def _incident_line(incident: dict | None) -> str:
    if not incident:
        return "No incident is selected."
    return (
        f"Incident: service={incident.get('serviceName')} "
        f"errorType={incident.get('errorType')} "
        f"traceId={incident.get('traceId')} "
        f"message={incident.get('message')}"
    )
