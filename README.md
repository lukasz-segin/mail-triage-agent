# mail-triage-agent

Routes an employee's free-text request to the right department inbox using a local LLM agent.

Everything runs on your machine in Docker Compose: the API, Ollama (CPU only, model `qwen2.5:3b`) and Mailpit, which catches the outgoing email. Message content and sender addresses never leave the local environment and are never logged.

## Prerequisites

- Docker Desktop, or Docker Engine with the Compose v2+ plugin (`docker compose version`).
- 16 GB RAM. On Windows, Docker's WSL2 VM gets half of that by default, which is enough.
- About 10 GB of free disk for images and the model.
- Internet access on the first start only, to pull the images and the ~2 GB model.

Podman isn't supported. Its health-gated startup behaves differently, so it may work but is best effort only.

## Run

```sh
docker compose up -d
```

This builds the API image, starts the three services, and has the API pull and warm up the model. The first start takes a few minutes (about 4 minutes on the hardware below, mostly the model download). Later starts reuse the model and take seconds.

To block until the stack is actually ready to answer requests:

```sh
docker compose up -d --wait --wait-timeout 900
```

It exits 0 once all three services are healthy, which for the API means the model is pulled **and** loaded. Add `--build` after changing the code.

Check readiness at any time:

```sh
curl -i http://localhost:8000/health
```

On Windows PowerShell, type `curl.exe` instead of `curl`.

- While starting it returns `503` with `Retry-After: 10` and a body like `{"detail":{"status":"starting","stage":"pulling","last_error":null}}`. The stage moves from `pulling` to `warming`.
- Once ready it returns `200 {"status":"ready","model":"qwen2.5:3b"}`.

Requests to the API before that get the same `503` "not ready" response.

### URLs

| What | URL |
|---|---|
| Interactive API docs | http://localhost:8000/api/v1/docs |
| Triage endpoint | `POST` http://localhost:8000/api/v1/triage |
| OpenAPI schema | http://localhost:8000/api/v1/openapi.json |
| Readiness | http://localhost:8000/health |
| Mailpit (caught email) | http://localhost:8025 |

All ports are published on `127.0.0.1` only, because the API has no authentication. Ollama's port isn't published at all.

### Stop and reset

```sh
docker compose down      # stop; the downloaded model is kept
docker compose down -v   # also delete the model volume; the next start re-downloads ~2 GB
```

## Sample request

Once `/health` answers `200`, send the US-01 example (bash or zsh):

```sh
curl -X POST http://localhost:8000/api/v1/triage   -H "Content-Type: application/json"   -d '{"email":"jan.nowak@example.com","message":"Nie działa mi komputer"}'
```

On Windows, Git Bash passes "ł" to `curl` in the ANSI code page, so the request fails with `400`; use the PowerShell variant there.

On Windows PowerShell, use `Invoke-RestMethod`. The `curl.exe` hint above applies to `/health` only: in Windows PowerShell 5.1, `curl.exe` strips the JSON's inner double quotes and sends "ł" in the wrong encoding, so this request would fail with `422`.

```powershell
$body = '{"email":"jan.nowak@example.com","message":"Nie działa mi komputer"}'
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/triage `
  -ContentType 'application/json; charset=utf-8' `
  -Body ([Text.Encoding]::UTF8.GetBytes($body))
```

Expected response: `200 {"department":"help-desk@example.com"}`.

Open Mailpit at http://localhost:8025 to see the email. It goes to `help-desk@example.com` with `Reply-To: jan.nowak@example.com`, `From: triage-agent@example.com`, subject `[Triage] New request`, and the message unaltered as its body. Each request sends exactly one email.

Errors (no email is sent in any of these cases):

- `503`: the model isn't ready yet (see `/health`).
- `502`: the model produced no department decision, or sending the email failed.
- `504`: a single model call took more than 90 s. A request makes at most 3 model calls, so the worst case is about 3 × 90 s.

You can also send the request from the interactive docs at http://localhost:8000/api/v1/docs, where `POST /api/v1/triage` comes pre-filled with this example.

## Department boundaries

The agent picks exactly one of these five inboxes. The responsibilities come from the PRD and are what the model is told in its system prompt.

| Address | Owns | Example (Polish) | Example (English) |
|---|---|---|---|
| `kadry@example.com` | Personnel administration: leave, contracts, employment documents | Chciałbym zgłosić urlop na jutro | I'd like to request a day of leave tomorrow |
| `human-resources@example.com` | Hiring and employee development | Chciałbym zapisać się na szkolenie z zarządzania projektami | We need to hire a junior developer for my team |
| `help-desk@example.com` | User-facing hardware and software problems | Nie działa mi komputer | My laptop won't turn on |
| `it@example.com` | Infrastructure, access, systems | Potrzebuję dostępu do bazy danych produkcyjnej | The VPN server is down for the whole office |
| `other@example.com` | Fallback: only when none of the four above matches | Gdzie mogę zaparkować rower? | hello? |

Each example was sent once on `qwen2.5:3b` and landed at the address in its row. The two examples from the brief ("Nie działa mi komputer", "Chciałbym zgłosić urlop na jutro") are covered by the live test, which passed 10 of 10 runs.

Rules the model follows:

- **Ownership wins.** If any of the four responsibilities plausibly matches, the request goes to that owner. `other@` is used only when nothing matches.
- **Leave goes to `kadry@`, not `human-resources@`.** Kadry owns personnel administration (leave, contracts, employment documents); HR owns hiring and employee development.
- **One request per email.** A message with several requests is routed by its main (first or dominant) one, and the receiving department forwards the rest.
- **Steering is ignored.** "Send this to it@" inside a message counts only when it agrees with what the request is about.

