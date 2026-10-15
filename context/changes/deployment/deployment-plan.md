# Plan: run Mail Triage Agent locally with Docker Compose

## Context

`context/foundation/infrastructure.md` fixes the platform: local Docker Compose with three services (`api`, `ollama`, `mailpit`), one-command start, and a `/health` that reports ready only after the model has been pulled **and** warmed up (FR-003, FR-008). Today only the `uv init` scaffold exists (`src/mail_triage_agent/__init__.py` prints a greeting). This change makes the stack start, become healthy and deliver mail into Mailpit. The triage endpoint (LangChain agent, send-email tool, the qwen/llama comparison and the latency figure) comes in the **next** change, which builds on the readiness gate added here.

Decisions taken with the user:
- **Scope**: infra and readiness only. End-to-end proof is an SMTP smoke mail into Mailpit, not US-01.
- **Ollama image**: `alpine/ollama:0.40.3` (CPU-only, ~34 MB compressed, amd64 and arm64; the brief allows it). The official `ollama/ollama:0.40.4` is 3.78 GB compressed on amd64 and would threaten the 10 GB disk NFR.

Facts checked on 2026-10-15 that supersede parts of infrastructure.md:
- Docker **is** installed now: Docker Desktop 29.8.2, Compose v5.6.0, the VM has 8.2 GB RAM and 8 CPUs. Native Ollama 0.40.0 is installed but not running.
- Pinned tags on Docker Hub: `alpine/ollama:0.40.3`, `axllent/mailpit:v1.31.6`, `python:3.11-slim`. All three publish amd64 and arm64.
- Mailpit image has a built-in `HEALTHCHECK /mailpit readyz`. Its outbound calls are off by default except the GitHub version check (`MP_DISABLE_VERSION_CHECK`) and reverse DNS (`MP_SMTP_DISABLE_RDNS`).
- Ollama's cloud models and web search are turned off with `OLLAMA_NO_CLOUD=1`.
- uv's Docker guide: `COPY --from=ghcr.io/astral-sh/uv:0.13.1`, a two-step `uv sync` (`--frozen --no-install-project`, then `--locked`), `UV_NO_DEV=1`, `UV_COMPILE_BYTECODE=1`, `UV_LINK_MODE=copy`, and `.venv` in `.dockerignore`.

## External integrations (all used only at build or first start)

| Integration | Used for | Data sent | Failure mode → support step |
|---|---|---|---|
| Docker Hub | pulling `python`, `alpine/ollama`, `axllent/mailpit` | none | `toomanyrequests` → `docker login`, then re-run |
| ghcr.io | uv binary at build time | none | blocked registry → fall back to `RUN pip install uv==0.13.1` in the Dockerfile (system Python of the image, not `.venv`) |
| PyPI | `uv sync` at build time | none | proxy or TLS interception → `docker compose build` with `HTTPS_PROXY`/`UV_NATIVE_TLS=1` build args (README note) |
| registry.ollama.ai | model pull on first start | none (model tag only) | interrupted pull resumes on retry. Proxy → set `HTTPS_PROXY` on the `ollama` service |
| cdn.jsdelivr.net | Swagger UI assets loaded by the **browser** at `/api/v1/docs` | none | offline browser → `/api/v1/openapi.json` still works. README note |
| GitHub (Mailpit version check) | — | — | disabled with `MP_DISABLE_VERSION_CHECK=true` |
| Ollama cloud | — | — | disabled with `OLLAMA_NO_CLOUD=1` |

Nothing at runtime sends message content or sender addresses anywhere. Ports are published on `127.0.0.1` only, so the unauthenticated API isn't reachable from the LAN.

## Phases

`context/changes/deployment/deployment-plan.md` (with `change.md` beside it) is the source of truth for progress. Tick its checkboxes as each item lands, and mark each phase heading ✅ once all its items are done.

