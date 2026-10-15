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
| PyPI | `uv sync` at build time | none | proxy → `docker compose build --build-arg HTTPS_PROXY=...` (README note). TLS interception would need the corporate CA in the image: not handled |
| registry.ollama.ai | model pull on first start | none (model tag only) | interrupted pull resumes on retry. Proxy → set `HTTPS_PROXY` on the `ollama` service |
| cdn.jsdelivr.net | Swagger UI assets loaded by the **browser** at `/api/v1/docs` | none | offline browser → `/api/v1/openapi.json` still works. README note |
| GitHub (Mailpit version check) | — | — | disabled with `MP_DISABLE_VERSION_CHECK=true` |
| Ollama cloud | — | — | disabled with `OLLAMA_NO_CLOUD=1` |
| GitHub Actions (Phase 7) | lint, tests and the API image build on PRs and on pushes to `main` | repo code only | a flaky runner or registry → re-run the job |

Nothing at runtime sends message content or sender addresses anywhere. Ports are published on `127.0.0.1` only, so the unauthenticated API isn't reachable from the LAN.

## Phases

`context/changes/deployment/deployment-plan.md` (with `change.md` beside it) is the source of truth for progress. Tick its checkboxes as each item lands, and mark each phase heading ✅ once all its items are done.

### Phase 0: Host preflight (read-only checks, ~5 min) ✅
- [x] `docker compose version` reports v2+ (v5.6.0 found). `docker run --rm hello-world` succeeds.
- [x] Inspect the Ollama image: `docker image inspect alpine/ollama:0.40.3` (Entrypoint/Cmd, no HEALTHCHECK expected) and `docker run --rm --entrypoint sh alpine/ollama:0.40.3 -c 'command -v ollama'`. **Gate**: if `ollama` isn't on PATH, or the image doesn't start `ollama serve`, set `entrypoint`/`command` explicitly in compose, or fall back to `ollama/ollama:0.40.4` and record the disk cost.
- [x] Free disk ≥ 10 GB on the Docker Desktop data disk (`docker system df` and Windows free space).
- [x] Note: native Ollama on 11434 doesn't matter, because the compose Ollama port isn't published.

Results (2026-10-15):
- Docker Compose v5.6.0. `hello-world` prints "Hello from Docker!".
- `alpine/ollama:0.40.3` (amd64): `Entrypoint=["/usr/bin/ollama"]`, `Cmd=["serve"]`, no HEALTHCHECK, `OLLAMA_HOST=0.0.0.0` preset, runs as root with `HOME=/root`, and the model dir is `/root/.ollama`. Unpacked size is 121 MB. **Gate passed**: no `entrypoint`/`command` override is needed.
- `ollama list` inside a running container exits 0, so it works as the healthcheck. The image has no `curl` or `wget`, which confirms the decision not to use an HTTP probe.
- Disk: Docker Desktop stores its data on C:, which has 36 GB free (≥ 10 GB). The VM has 8.2 GB RAM and 8 CPUs.

### Phase 1: Readiness in the API (code) ✅
Files: `src/mail_triage_agent/__init__.py` (reuse the existing `main` script entry), new `src/mail_triage_agent/app.py`, new `src/mail_triage_agent/readiness.py`, `pyproject.toml`.
- [x] `uv add ollama` (the official client, which `langchain-ollama` uses in the next change anyway) and `uv add --dev pytest`.
- [x] `readiness.py`: one module-level state (`starting` + stage `pulling|warming`, `ready`, or `failed`) plus a `last_error` that never contains user data. It also holds `MODEL` (from env `OLLAMA_MODEL`, default `qwen2.5:3b`), `OLLAMA_HOST` (default `http://ollama:11434`) and one shared `MODEL_OPTIONS` constant (e.g. `num_ctx`). The next change's agent **must** reuse it: a different `num_ctx` makes Ollama reload the model and the first real request pays the cold start.
- [x] Warm-up task, started from the FastAPI `lifespan`:
  1. If `client.show(MODEL)` succeeds, skip the pull. This allows offline restarts and avoids a registry round-trip. Otherwise `client.pull(MODEL)`.
  2. Run one `client.chat(...)` with a trivial prompt, `options=MODEL_OPTIONS` and `keep_alive=-1`.
  3. Retry on error with capped backoff (2 s → 30 s), staying `starting` with `last_error` set. No crash loop, so `docker compose logs api` shows each attempt (stage and error class only).
