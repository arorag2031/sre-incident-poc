# SRE Incident Copilot — local POC

Transportable, event-driven demo you can run on a laptop and zip onto another host (AWS ECS, DigitalOcean, Render, or another engineer’s machine) **without changing application code**. All service-to-service URLs use Docker Compose DNS names (`redis`, `postgres`, `service-a`, `service-b`).

You do **not** need Java, Maven, or Python installed. You only need [Docker Desktop](https://www.docker.com/products/docker-desktop/).

---

## One command to start everything

Step-by-step (env file, URLs, stop/restart): **[docs/how-to-run.md](docs/how-to-run.md)**.

From this folder:

```bash
docker compose up --build
```

First start can take several minutes while Docker downloads images and Maven builds the two Spring Boot services. Leave the terminal open. When it is ready you will see `sre-chatbot` listening.

Stop with `Ctrl+C`, then `docker compose down`. Keep database data: omit `-v`. Wipe database: `docker compose down -v`.

---

## Open these URLs

| What | URL |
| --- | --- |
| Chatbot UI (login + 20/80 incident copilot) | http://localhost:8501 |
| Gateway demo page (clickable crash links) | http://localhost:8080 |
| Service-B health (processor) | http://localhost:8081/actuator/health |

### Demo login

| Email | Password |
| --- | --- |
| `sre@local.dev` | `ChangeMe123!` |
| `demo@local.dev` | `demo123` |

Accounts live in `chatbot/users.json` (local file, no cloud IdP).

---

## The 10 presentation failure URLs

Use Service-A on port **8080** (also aliased on **8082** so either host port works). Each call creates a new `traceId`, writes JSON logs under `./logs`, and publishes a JSON payload to Redis Pub/Sub topic **`system-failures`**. The chatbot background listener turns that into a left-sidebar incident card.

If the browser says **localhost refused to connect**, the stack is not running yet — wait until `docker compose up --build` shows `sre-chatbot` listening, then use **8080** (or **8082** after a recreate). Do not use a random port.

1. http://localhost:8080/simulate-crash/null-pointer  
2. http://localhost:8080/simulate-crash/db-timeout  
3. http://localhost:8080/simulate-crash/kafka-drop  
4. http://localhost:8080/simulate-crash/out-of-memory  
5. http://localhost:8080/simulate-crash/auth-lock  
6. http://localhost:8080/simulate-crash/deadlock  
7. http://localhost:8080/simulate-crash/bad-payload  
8. http://localhost:8080/simulate-crash/rate-limit  
9. http://localhost:8080/simulate-crash/disk-full  
10. http://localhost:8080/simulate-crash/circuit-breaker  

Same paths on port **8082** also work (example: http://localhost:8082/simulate-crash/null-pointer).

`circuit-breaker` waits a few seconds on purpose: Service-A retries Service-B’s hang endpoint until Resilience4j opens the circuit.

Browser or curl both work:

```bash
curl -i http://localhost:8080/simulate-crash/null-pointer
```

---

## Suggested live demo flow (about 3 minutes)

1. Run `docker compose up --build`.
2. Open http://localhost:8501 and sign in.
3. Click **➕ Open Fresh Chat** and ask a general question (Groq answers if `GROQ_API_KEY` is set; otherwise a local mock is used).
4. In another tab, hit one of the 10 crash URLs.
5. Watch a new incident card appear on the **left (20%)**. Click **Open**.
6. The **right (80%)** chat fills with a four-section SRE brief:  
   1) Infrastructure/App Impact  
   2) Faulty Line of Code Context  
   3) Business Justification  
   4) Estimated Time to Repair (ETTR)  
7. Click **Create Jira Ticket** and **Automate Hotfix Deployment** — they are interactive placeholders only (toasts), ready to wire later.

---

## What is running

| Container | Role |
| --- | --- |
| `sre-redis` | Event bus (Pub/Sub channel `system-failures`) |
| `sre-postgres` | Service-B order data |
| `sre-service-b` | Spring Boot 3 core processor (JPA + failure simulators) |
| `sre-service-a` | Spring Boot 3 gateway (WebClient + Resilience4j) |
| `sre-chatbot` | Streamlit UI, Redis listener thread, log correlation |

Failure JSON fields: `timestamp`, `serviceName`, `traceId`, `correlationId`, `errorType`, `message`.

Logs: structured JSON via Logback to `./logs/service-a/` and `./logs/service-b/`, mounted into the chatbot container as read-only.

---

## Live LLM (Groq free tier)

1. Create a key at https://console.groq.com/keys
2. Put it in `.env`:

```bash
GROQ_API_KEY=your-key-here
GROQ_MODEL=openai/gpt-oss-20b
```

`openai/gpt-oss-20b` is Groq’s current free-tier replacement for the retired Llama 3.1 8B Instant model. For a larger model, use `openai/gpt-oss-120b`.

3. Recreate the chatbot if Compose is already running:

```bash
docker compose up -d --build chatbot
```

Do not commit `.env`. If the key is missing or Groq errors, the UI stays up with a local SRE mock.

---

## Zip and run elsewhere (AWS ECS / DigitalOcean / Render)

1. Zip this directory (include `docker-compose.yml` and all source; you can omit `logs/*.log`).
2. Unzip on the target host that can run Compose (or map each service in `docker-compose.yml` to an ECS task / Render service using the **same environment variables**).
3. Run `docker compose up --build`.
4. Point a browser at host port **8501** (UI) and **8080** (crash URLs).

Do not replace `redis` / `postgres` / `service-b` hostnames in YAML with `localhost` — those names only work inside the Compose network. `localhost` is only for **your browser** on the same machine.

---

## Ports

| Port | Service |
| --- | --- |
| 8501 | Chatbot |
| 8080 | Service-A gateway (crash URLs) |
| 8082 | Same gateway, extra host alias |
| 8081 | Service-B processor |
| 6379 | Redis |
| 5432 | PostgreSQL |

---

## More documentation

| Doc | What it covers |
| --- | --- |
| [docs/how-to-run.md](docs/how-to-run.md) | Bring up, URLs, login, stop/restart |
| [docs/architecture.md](docs/architecture.md) | Stack, crash flow, Redis incidents, chatbot + LLM (diagrams) |
| [docs/swap-llm-model.md](docs/swap-llm-model.md) | Change Groq/OpenAI-compatible model with `.env` only |
| [docs/run-on-another-machine.md](docs/run-on-another-machine.md) | `.env` checklist to run the stack on another laptop with Docker |

## Layout

```
sre-incident-poc/
  docker-compose.yml
  docs/             How to run, architecture, LLM swap, portable .env
  chatbot/          Python Streamlit UI
  service-a/        Java gateway
  service-b/        Java processor + Postgres
  logs/             Shared JSON logs
```