### Phase 0: Host preflight (read-only checks, ~5 min)
- [ ] `docker compose version` reports v2+ (v5.6.0 found). `docker run --rm hello-world` succeeds.
- [ ] Inspect the Ollama image: `docker image inspect alpine/ollama:0.40.3` (Entrypoint/Cmd, no HEALTHCHECK expected) and `docker run --rm --entrypoint sh alpine/ollama:0.40.3 -c 'command -v ollama'`. **Gate**: if `ollama` isn't on PATH, or the image doesn't start `ollama serve`, set `entrypoint`/`command` explicitly in compose, or fall back to `ollama/ollama:0.40.4` and record the disk cost.
- [ ] Free disk ≥ 10 GB on the Docker Desktop data disk (`docker system df` and Windows free space).
- [ ] Note: native Ollama on 11434 doesn't matter, because the compose Ollama port isn't published.

### Phase 1: Readiness in the API (code)
Files: `src/mail_triage_agent/__init__.py` (reuse the existing `main` script entry), new `src/mail_triage_agent/app.py`, new `src/mail_triage_agent/readiness.py`, `pyproject.toml`.
- [ ] `uv add ollama` (the official client, which `langchain-ollama` uses in the next change anyway) and `uv add --dev pytest`.
- [ ] `readiness.py`: one module-level state (`starting` + stage `pulling|warming`, `ready`, or `failed`) plus a `last_error` that never contains user data. It also holds `MODEL` (from env `OLLAMA_MODEL`, default `qwen2.5:3b`), `OLLAMA_HOST` (default `http://ollama:11434`) and one shared `MODEL_OPTIONS` constant (e.g. `num_ctx`). The next change's agent **must** reuse it: a different `num_ctx` makes Ollama reload the model and the first real request pays the cold start.
- [ ] Warm-up task, started from the FastAPI `lifespan`:
  1. If `client.show(MODEL)` succeeds, skip the pull. This allows offline restarts and avoids a registry round-trip. Otherwise `client.pull(MODEL)`.
  2. Run one `client.chat(...)` with a trivial prompt, `options=MODEL_OPTIONS` and `keep_alive=-1`.
  3. Retry on error with capped backoff (2 s → 30 s), staying `starting` with `last_error` set. No crash loop, so `docker compose logs api` shows each attempt (stage and error class only).
- [ ] `app.py`: `FastAPI(docs_url="/api/v1/docs", openapi_url="/api/v1/openapi.json", lifespan=...)`.
  - `GET /health`: `200 {"status":"ready","model":...}` when ready. Otherwise `503 {"status":"starting","stage":...,"last_error":...}` with `Retry-After: 10`.
  - A reusable `require_ready` dependency that raises the same 503 "not ready" (FR-003). The next change attaches it to the triage endpoint.
- [ ] `main()` runs `uvicorn.run("mail_triage_agent.app:app", host="0.0.0.0", port=8000)`. Keep uvicorn access logs, which show path and status only, never bodies.
- [ ] `tests/test_health.py`: with the Ollama client faked, `/health` is 503 while starting, 200 once ready, and `require_ready` returns 503 before ready. `uv run pytest`, `uv run ruff check`, `uv run ruff format`.

### Phase 2: API image
Files: new `Dockerfile` and `.dockerignore`.
- [ ] `FROM python:3.11-slim`, `COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /bin/`, `ENV UV_NO_DEV=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PATH=/app/.venv/bin:$PATH`.
- [ ] Layered sync per the uv guide (cache mount, `uv.lock` bind, `--frozen --no-install-project`, then copy `pyproject.toml uv.lock README.md src/` and `uv sync --locked`). Run as a non-root user. `CMD ["mail-triage-agent"]`.
- [ ] `.dockerignore`: `.venv`, `.git`, `.claude`, `context`, `documents`, `__pycache__`, `*.pyc`, `.ruff_cache`, `.pytest_cache`, `tests`.
- [ ] Fix `README.md` (currently `# mail-trage-agent` with a typo and no newline). It's copied into the image and `uv_build` needs it in UTF-8.
- [ ] `docker compose build api` succeeds. Check the image size with `docker image ls`.