- [x] `app.py`: `FastAPI(docs_url="/api/v1/docs", openapi_url="/api/v1/openapi.json", lifespan=...)`.
  - `GET /health`: `200 {"status":"ready","model":...}` when ready. Otherwise `503 {"status":"starting","stage":...,"last_error":...}` with `Retry-After: 10`.
  - A reusable `require_ready` dependency that raises the same 503 "not ready" (FR-003). The next change attaches it to the triage endpoint.
- [x] `main()` runs `uvicorn.run("mail_triage_agent.app:app", host="0.0.0.0", port=8000)`. Keep uvicorn access logs, which show path and status only, never bodies.
- [x] `tests/test_health.py`: with the Ollama client faked, `/health` is 503 while starting, 200 once ready, and `require_ready` returns 503 before ready. `uv run pytest`, `uv run ruff check`, `uv run ruff format`.

As built (deviations from the items above):
- **No `failed` state.** Warm-up retries forever, so the state is only `starting` (stage `pulling` or `warming`) or `ready`. A permanent failure, such as a wrong model tag, shows as `starting` with `last_error` set until the healthcheck `start_period` runs out.
- **`last_error` carries the exception class and message** (truncated to 300 chars), not just the class. Warm-up never handles user data, and the message is what makes a wrong tag or an unreachable host diagnosable from `/health` and the logs.
- **`/health` uses `require_ready` itself**, so every 503 has the same shape: `{"detail": {"status", "stage", "last_error"}}` with `Retry-After: 10`.
- **The warm-up chat adds `num_predict: 1`** on top of `MODEL_OPTIONS`. Only load-time options such as `num_ctx` trigger a reload, so this keeps warm-up short without risking one.
- **Tests are in `tests/test_readiness.py`** (6 tests): `/health` returns 503 then 200, `require_ready` gates another route, the pull happens only when the model is missing, the chat uses `MODEL_OPTIONS` and `keep_alive=-1`, and warm-up retries until it succeeds.
- **The test client uses `httpx2`** as a dev dependency, as Starlette's deprecation warning recommends.
- **The broad `except Exception` carries `# noqa: BLE001`, with a reason in the code.** An escaped exception would end the background task silently.
- **Proof:** `ruff format` and `ruff check` are clean and 6/6 tests pass. A live run with `OLLAMA_HOST` pointed at a closed port returned `/health` 503 with `stage: pulling` and `last_error: ConnectionError …`, `/api/v1/docs` returned 200, and the logs showed retries at 2 s and then 4 s.

### Phase 2: API image ✅
Files: new `Dockerfile` and `.dockerignore`.
- [x] `FROM python:3.11-slim`, `COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /bin/`, `ENV UV_NO_DEV=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PATH=/app/.venv/bin:$PATH`.
- [x] Layered sync per the uv guide (cache mount, `uv.lock` bind, `--frozen --no-install-project`, then copy `pyproject.toml uv.lock README.md src/` and `uv sync --locked`). Run as a non-root user. `CMD ["mail-triage-agent"]`.
- [x] `.dockerignore`: `.venv`, `.git`, `.claude`, `context`, `documents`, `__pycache__`, `*.pyc`, `.ruff_cache`, `.pytest_cache`, `tests`.
- [x] Fix `README.md` (currently `# mail-trage-agent` with a typo and no newline). It's copied into the image and `uv_build` needs it in UTF-8.
- [x] `docker compose build api` succeeds. Check the image size with `docker image ls`.

As built (deviations from the items above):
- **First sync binds `pyproject.toml` and `uv.lock` and runs `--locked`**, as the current uv guide does, instead of `--frozen` with only the lockfile.
- **`UV_PYTHON_DOWNLOADS=never`**, so uv always uses the image's Python 3.11 and never downloads one.
- **The non-root user is `useradd --system app`** (uid 999). A fixed uid 10001 triggered a `SYS_UID_MAX` warning.
- **`.dockerignore` also excludes `docs`, `.10x-cli.json` and `.claude`.**
- **Built with `docker build -t mail-triage-agent-api:dev .`**, because the compose file only arrives in Phase 3. `docker compose build` gets exercised in Phase 4.
- **Proof:**
  - The image is **278 MB** and runs as `uid=999(app)`.
  - With Ollama unreachable, `/health` returns 503 (`stage: pulling`), `/api/v1/docs` returns 200, and the logs show the warm-up retry.
  - The planned compose healthcheck command (`python -c "urllib.request.urlopen(...)"`) exits 1 while the service is not ready.
  - Access logs show method, path and status only.

