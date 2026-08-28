import os
from pathlib import Path

from openai import OpenAI

from context_pack import investigation_context

ENV_CANDIDATES = (
    os.getenv("DISPLAY_FLAG_FILE", ""),
    "/config/.env",
    str(Path(__file__).resolve().parent.parent / ".env"),
)

SYSTEM_PROMPT_INITIAL = """You are a principal SRE plus staff Java engineer (like Copilot/Claude on a local repo).
You receive repo-relative FILE listings with line numbers and matching container logs.
Use only those files. For the first incident analysis use these four sections:

1) Infrastructure/App Impact
2) Faulty Line of Code Context — exact FILE path, method, line numbers, and a short code quote from the listing
3) Business Justification
4) Estimated Time to Repair (ETTR)

If a gateway route calls Service-B, name both files (SimulateCrashController and FailureController) when relevant.
"""

SYSTEM_PROMPT_FOLLOWUP = """You are a principal SRE plus staff Java engineer with the same numbered source listings.
If the user asks which file to change, what to edit, or where the bug is:
- Give the exact repo-relative path (example: service-b/src/main/java/.../FailureController.java)
- Name the class and method
- Give line numbers from the listings
- Quote 5–15 lines of that method
- Say what to change (null-check, return 4xx, etc.)
- Mention related files (gateway proxy vs processor throw site)

Do not repeat the four-section RCA unless they ask. Do not invent files.
"""

SYSTEM_PROMPT_FRESH = """You are a principal SRE plus staff Java engineer with the microservice source listings.
If they ask where something lives, give exact FILE paths and line numbers from the listings.
Do not invent an incident unless they describe one.
"""

_GROQ_MODELS = (
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
)


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, _, value = line.partition("=")
        parsed = value.strip().strip('"').strip("'")
        if parsed:
            values[key.strip()] = parsed
    return values


def _env(name: str, default: str = "") -> str:
    for candidate in ENV_CANDIDATES:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_file():
            file_value = _parse_env_file(path).get(name, "")
            if file_value:
                return file_value
    return (os.getenv(name, default) or default).strip()


def _groq_key() -> str:
    return _env("GROQ_API_KEY")


def groq_ready() -> bool:
    return bool(_groq_key())


def _configured_groq_model() -> str:
    return _env("GROQ_MODEL", "openai/gpt-oss-20b") or "openai/gpt-oss-20b"


def _llm_base_url() -> str:
    return (
        _env("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
        or "https://api.groq.com/openai/v1"
    )


def _user_turns(messages: list[dict]) -> int:
    return sum(1 for item in messages if item.get("role") == "user")


def _is_initial_incident_turn(messages: list[dict], incident: dict | None) -> bool:
    if not incident:
        return False
    return _user_turns(messages) <= 1


def _incident_summary(incident: dict | None) -> str:
    if not incident:
        return ""
    return (
        f"Selected incident: service={incident.get('serviceName')} "
        f"errorType={incident.get('errorType')} "
        f"traceId={incident.get('traceId')} "
        f"message={incident.get('message')}"
    )


def mock_sre_answer(user_text: str, incident: dict | None, initial: bool) -> str:
    if incident is None:
        return (
            "No incident is selected. Ask a troubleshooting question, or open a card on the left.\n\n"
            f"{user_text}"
        )
    if not initial:
        return (
            f"The issue is a `{incident.get('errorType')}` in `{incident.get('serviceName')}` "
            f"(trace `{incident.get('shortTrace')}`): {incident.get('message')} "
            "That happens when order enrichment calls `toUpperCase()` on a null customer profile. "
            "It is an application null-deref, not a disk or broker outage. "
            "Ask if you want the likely code path, blast radius, or a workaround."
        )
    return f"""1) Infrastructure/App Impact
Service `{incident.get("serviceName")}` returned `{incident.get("errorType")}` on trace `{incident.get("shortTrace")}`. Service-A callers of `/simulate-crash/*` get a failed HTTP response, so order enrichment is degraded.

2) Faulty Line of Code Context
`{incident.get("message")}`
Assumption: Service-B `FailureController` null-pointer simulator (`loadCustomerProfile` then `toUpperCase()`).

3) Business Justification
Checkout/order enrichment fails for that request path, which burns SLAs and creates pages until contained.

4) Estimated Time to Repair (ETTR)
About 25–45 minutes to confirm blast radius, apply a workaround, and verify a healthy processor path.
"""


def _system_prompt(messages: list[dict], incident: dict | None) -> str:
    pack = investigation_context(incident)
    if incident is None:
        return SYSTEM_PROMPT_FRESH + "\n\n" + pack
    if _is_initial_incident_turn(messages, incident):
        return SYSTEM_PROMPT_INITIAL + "\n\n" + pack
    return SYSTEM_PROMPT_FOLLOWUP + "\n\n" + pack


def _groq_complete(messages: list[dict], incident: dict | None) -> str:
    client = OpenAI(api_key=_groq_key(), base_url=_llm_base_url())
    api_messages = [{"role": "system", "content": _system_prompt(messages, incident)}]
    for item in messages:
        if item["role"] in ("user", "assistant") and item.get("content"):
            api_messages.append({"role": item["role"], "content": item["content"]})

    tried: set[str] = set()
    last_error: Exception | None = None
    for model_name in (_configured_groq_model(), *_GROQ_MODELS):
        if not model_name or model_name in tried:
            continue
        tried.add(model_name)
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=api_messages,
                temperature=0.2,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as exc:
            last_error = exc
            detail = str(exc).lower()
            if any(token in detail for token in ("404", "not found", "deprecat", "no longer", "model_not_found")):
                continue
            raise
    if last_error:
        raise last_error
    return "No model output."


def complete(messages: list[dict], incident: dict | None) -> str:
    last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    initial = _is_initial_incident_turn(messages, incident)
    if not _groq_key():
        return mock_sre_answer(last, incident, initial)

    try:
        return _groq_complete(messages, incident) or "No model output."
    except Exception as exc:  # noqa: BLE001 — keep the UI up if Groq is down
        hint = str(exc)
        if _groq_key():
            hint = hint.replace(_groq_key(), "***")
        return mock_sre_answer(last, incident, initial) + f"\n\n(Groq error: {hint})"