### Phase 3: `docker-compose.yml`
- [ ] **ollama**: `alpine/ollama:0.40.3` with named volume `ollama-models:/root/.ollama`. Env: `OLLAMA_KEEP_ALIVE=-1`, `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_NO_CLOUD=1`. No `ports:`. Healthcheck `["CMD","ollama","list"]` (interval 10s, start_period 30s). `restart: unless-stopped`.
- [ ] **mailpit**: `axllent/mailpit:v1.31.6`. Env: `MP_DISABLE_VERSION_CHECK=true`, `MP_SMTP_DISABLE_RDNS=true`. Ports `127.0.0.1:${MAILPIT_UI_PORT:-8025}:8025`, with SMTP 1025 internal only. Use the image's built-in healthcheck. `restart: unless-stopped`.
- [ ] **api**: `build: .`. Env: `OLLAMA_HOST=http://ollama:11434`, `OLLAMA_MODEL=qwen2.5:3b`, `SMTP_HOST=mailpit`, `SMTP_PORT=1025`. Ports `127.0.0.1:${API_PORT:-8000}:8000`. `depends_on` ollama and mailpit with `condition: service_healthy`. Healthcheck `["CMD","python","-c","import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)"]` (urlopen raises on 503). Use `interval: 10s`, `timeout: 5s`, `retries: 3`, `start_period: 15m` and `start_interval: 5s`, so a slow first pull counts as "starting" rather than "unhealthy". `restart: unless-stopped`.
- [ ] No one-shot or init services, which avoids the `up --wait` exit-1 pitfall.
- [ ] `docker compose config` validates.

### Phase 4: Bring-up and verification
- [ ] `docker compose up -d --build --wait --wait-timeout 900`, then check the exit code is 0 and `docker compose ps` shows three services healthy.
- [ ] While it starts, `curl -i localhost:8000/health` returns 503 with a stage that moves `pulling` → `warming` → 200 ready.
- [ ] `http://localhost:8000/api/v1/docs` loads.
- [ ] SMTP smoke test: `docker compose exec api python -c "<smtplib send to mailpit:1025, From triage-agent@example.com, To other@example.com, Reply-To test@example.com>"`. Then `curl localhost:8025/api/v1/messages` shows one message with the Reply-To header. Delete it in the UI afterwards.
- [ ] Privacy: `docker compose logs api` contains no message bodies or addresses (only the smoke command, which runs outside the app). `docker compose logs ollama | grep -i cloud` shows cloud disabled.
- [ ] Keep-alive: wait ≥ 10 min idle, then `docker compose exec ollama ollama ps` still lists the model as loaded.
- [ ] Restart path: `docker compose restart api` returns to ready without a pull (the `show` short-circuit).
- [ ] Record `docker stats --no-stream` (idle, model loaded) and `docker system df`.

### Phase 5: Docs
- [ ] `README.md`:
  - prerequisites (Docker Desktop or Engine with Compose v2+, 16 GB RAM, ~10 GB disk)
  - one-command start and the wait variant (`docker compose up -d --wait --wait-timeout 900`)
  - URLs (`/api/v1/docs`, `/health`, Mailpit at `:8025`)
  - stop and reset (`down`, `down -v` re-downloads the ~2 GB model)
  - measured memory and disk with the hardware they were measured on
  - a **Troubleshooting** table covering every edge case below
  - a working `curl -i http://localhost:8000/health` readiness check
  - "Sample request" and "Department boundaries" headings, each marked `TODO(next change)` and pointing to the hand-off checklist below. They must not be left as silent empty sections.
- [ ] Update `context/foundation/infrastructure.md` in place. Docker is installed (versions above). The Ollama image is `alpine/ollama` and why. The VM has 8.2 GB, not 7 GB. Add the `num_ctx` reload risk to the risk register.
- [ ] Update `AGENTS.md` "Current state" (compose exists; the agent and endpoint are still pending).