### Phase 3: `docker-compose.yml` ✅
- [x] **ollama**: `alpine/ollama:0.40.3` with named volume `ollama-models:/root/.ollama`. Env: `OLLAMA_KEEP_ALIVE=-1`, `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_NO_CLOUD=1`. No `ports:`. Healthcheck `["CMD","ollama","list"]` (interval 10s, start_period 30s). `restart: unless-stopped`.
- [x] **mailpit**: `axllent/mailpit:v1.31.6`. Env: `MP_DISABLE_VERSION_CHECK=true`, `MP_SMTP_DISABLE_RDNS=true`. Ports `127.0.0.1:${MAILPIT_UI_PORT:-8025}:8025`, with SMTP 1025 internal only. Use the image's built-in healthcheck. `restart: unless-stopped`.
- [x] **api**: `build: .`. Env: `OLLAMA_HOST=http://ollama:11434`, `OLLAMA_MODEL=qwen2.5:3b`, `SMTP_HOST=mailpit`, `SMTP_PORT=1025`. Ports `127.0.0.1:${API_PORT:-8000}:8000`. `depends_on` ollama and mailpit with `condition: service_healthy`. Healthcheck `["CMD","python","-c","import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)"]` (urlopen raises on 503). Use `interval: 10s`, `timeout: 5s`, `retries: 3`, `start_period: 15m` and `start_interval: 5s`, so a slow first pull counts as "starting" rather than "unhealthy". `restart: unless-stopped`.
- [x] No one-shot or init services, which avoids the `up --wait` exit-1 pitfall.
- [x] `docker compose config` validates.

As built (deviations from the items above):
- **The api service also sets `image: mail-triage-agent-api`**, so the built image has a stable name for `docker image ls`.
- **The ollama healthcheck adds `timeout: 5s`, `retries: 3` and `start_interval: 2s`**, so Compose notices quickly once `ollama serve` is up.
- **`SMTP_HOST` and `SMTP_PORT` are set on `api` but nothing reads them yet.** The send-email tool in the next change will. The Phase 4 smoke test passes `mailpit:1025` explicitly.
- **Proof:**
  - `docker compose config -q` passes.
  - The resolved config publishes `127.0.0.1:8000→8000` (api) and `127.0.0.1:8025→8025` (mailpit), and nothing for ollama.
  - `API_PORT=8080` overrides the published port.
  - `api` depends on `ollama` and `mailpit` with `service_healthy`.
  - The Mailpit image's healthcheck is `["CMD","/mailpit","readyz"]`.

### Phase 4: Bring-up and verification ✅
- [x] `docker compose up -d --build --wait --wait-timeout 900`, then check the exit code is 0 and `docker compose ps` shows three services healthy.
- [x] While it starts, `curl -i localhost:8000/health` returns 503 with a stage that moves `pulling` → `warming` → 200 ready.
- [x] `http://localhost:8000/api/v1/docs` loads.
- [x] SMTP smoke test: `docker compose exec api python -c "<smtplib send to mailpit:1025, From triage-agent@example.com, To other@example.com, Reply-To test@example.com>"`. Then `curl localhost:8025/api/v1/messages` shows one message with the Reply-To header. Delete it in the UI afterwards.
- [x] Privacy: `docker compose logs api` contains no message bodies or addresses (only the smoke command, which runs outside the app). `docker compose logs ollama | grep -i cloud` shows cloud disabled.
- [x] Keep-alive: wait ≥ 10 min idle, then `docker compose exec ollama ollama ps` still lists the model as loaded.
- [x] Restart path: `docker compose restart api` returns to ready without a pull (the `show` short-circuit).
- [x] Record `docker stats --no-stream` (idle, model loaded) and `docker system df`.

Results (2026-10-15, Windows 11, Docker Desktop 29.8.2 on WSL2, VM with 8 CPUs and 7.64 GiB RAM):
- **Cold start:** `up -d --build --wait --wait-timeout 900` exited **0 after 247 s**. The API image was already built, so the time is mostly the `qwen2.5:3b` pull. All three services are `healthy`.
- **`/health` stages:**
  - `starting/pulling` from 20:48:30.
  - `starting/warming` at 20:49:36.
  - `200 {"status":"ready","model":"qwen2.5:3b"}` at 20:49:44, so warm-up took about 8 s.
  - The API logs show `show → 404 → pull → chat → ready`.
