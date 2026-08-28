# Project architecture and runtime flow

Local proof-of-concept: two Spring Boot 3 microservices, Redis as an incident bus, Postgres for Service-B data, and a Streamlit “incident copilot” that packs **this repo’s Java + logs** into an LLM prompt. No Cursor is required at runtime — only Docker Compose.

```mermaid
flowchart TB
  subgraph laptop [Your laptop]
    Browser[Browser]
  end

  subgraph compose [Docker Compose network]
    SA["sre-service-a<br/>gateway :8080 / host 8080+8082"]
    SB["sre-service-b<br/>processor :8080 / host 8081"]
    PG[(sre-postgres<br/>sredb)]
    RD[(sre-redis<br/>Pub/Sub + incident list)]
    CB["sre-chatbot<br/>Streamlit :8501"]
  end

  DiskLogs["./logs JSON files"]
  CodeA["./service-a source"]
  CodeB["./service-b source"]
  Env["./.env"]

  Browser -->|crash URLs| SA
  Browser -->|login + chat| CB
  SA -->|HTTP WebClient| SB
  SB --> PG
  SA -->|publish JSON| RD
  SB -->|publish JSON| RD
  SA --> DiskLogs
  SB --> DiskLogs
  CB -->|subscribe + LPUSH| RD
  CB -->|read-only| DiskLogs
  CB -->|read-only| CodeA
  CB -->|read-only| CodeB
  CB -->|read-only| Env
  CB -->|HTTPS chat completions| LLM[Groq or other OpenAI-compatible API]
```

---

## Containers and ports

| Container | Image / build | Role | Host ports |
| --- | --- | --- | --- |
| `sre-redis` | `redis:7-alpine` | Pub/Sub channel `system-failures`; list `sre:incidents` | 6379 |
| `sre-postgres` | `postgres:16-alpine` | Service-B orders / JPA | 5432 |
| `sre-service-b` | `./service-b` | Failure simulators, DB, Redis publish | **8081** → container 8080 |
| `sre-service-a` | `./service-a` | Gateway, Resilience4j, crash routes, Redis publish | **8080** and **8082** |
| `sre-chatbot` | `./chatbot` | Login, incident sidebar, Groq/mock chat | **8501** |

Inside Compose, services talk by **DNS name** (`postgres`, `redis`, `service-b`), never `localhost`. `localhost` is only for the browser on the same machine.

```mermaid
flowchart LR
  subgraph host [Host ports]
    p8501[8501]
    p8080[8080 / 8082]
    p8081[8081]
  end
  p8501 --> CB[chatbot]
  p8080 --> SA[service-a]
  p8081 --> SB[service-b]
```

---

## Crash and incident pipeline

Hitting a demo URL on Service-A (example: `/simulate-crash/null-pointer`) proxies to Service-B, which throws a simulated failure. Exceptions are published as JSON to Redis. The chatbot listener stores a card and later packs matching logs + ranked source files for the LLM.

```mermaid
sequenceDiagram
  participant User as Browser
  participant A as service-a
  participant B as service-b
  participant PG as postgres
  participant R as redis
  participant L as ./logs
  participant C as chatbot listener

  User->>A: GET /simulate-crash/null-pointer
  A->>B: WebClient GET processor crash path
  B->>PG: optional DB work (timeout / pool sims)
  B-->>A: error / timeout / simulated fault
  A->>R: PUBLISH system-failures JSON
  A->>L: JSON log line with traceId
  B->>L: JSON log line with traceId
  C->>R: SUBSCRIBE system-failures
  C->>C: drop favicon / actuator noise
  C->>R: LPUSH sre:incidents
  User->>C: Open card in Streamlit
```

Failure JSON fields used across the stack: `timestamp`, `serviceName`, `traceId`, `correlationId`, `errorType`, `message`.

**Ten gateway routes** (Service-A `SimulateCrashController` → Service-B `FailureController`):

1. `null-pointer` — NPE on null profile `toUpperCase()`
2. `db-timeout` — pool / SQL timeout simulation
3. `kafka-drop`
4. `out-of-memory`
5. `auth-lock` — shared `INTERNAL_API_KEY`
6. `deadlock`
7. `bad-payload`
8. `rate-limit`
9. `disk-full`
10. `circuit-breaker` — Resilience4j on Service-A after retries

`ALLOW_Display=False` in `.env` puts Service-A in maintenance (HTML) and the chatbot drops ingest so the demo can show “site down.”

---

## Chatbot UI and LLM investigation

```mermaid
flowchart TB
  Login[users.json email/password]
  UI[Streamlit 20% cards / 80% chat]
  Pack[context_pack.py]
  LLM[llm.py complete]

  Login --> UI
  UI -->|Open incident| LLM
  Pack -->|numbered Java + yml + xml| LLM
  Pack -->|logs_for_trace| LLM
  LLM -->|GROQ_* from .env| API[OpenAI-compatible HTTP]
  LLM -->|missing key or API error| Mock[local mock paragraph]
```

On **Open**:

1. Session stores the incident JSON.
2. First user turn asks for a four-section RCA (impact, faulty lines, business, ETTR).
3. `investigation_context` mounts `CODE_ROOTS` (`/code/service-a` and `/code/service-b`) and scores files (controllers named *Fail* / *Simulate* rank higher).
4. Listings include **repo-relative paths and line numbers** so the model can name `service-b/src/main/java/.../FailureController.java`.
5. Follow-ups use a shorter system prompt (do not repeat the four sections unless asked).

Jira and hotfix buttons are **UI stubs** (toasts), not real ticketing or CI.

---

## Source layout (what lives where)

```mermaid
flowchart TB
  Root[sre-incident-poc]
  Root --> DC[docker-compose.yml]
  Root --> ENV[.env gitignored]
  Root --> Docs[docs/]
  Root --> SA[service-a Spring Boot gateway]
  Root --> SB[service-b Spring Boot processor]
  Root --> CB[chatbot Streamlit]
  Root --> Logs[logs/]

  SA --> SAC[SimulateCrashController]
  SA --> SAP[FailurePublisher]
  SB --> SBF[FailureController]
  CB --> APP[app.py]
  CB --> EL[event_listener.py]
  CB --> LLM[llm.py]
  CB --> CP[context_pack.py]
```

| Path | Responsibility |
| --- | --- |
| `service-a/.../SimulateCrashController.java` | Public crash URLs, proxy to B |
| `service-a/.../FailurePublisher.java` | Redis publish |
| `service-a/.../MaintenanceFilter.java` | `ALLOW_Display` |
| `service-b/.../FailureController.java` | Simulated faults |
| `chatbot/event_listener.py` | Redis → incident list |
| `chatbot/log_collector.py` | Correlate `./logs` by `traceId` |
| `chatbot/context_pack.py` | Rank and number source for the prompt |
| `chatbot/llm.py` | Groq/OpenAI-compatible call + mock fallback |
| `chatbot/users.json` | Demo logins (not `.env`) |

---

## Data that never goes through the LLM

Postgres order rows, Redis Pub/Sub plumbing, and HTTP between A and B are **unchanged** by `GROQ_MODEL`. The model only sees what `llm.py` puts in the chat-completions request: system prompt + packed files + logs + the Streamlit message history.