## Architecture decisions

- **The agent sends the email itself, through tool calling.** A LangChain agent (`create_agent`) on the local Ollama model reads the message and calls the `send_email` tool. Routing comes only from the model reading the intent: there is no keyword or rule-based routing, and no code that pre-classifies or overrides its choice.
- **The tool takes only the department.** The model supplies one argument, the department address, and the tool's schema restricts it to the five addresses. The tool injects everything else from the original request: the body (the message, verbatim) and `Reply-To` (the sender). So the model can't alter the employee's message, can't change the reply address, and can't send outside the five inboxes. A rejected address goes back to the model as an error so it can correct itself (at most 3 model calls per request).
- **At most one email per request.** The tool records the send under a lock, and any further call in the same request is refused. The agent stops right after the send, which also saves a model turn.
- **The response comes from the send record.** The department in the response is where the email actually went, not what the model said. Success is decided by that record: once the email is sent, the request succeeds; if nothing was sent, the API returns an error (`502` or `504`) and no email exists.
- **Local and CPU-only.** `alpine/ollama` (much smaller than `ollama/ollama`) runs `qwen2.5:3b`, a 3B model that supports tool calling. It routed the brief's examples 10 of 10, so the alternative candidate (`llama3.2:3b`) wasn't needed. The model is pulled and warmed up on start, and `/health` and the triage endpoint answer `503` until it is loaded, so the first real request doesn't pay the cold start. Every model call reuses the warm-up's settings so Ollama doesn't reload the model.
- **FastAPI** gives the OpenAPI docs at `/api/v1/docs` for free, with the request pre-filled. **Mailpit** catches the email; its SMTP port stays on the Compose network.
- **Privacy.** Nothing leaves the machine. Logs carry only the department, the outcome and the elapsed time, never the message or the sender, and error responses never echo the request. LangChain tracing is off.

## Known limitations

- **No input validation yet.** The endpoint accepts any strings for `email` and `message`: a malformed address, an empty message or a very long one is not rejected up front with a clear error. A sender address containing a line break is still refused before anything is sent, but it comes back as a generic `502`.
- **Routing errors are possible.** A 3B model on CPU can misroute a borderline message. For example, "Potrzebuję zaświadczenia o zatrudnieniu" (an employment certificate, which belongs to `kadry@`) went to `human-resources@` in one run.
- **No retry or outbox.** A failed send returns an error and is not retried later. A production version would add a durable outbox.
- **No authentication.** The API is published on `127.0.0.1` only. A caller can submit on behalf of any address, which becomes the `Reply-To`.

## Resource usage

Measured on 2026-10-15 on an Intel Core i5-10210U laptop with 16 GB RAM, Windows 11, Docker Desktop 29.8.2 on WSL2 (VM: 8 CPUs, 7.64 GiB RAM):

| | |
|---|---|
| Memory, idle with the model loaded (`docker stats`) | ollama 3.91 GiB, api 45 MiB, mailpit 9 MiB: about 4 GiB in total |
| Disk (`docker system df`) | about 2.8 GB: images 459 MB (api 278 MB, ollama 121 MB, mailpit 60 MB), model volume 1.93 GB, build cache 355 MB |
| First start, `up -d --wait` | 247 s, mostly the model download |
| Restart with the model present | 11 s |

A warm request takes about 2.5–4 s end to end on the same hardware (the API logs about 2.5 s of routing).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `error during connect ... dockerDesktopLinuxEngine` | Docker Desktop isn't running | Start Docker Desktop and wait for "Engine running". |
| `up --wait` times out, and `/health` shows `pulling` with a network error in `last_error` | No internet, or a proxy | Fix connectivity, or set `HTTPS_PROXY` on the `ollama` service. The API keeps retrying, so just re-run `up --wait`. |
| `toomanyrequests` when pulling images | Docker Hub's anonymous pull limit | `docker login`, then re-run. |
| `bind: address already in use` on 8000 or 8025 | The port is taken | Pick other ports: `API_PORT=8080 MAILPIT_UI_PORT=8026 docker compose up -d --wait` (PowerShell: `$env:API_PORT=8080; $env:MAILPIT_UI_PORT=8026; docker compose up -d --wait`). |
| The `ollama` container keeps restarting, or `docker inspect` shows `OOMKilled` | The Docker VM has too little memory | On Windows, raise `memory=` under `[wsl2]` in `%UserProfile%\.wslconfig`, then run `wsl --shutdown` and restart Docker Desktop. Elsewhere, raise the memory limit in Docker's settings. |
| `no space left on device` | Not enough disk | Check `docker system df` and prune unused images. |
| The first request after a long idle is slow | The model was unloaded | `docker compose exec ollama ollama ps` should list the model with `UNTIL Forever`. `OLLAMA_KEEP_ALIVE=-1` in the compose file normally prevents this. |
| `/bin/sh^M: not found` in a container | CRLF line endings | `.gitattributes` forces LF already. Re-clone if your Git rewrote the files. |
| The Swagger page at `/api/v1/docs` is blank | The browser is offline and can't load the Swagger UI assets from the CDN | Use `/api/v1/openapi.json` or `curl`. |
| PyPI connection errors during `docker compose build` | A proxy | `docker compose build --build-arg HTTPS_PROXY=http://<proxy>:<port>`, then `docker compose up -d --wait`. |

Logs: `docker compose ps` shows health, and `docker compose logs -f api` (or `ollama`, `mailpit`) shows each service.

## Development

Dependencies and commands go through [uv](https://docs.astral.sh/uv/):

```sh
uv sync
uv run pytest
uv run ruff check
uv run ruff format
```