- **Model:** `ollama ps` shows `qwen2.5:3b 2.2 GB, 100% CPU, CONTEXT 4096, UNTIL Forever`. The context matches `MODEL_OPTIONS`.
- **Docs:** `/api/v1/docs` returned 200.
- **SMTP smoke test:** a stdlib `smtplib` send from the `api` container to `mailpit:1025` produced one message in the Mailpit API:
  - `From: triage-agent@example.com`, `To: other@example.com`, `Reply-To: test@example.com`, subject `[Triage] New request`.
  - It was deleted afterwards through the Mailpit API (`DELETE /api/v1/messages`), leaving a total of 0.
- **Privacy:**
  - The `api` logs have 0 lines matching `@example.com` or the smoke text.
  - Non-healthcheck lines are startup, readiness stages, and httpx request lines to `ollama:11434`. Those carry only URL and status, never bodies.
  - The ollama logs show `Ollama cloud disabled: true` and `OLLAMA_NO_CLOUD:true`.
- **Memory** (idle, model loaded): ollama 3.91 GiB, api 45 MiB, mailpit 9 MiB. That's about 4 GiB out of 7.64 GiB.
- **Disk:** about **2.8 GB** in total.
  - Images: api 278 MB, `alpine/ollama` 121 MB, mailpit 60 MB (459 MB in all).
  - Model volume: 1.93 GB.
  - Build cache: 355 MB.
  - That is well under the 10 GB NFR.
- **Keep-alive:** the model was ready at 20:49:44 and checked at 21:00:46, after 11 min idle. `ollama ps` still listed `qwen2.5:3b … UNTIL Forever`.
- **Restart path:** `docker compose restart api` was back to `/health` 200 in **4 s**. The logs show `show → 200`, then `chat`, then ready, with no pull, and the model stayed loaded.
- **Fix made during this phase:** the ready log line said "pulled and warmed up" even when nothing was pulled. It now reads "loaded and warmed up". After the fix, lint is clean, 6/6 tests pass, and the rebuild plus `up --wait` with the model already present took **11 s** with exit 0.

### Phase 5: Docs ✅
- [x] `README.md`:
  - prerequisites (Docker Desktop or Engine with Compose v2+, 16 GB RAM, ~10 GB disk)
  - one-command start and the wait variant (`docker compose up -d --wait --wait-timeout 900`)
  - URLs (`/api/v1/docs`, `/health`, Mailpit at `:8025`)
  - stop and reset (`down`, `down -v` re-downloads the ~2 GB model)
  - measured memory and disk with the hardware they were measured on
  - a **Troubleshooting** table covering every edge case below
  - a working `curl -i http://localhost:8000/health` readiness check
  - "Sample request" and "Department boundaries" headings, each marked `TODO(next change)` and pointing to the hand-off checklist below. They must not be left as silent empty sections.
- [x] Update `context/foundation/infrastructure.md` in place. Docker is installed (versions above). The Ollama image is `alpine/ollama` and why. The VM has 8.2 GB, not 7 GB. Add the `num_ctx` reload risk to the risk register.
- [x] Update `AGENTS.md` "Current state" (compose exists; the agent and endpoint are still pending).

As built (deviations from the items above):
- **The README also has a URL table** (docs, OpenAPI schema, `/health`, Mailpit), the `503` and `200` `/health` bodies, a `curl.exe` note for Windows PowerShell, PowerShell syntax for the port override, and a short Development section (`uv sync`, pytest, ruff).
- **Measured figures name the host CPU** (Intel Core i5-10210U, 16 GB RAM) as well as the VM, and include the first-start (247 s) and restart (11 s) times. The request latency is left to the next change.
- **The PyPI proxy step is `--build-arg HTTPS_PROXY=...` only.** `HTTPS_PROXY` is a predefined Docker build arg, but the Dockerfile declares no `ARG UV_NATIVE_TLS`, and native TLS would need the corporate CA in the image anyway, so that hint was dropped here and in the integrations table.
- **`infrastructure.md`**: weaknesses 1 to 3 and their risk rows are marked resolved or re-rated with measured figures, the Getting Started steps name `alpine/ollama`, and the `num_ctx` reload risk is a new row. `AGENTS.md` also names `alpine/ollama` in the target architecture.
- **Proof:** with the stack up, `/health` returned `200 {"status":"ready","model":"qwen2.5:3b"}`, `/api/v1/docs` and `/api/v1/openapi.json` returned 200, Mailpit at `:8025` returned 200, the `503` body in the README matches `require_ready`, and `README.md` is plain ASCII (valid UTF-8).

