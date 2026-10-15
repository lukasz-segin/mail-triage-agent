# AGENTS.md

## Project

Mail Triage Agent: a proof-of-concept HTTP API that reads an employee's free-text request (Polish or English) and has a local LLM agent forward it by email to one of five department inboxes. The original brief is [idea-notes.md](idea-notes.md). The binding product contract is [context/foundation/prd.md](context/foundation/prd.md), and the stack hand-off is [context/foundation/tech-stack.md](context/foundation/tech-stack.md). Hard deadline: 2026-10-16.

## Current state

The Compose stack runs and becomes healthy: [docker-compose.yml](docker-compose.yml) (api, `alpine/ollama`, Mailpit) and the [Dockerfile](Dockerfile). The API ([src/mail_triage_agent/app.py](src/mail_triage_agent/app.py)) serves `/health`, the docs and `POST /api/v1/triage`, which maps routing failures to 502/504. [triage.py](src/mail_triage_agent/triage.py) owns the routing path: the closed address list, the system prompt, the LangChain agent on `ChatOllama`, the guarded `send_email` tool (model supplies only the department; body and `Reply-To` injected; one send per request) and `route()`, which returns the department from the send record. [readiness.py](src/mail_triage_agent/readiness.py) pulls and warms up the model in the background and provides the `require_ready` dependency (FR-003), plus `MODEL` and `MODEL_OPTIONS`, which every model call must reuse so Ollama doesn't reload the model. Tests live in `tests/` (`uv run pytest`). The opt-in live test runs both brief examples 5 times each against the running stack: `LIVE_STACK=1 uv run pytest -m live -s` (PowerShell: `$env:LIVE_STACK=1; uv run pytest -m live -s`). CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs ruff, pytest and the API image build on every PR and push to `main`; run the same commands locally before pushing.

Still pending: input validation (FR-002; the endpoint accepts any strings for now), the model comparison and latency figure, and the README department table (marked `TODO(next change)`).

## Commands

Manage dependencies and run code only through `uv` (`uv add <pkg>`, `uv sync`, `uv run mail-triage-agent`). Never `pip install` into `.venv`.

Lint and format with ruff (dev dependency, default rules): `uv run ruff check` and `uv run ruff format`.

`README.md` must stay UTF-8. The `uv_build` backend fails on UTF-16, which broke the first bootstrap attempt.

## Target architecture (from the PRD and tech-stack hand-off)

- **Compose**: one `docker-compose.yml` with three services: the API (official `python` image), `alpine/ollama` (CPU-only; the official image is 3.78 GB) and `axllent/mailpit` as the email-capture server. `docker compose up -d` must pull and warm up the model. The API's `/health` healthcheck reports ready only after warm-up, and requests before that get an explicit "not ready" response (FR-003).
- **Model choice**: pick the smallest tool-calling model (candidates: `qwen2.5:3b`, `llama3.2:3b`) that routes every PRD US-01 to US-03 acceptance example to the correct department and answers in under 30 s per request on CPU only, once ready (PRD NFR). Record the measured figure in the README.
- **API**: FastAPI, with interactive docs at `/api/v1/docs` (a hard requirement from the brief). One endpoint takes `{ email, message }`. It validates the email syntax and rejects empty, whitespace-only and over-2000-character messages before sending anything (FR-002).
- **Agent**: a LangChain agent backed by Ollama decides the department. Routing must come from the model reading intent: no keyword or rule-based routing, and no code that pre-classifies or overrides the decision (FR-011).
- **Send-email tool**: the email must be sent through tool calling, and this tool is where the guardrails live (FR-005, FR-012):
  - The model supplies only the department. The tool injects the body (the original message, verbatim) and `Reply-To` (the sender) from the request.
  - `From: triage-agent@example.com`, subject `[Triage] New request`.
  - Any address outside the closed list is rejected: `human-resources@`, `help-desk@`, `it@`, `kadry@`, `other@example.com` (fallback only when none of the four responsibilities match).
  - At most one send per request. Further calls within the same request fail and send nothing.
  - The response returns the department taken from the tool's execution record (where the email actually went), not the model's stated answer (FR-006).
- **Failure semantics**: if the decision or the send fails, return an error and send no email. Once the email is sent, the request counts as a success (FR-007).
- **Privacy**: message content and sender addresses are never written to logs or stored. Nothing leaves the local environment.

Department boundaries and the acceptance examples are in PRD US-01 to US-03. The README must eventually include run instructions, a sample curl request, and a department boundary table (FR-010).

## Workflow (`context/`)

`context/foundation/` holds living project docs, `context/changes/<change-id>/` holds in-flight changes, and `context/archive/` holds completed ones. Each folder's `README.md` states its conventions.

Never write to `context/archive/`. Archived changes are immutable; if a target path starts with `context/archive/`, stop and open a new change with `/10x-new` instead.
