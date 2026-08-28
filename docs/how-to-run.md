# How to run and bring up this app

You only need **Docker Desktop** (or Docker Engine + Compose v2). You do **not** need Java, Maven, Python, or Cursor.

---

## Bring the stack up

1. Open a terminal in the project folder (the one that contains `docker-compose.yml`).
2. If there is no `.env` yet:

```bash
cp .env.example .env
```

3. Optional: put a Groq key in `.env` as `GROQ_API_KEY=...`. Leave it empty if you only want the local mock chat. Details: [run-on-another-machine.md](run-on-another-machine.md).
4. Start everything:

```bash
docker compose up --build
```

First start can take several minutes (image download + Maven build of both Java services). Leave that terminal open. You are ready when `sre-chatbot` is listening.

Run in the background instead:

```bash
docker compose up -d --build
```

Check containers:

```bash
docker compose ps
```

---

## Open the app

| What | URL |
| --- | --- |
| Chatbot (sign in here) | http://localhost:8501 |
| Gateway / crash URLs | http://localhost:8080 |
| Service-B health | http://localhost:8081/actuator/health |

Demo logins (`chatbot/users.json`):

| Email | Password |
| --- | --- |
| `sre@local.dev` | `ChangeMe123!` |
| `demo@local.dev` | `demo123` |

Quick demo: sign in → in another tab open http://localhost:8080/simulate-crash/null-pointer → back on 8501, click **Open** on the new left-side card.

If the browser says connection refused, wait until Compose finishes starting `sre-service-a` and `sre-chatbot`.

---

## Stop / restart

| Goal | Command |
| --- | --- |
| Stop (Ctrl+C if it is in the foreground), then remove containers | `docker compose down` |
| Stop but keep Postgres data | `docker compose down` (do **not** add `-v`) |
| Wipe the database volume | `docker compose down -v` |
| Start again after a stop | `docker compose up --build` |
| Recreate only the chatbot after `.env` LLM changes | `docker compose up -d chatbot` |

---

## Related docs

- [architecture.md](architecture.md) — what each container does
- [swap-llm-model.md](swap-llm-model.md) — change the chat model
- [run-on-another-machine.md](run-on-another-machine.md) — copy the folder to a second laptop and fill `.env`