### Phase 6: Clean-clone rehearsal — ⏭ DEFERRED (run after the triage endpoint change, before submission)
Not part of this change's verification. Kept here so the steps are documented in one place; the next change's hand-off checklist points back to it.
- [ ] `docker compose down -v` (human approval, since it deletes the model volume), fresh `git clone` into a temp dir, then run the exact README command and time it against the 15-minute NFR. Record the time in the README.
- [ ] Run the README sample curl verbatim and confirm the email in Mailpit shows the right recipient and `Reply-To`.

### Phase 7: CI on GitHub Actions ✅
Added after PR #2 merged with no checks, because the repo had no `.github/workflows/`. It follows `tech-stack.md`: "CI runs checks on GitHub Actions with manual promotion, since nothing is hosted." It gets number 7 so that existing references to Phase 6 stay valid.
- [x] New `.github/workflows/ci.yml`, triggered on `pull_request` to `main` and on `push` to `main`. `permissions: contents: read`, and `concurrency` cancels superseded runs on the same PR.
- [x] Job **`test`** (ubuntu-latest): `actions/checkout`, then `astral-sh/setup-uv` pinned to uv `0.13.1` (same as the Dockerfile) with its cache enabled, then:
  - `uv sync --locked` (Python 3.11 comes from `.python-version`)
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run pytest`
- [x] Job **`build`** (ubuntu-latest): `docker compose config -q`, then `docker compose build api`. This proves the Dockerfile and `uv.lock` still build. It doesn't run `up --wait`, because that would pull the ~2 GB model on every PR, and the faked-Ollama tests already cover the readiness logic.
- [x] Pin action versions to exact current releases (check the latest tags at implementation time). No secrets are needed.
- [x] Verify locally first: `uv sync --locked && uv run ruff check && uv run ruff format --check && uv run pytest`, then `docker compose config -q && docker compose build api`. Then open a PR and confirm that the `test` and `build` checks show up and pass.
- [ ] Human step (optional): in GitHub branch protection for `main`, mark `test` and `build` as required checks.

As built (deviations from the items above):
- **Pinned versions** (latest releases on 2026-10-15): `actions/checkout@v7.0.1` and `astral-sh/setup-uv@v10.3.0`.
- **`cancel-in-progress` applies to PR runs only**, so every push to `main` is checked to the end.
- **Branch protection is left to the repo owner** (the optional human step above), so `test` and `build` are reported on PRs but don't block merging yet.
- **Proof:**
  - Locally: `uv sync --locked`, `ruff check` and `ruff format --check` are clean, 6/6 tests pass, `docker compose config -q` passes and `docker compose build api` builds.
  - On GitHub, PR #4 run 38794759802: `test` passed in 9 s (CPython 3.11.17, 6 passed) and `build` passed in 15 s.

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
The triage endpoint, input validation (FR-002), the LangChain agent and send-email tool (FR-004 to FR-007, FR-011, FR-012), the qwen2.5:3b vs llama3.2:3b measurement and latency figure, the sample curl and the boundary table. (CI is Phase 7 of this plan.)

## Hand-off checklist for the next change (triage endpoint)

Copy these into the next change's plan as **must-have** items. The brief requires the sample request ("przykładowe zapytanie (cURL lub podobne)") and FR-010 requires both README items, so the change can't close while either is still a placeholder.
- [ ] **README sample request**: a ready-to-paste `curl` against the triage endpoint using the US-01 example (`{"email":"jan.nowak@example.com","message":"Nie działa mi komputer"}`), plus the expected response (`help-desk@example.com`) and where to see the email (Mailpit at `:8025`). Replace the `TODO(next change)` marker.
- [ ] **README department-boundary table**: all five addresses with their responsibility from PRD US-03, and example messages in Polish and English (at least the US-01 to US-03 examples). Replace the `TODO(next change)` marker.
- [ ] Verification step: run the README curl verbatim against a fresh `docker compose up -d --wait` and confirm the email in Mailpit shows the right recipient and `Reply-To`.
- [ ] Attach `require_ready` to the triage endpoint, and reuse `MODEL`/`MODEL_OPTIONS` from `readiness.py` in the agent.
- [ ] Record the measured latency (warm and after 10 min idle) with the hardware it was measured on.
- [ ] Run Phase 6 (clean-clone rehearsal) from `context/changes/deployment/deployment-plan.md`, with the sample curl included, before submission.