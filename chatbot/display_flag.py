import os
from pathlib import Path

_CANDIDATE_FILES = (
    os.getenv("DISPLAY_FLAG_FILE", ""),
    "/config/.env",
    "/app/runtime.env",
    str(Path(__file__).resolve().parent.parent / ".env"),
    str(Path(__file__).resolve().parent / ".env"),
)


def _parse_bool(raw: str) -> bool | None:
    value = raw.strip().strip('"').strip("'")
    if not value:
        return None
    lowered = value.lower()
    if lowered in {"true", "1", "yes", "on"}:
        return True
    if lowered in {"false", "0", "no", "off"}:
        return False
    return None


def is_display_allowed() -> bool:
    env_direct = _parse_bool(os.getenv("ALLOW_Display", "") or os.getenv("ALLOW_DISPLAY", ""))
    file_value = _read_from_file()
    if file_value is not None:
        return file_value
    if env_direct is not None:
        return env_direct
    return True


def _read_from_file() -> bool | None:
    for candidate in _CANDIDATE_FILES:
        if not candidate:
            continue
        path = Path(candidate)
        if not path.is_file():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if stripped.startswith("export "):
                    stripped = stripped[7:].strip()
                key, _, value = stripped.partition("=")
                if key.strip() in {"ALLOW_Display", "ALLOW_DISPLAY"}:
                    parsed = _parse_bool(value)
                    if parsed is not None:
                        return parsed
        except OSError:
            continue
    return None