### Phase 6: Clean-clone rehearsal — ⏭ DEFERRED (run after the triage endpoint change, before submission)
Not part of this change's verification. Kept here so the steps are documented in one place; the next change's hand-off checklist points back to it.
- [ ] `docker compose down -v` (human approval, since it deletes the model volume), fresh `git clone` into a temp dir, then run the exact README command and time it against the 15-minute NFR. Record the time in the README.
- [ ] Run the README sample curl verbatim and confirm the email in Mailpit shows the right recipient and `Reply-To`.

## Edge cases → support steps (go into the README Troubleshooting section)

| Symptom | Cause | Step |
|---|---|---|
| `error during connect ... dockerDesktopLinuxEngine` | Docker Desktop not running | Start Docker Desktop and wait for "Engine running" |
| `up --wait` times out, `/health` shows `pulling` with a network error | No internet or proxy | Fix connectivity, or set `HTTPS_PROXY` on `ollama`. The API keeps retrying, so re-run `up --wait` |
| `toomanyrequests` on pull | Docker Hub anonymous limit | `docker login` |
| `bind: address already in use` on 8000/8025 | Port taken | `API_PORT=8080 MAILPIT_UI_PORT=8026 docker compose up -d --wait` |
| `ollama` container restarts or `OOMKilled` (`docker inspect`) | Docker VM memory too small | Raise `memory=` in `%UserProfile%\.wslconfig`, then `wsl --shutdown` (human step) |
| `no space left on device` | Disk | `docker system df`. Prune unused images (human step) |
| First request slow after idle | Model unloaded | Check that `docker compose exec ollama ollama ps` shows it loaded. `OLLAMA_KEEP_ALIVE=-1` should prevent this |
| `/bin/sh^M` in a container | CRLF | Already mitigated by `.gitattributes` (`eol=lf`) |
| Swagger page blank offline | CDN assets | Use `/api/v1/openapi.json` or curl |
| Podman | Different health-gating | Unsupported, best effort only |

## Verification (end of change)
`uv run ruff check && uv run pytest`, then `docker compose up -d --build --wait --wait-timeout 900` exits 0 with all three services healthy, `/health` returns 200, `/api/v1/docs` loads, the smoke email with the correct Reply-To shows in Mailpit, the model stays loaded after 10 minutes idle, and the README figures are recorded.

## Out of scope (next change)
The triage endpoint, input validation (FR-002), the LangChain agent and send-email tool (FR-004 to FR-007, FR-011, FR-012), the qwen2.5:3b vs llama3.2:3b measurement and latency figure, the sample curl, the boundary table, and CI.

## Hand-off checklist for the next change (triage endpoint)

Copy these into the next change's plan as **must-have** items. The brief requires the sample request ("przykładowe zapytanie (cURL lub podobne)") and FR-010 requires both README items, so the change can't close while either is still a placeholder.
- [ ] **README sample request**: a ready-to-paste `curl` against the triage endpoint using the US-01 example (`{"email":"jan.nowak@example.com","message":"Nie działa mi komputer"}`), plus the expected response (`help-desk@example.com`) and where to see the email (Mailpit at `:8025`). Replace the `TODO(next change)` marker.
- [ ] **README department-boundary table**: all five addresses with their responsibility from PRD US-03, and example messages in Polish and English (at least the US-01 to US-03 examples). Replace the `TODO(next change)` marker.
- [ ] Verification step: run the README curl verbatim against a fresh `docker compose up -d --wait` and confirm the email in Mailpit shows the right recipient and `Reply-To`.
- [ ] Attach `require_ready` to the triage endpoint, and reuse `MODEL`/`MODEL_OPTIONS` from `readiness.py` in the agent.
- [ ] Record the measured latency (warm and after 10 min idle) with the hardware it was measured on.
- [ ] Run Phase 6 (clean-clone rehearsal) from `context/changes/deployment/deployment-plan.md`, with the sample curl included, before submission.