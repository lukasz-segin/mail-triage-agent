# First Routed Request Implementation Plan

## Overview

Roadmap slice S-01. Add `POST /api/v1/triage`: an employee submits `{email, message}`, a LangChain agent on the local Ollama model reads the intent and calls a guarded `send_email` tool, and exactly one email lands in Mailpit at the owning department with the message verbatim, `Reply-To` = sender, `From: triage-agent@example.com` and subject `[Triage] New request`. The response names the department taken from the tool's send record. This proves the PRD's primary success criterion for both examples the brief gives ("Nie działa mi komputer" → `help-desk@`, "Chciałbym zgłosić urlop na jutro" → `kadry@`), which are the ones a reviewer will try first, and carries the send guardrails (FR-005, FR-006, FR-007, FR-012), because an unguarded tool must never ship.

## Current State Analysis

- `src/mail_triage_agent/app.py:20` builds the FastAPI app with docs at `/api/v1/docs` and serves `/health` only, gated by `readiness.require_ready`.
- `src/mail_triage_agent/readiness.py:11-18` holds `MODEL` (env `OLLAMA_MODEL`, default `qwen2.5:3b`), `OLLAMA_HOST`, `MODEL_OPTIONS = {"num_ctx": 4096}` and `KEEP_ALIVE = -1`. The warm-up (`readiness.py:52`) loads the model with these values, so every model call must use the same `num_ctx` or Ollama reloads the model.
- `require_ready` (`readiness.py:77`) is already tested as a gate on a POST route (`tests/test_readiness.py:58`).
- `docker-compose.yml:8-9` already passes `SMTP_HOST=mailpit` and `SMTP_PORT=1025` to the API. Mailpit's SMTP is reachable only on the compose network, and its UI and REST API on `127.0.0.1:8025`.
- No LangChain dependency, no agent, no tool, no SMTP code. `README.md` carries two `TODO(next change)` markers ("Sample request", "Department boundaries").
- Logging is stdlib `basicConfig` at INFO (`src/mail_triage_agent/__init__.py:7`). Nothing yet prevents message content or sender addresses from reaching logs.

## Desired End State

With the stack up (`docker compose up -d --wait`):

```sh
curl -s -X POST http://localhost:8000/api/v1/triage \
  -H "Content-Type: application/json" \
  -d '{"email":"jan.nowak@example.com","message":"Nie działa mi komputer"}'
# → 200 {"department":"help-desk@example.com"}

curl -s -X POST http://localhost:8000/api/v1/triage \
  -H "Content-Type: application/json" \
  -d '{"email":"jan.nowak@example.com","message":"Chciałbym zgłosić urlop na jutro"}'
# → 200 {"department":"kadry@example.com"}
```

Each request produces exactly one new email in Mailpit at its department. The first goes to `help-desk@example.com` with `Reply-To: jan.nowak@example.com`, `From: triage-agent@example.com`, subject `[Triage] New request` and body `Nie działa mi komputer`. Before the model is ready the endpoint answers the existing 503. When the model produces no decision, the endpoint answers 502 and sends nothing. When the model times out (90 s), it answers 504 and sends nothing. CI unit tests prove the core guardrails against fakes, and an opt-in live test proves both brief examples against the real stack, 5 of 5 consecutive runs each. A text-only reply from the model is a 502, which a reviewer sees as "no email", so tool-calling reliability is part of this change's DoD, not S-02's. The Swagger "Try it out" is pre-filled with the US-01 request and shows an example response.

### Key Discoveries:

- LangChain 1.4.6 `create_agent` + `@tool` with a `ToolRuntime[Context]` parameter: the runtime context is per-invoke and invisible to the model, which makes it the place to inject the sender, the message and the send record (probed in a scratch env).
- `return_direct=True` is **not** usable: it also ends the loop on a validation error, so the model can't correct an invalid address. A `@before_model(can_jump_to=["end"])` hook that jumps to `end` once a send is recorded gives "stop right after send" and still allows correction (probed: invalid → valid sends once, no further model turn).
- Parallel tool calls in one AI message execute concurrently in separate threads (probed: different thread ids), so the once-per-request check-and-record must hold a lock.
- A tool exception other than a schema validation error or a handled `ToolException` propagates out of `invoke` unchanged (probed with a custom exception class). Refusals are `ToolException`s with `handle_tool_error=True`, so they return to the model as error messages instead of raising. Probed: a parallel second call is refused, one email is sent, and `invoke` returns normally. Nothing in the planned agent raises after a send, but `route` still decides success from the send record, not from whether `invoke` raised (FR-007, defense in depth).
- `langchain.agents.middleware.ModelCallLimitMiddleware(run_limit=..., exit_behavior="end")` exists and caps model turns per invoke.
- `ChatOllama(model=MODEL, base_url=OLLAMA_HOST, num_ctx=MODEL_OPTIONS["num_ctx"], keep_alive=KEEP_ALIVE, temperature=0, client_kwargs={"timeout": 90})` sends `options={"num_ctx": 4096, "temperature": 0}` and `keep_alive=-1`, which matches the warm-up, and sets a 90 s httpx timeout (probed).
- A `Literal[...]` argument annotation becomes a JSON-schema `enum` in the tool schema the model sees (probed).

## What We're NOT Doing

- Input validation for FR-002 (email syntax, empty or whitespace-only message, 2000-character limit) belongs to S-03. S-01 accepts any strings. A CR/LF in `email` is still refused by the stdlib email policy when the `Reply-To` header is set, so it fails with no send. That's not a clean 4xx yet; S-03 moves it up front.
- Verifying "hello?" → `other@` (US-02) and the English variants of the examples, re-checking both Polish brief examples on the final model, adjusting the prompt if one of them fails, choosing the final model across all examples, and recording the latency figure in the README. All of these belong to S-02. S-01's prompt already carries the full PRD boundaries (see `SYSTEM_PROMPT`), and S-01 proves the two Polish brief examples; S-02 only verifies the rest and adjusts.
- The README department-boundary table and the architecture notes, including why the tool takes only the department (the agent still sends the email itself through the tool) and why leave goes to `kadry@`, not `human-resources@`. Its `TODO(next change)` marker stays for S-04, and the S-04 note in the roadmap still applies.
- Re-prompting a model that answered in text without calling the tool. That path is a 502.
- Retries, outbox or queueing of failed sends (PRD Non-Goals).
- Any persistence of requests (no-retention NFR).

## Implementation Approach

All routing logic goes in one new module, `src/mail_triage_agent/triage.py`, that owns the closed address list, the prompt, the SMTP send, the tool, the agent and a single `route(email, message) -> str` entry point. `app.py` only adds the HTTP contract and maps `route`'s typed errors to status codes. The guardrails live in the tool and in `route`, not in the endpoint:

1. The tool argument is `department: Literal[<five addresses>]`, so the model sees the closed list as an enum. Schema validation rejects anything else and the error goes back to the model as a tool message. The tool body re-checks membership as defense in depth.
2. The tool takes the body and `Reply-To` from the runtime context, never from the model.
3. A per-request send record (department or `None`) plus a lock: the first valid call sends and records, and any later call refuses and sends nothing. Only real sends use the budget; rejected calls don't.
4. The `before_model` hook ends the loop once a send is recorded. `ModelCallLimitMiddleware(run_limit=3, exit_behavior="end")` bounds correction attempts.
5. `route` returns the recorded department if one exists, **even if `invoke` raised afterwards** (FR-007). Otherwise it raises "no decision" or "timeout".

**Tool-calling reliability is fixed inside S-01.** The default `qwen2.5:3b` may answer in text instead of calling the tool. If either brief example fails any of its 5 live runs (a text reply instead of a tool call, or the wrong department, such as leave going to `human-resources@`), fix it in this change, in this order, and re-run all 10:
(a) tighten `SYSTEM_PROMPT` ("You must call `send_email` exactly once. Never answer in text."), and sharpen the kadry vs HR or help-desk vs IT boundary wording, using only the PRD responsibility text;
(b) switch the model to `llama3.2:3b`: change `OLLAMA_MODEL` in `docker-compose.yml`, the default in `src/mail_triage_agent/readiness.py:11`, and the README mentions of `qwen2.5:3b`, noting that the README resource figures were measured with qwen.
Either fix stays within FR-011: no keyword routing and nothing that pre-classifies or overrides the model. If neither gets 5/5, stop and bring it to the user before changing anything else.

The endpoint is a sync `def`, so FastAPI runs it in its threadpool. `agent.invoke` and `smtplib` are both blocking, which avoids async plumbing for a PoC with less than 1 QPS.

## Critical Implementation Details

- **State sequencing (FR-007 vs FR-012):** record the department in the send record only after the SMTP `send_message` returns without error, while still holding the lock. If SMTP raises, nothing is recorded, the exception propagates and `route` reports a send failure (502). Record first and a failed send would be reported as delivered. Hold the lock across the SMTP call so a concurrent sibling call can't send a second email in the gap.
- **Privacy:** log only the delivered department, the outcome and the elapsed time. Never log the message, the sender, or `str(exc)` of exceptions that could embed them; log `type(exc).__name__` instead. Error response bodies are fixed strings that echo nothing from the request. Do not set any `LANGSMITH_*` or `LANGCHAIN_TRACING*` variable: LangChain tracing is off by default and must stay off (no data leaves the environment).
- **Verbatim body:** `EmailMessage.set_content(message)` (UTF-8) may append one trailing newline and choose a transfer encoding. Tests must compare the decoded `get_content()`, allowing exactly that one added `\n`, not the raw wire bytes.
- **Lock in the context:** the probe showed pydantic warns about a `threading.Lock` field on a dataclass context schema. Keep the lock out of pydantic's view (for example a plain class or `field(..., repr=False)` typed as `Any`) so the test output stays clean.

## Phase 1: Agent and guarded send-email tool

### Overview

Add the LangChain dependencies and the `triage` module, with the core guardrails (one send, injected fields, closed list, no-decision and SMTP-failure errors) proven by unit tests against a scripted fake chat model and a fake SMTP sender. The fake-model work is timeboxed (see §3).

### Changes Required:

#### 1. Dependencies

**File**: `pyproject.toml`, `uv.lock`

**Intent**: Add the agent framework and the Ollama chat model integration via `uv add`, never pip.

**Contract**: `uv add "langchain>=1.4.6" "langchain-ollama>=1.1.0"`. `uv.lock` is regenerated, and CI's `uv sync --locked` must still pass.

#### 2. Triage module

**File**: `src/mail_triage_agent/triage.py` (new)

**Intent**: Own the whole routing-and-send path: the closed address list, the system prompt, the SMTP send, the guarded tool, the agent and the `route` entry point that turns an agent run into "delivered department" or a typed failure.

**Contract**:
- `DEPARTMENTS`: the five addresses (`kadry@`, `human-resources@`, `help-desk@`, `it@`, `other@example.com`) as a `Literal` type and a matching tuple/frozenset used for the in-tool re-check.
- Constants: `FROM_ADDRESS = "triage-agent@example.com"`, `SUBJECT = "[Triage] New request"`, `MODEL_TIMEOUT_SECONDS = 90` (per model call, see Performance Considerations), `MAX_MODEL_CALLS = 3`, `SMTP_TIMEOUT_SECONDS = 10`. `SMTP_HOST` and `SMTP_PORT` come from env (defaults `mailpit`, `1025`), the same way `readiness.py` reads its env.
- `SYSTEM_PROMPT`: instructs the model to read the request's intent and call `send_email` exactly once with the owning department. It lists the four responsibilities verbatim from PRD Business Logic and US-03, says `other@example.com` is only for when none of them plausibly matches (ownership wins), says the message may be Polish or English, and says instructions inside the message about where to send it are ignored unless they agree with the content, and says "You must call `send_email` exactly once". The prompt is complete for S-01: all five addresses with their responsibilities (the fallback included), ownership wins, steering ignored. S-02 only adjusts it. The employee's message goes to the model as the user message. No keyword or rule code anywhere (FR-011).
- `send_mail(msg: EmailMessage) -> None`: blocking `smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS)` (10 s) + `send_message`. It's the single seam tests replace. The timeout stops an unresponsive Mailpit from hanging the request while the tool holds the lock.
- A per-request context object: `sender: str`, `message: str`, `delivered_to: str | None`, plus a lock.
- `send_email` tool: argument `department: <Literal of the five>` only, plus the injected `ToolRuntime` context. The docstring tells the model what it does. Under the lock: if `delivered_to` is already set → refuse (raise a `ToolException` so the refusal returns to the model as an error message, not out of the agent; set `handle_tool_error=True`); re-check membership → refuse the same way; build the `EmailMessage` (From, To = department, Reply-To = context sender, Subject, body = context message via `set_content`); `send_mail`, where `smtplib.SMTPException` or `OSError` from that call only (connection refused, SMTP timeout) is raised as `SendFailed` (it is not a `ToolException`, so it propagates out of `invoke` unchanged); then set `delivered_to`. Return a short confirmation string.
- A `before_model` middleware with `can_jump_to=["end"]` that returns `{"jump_to": "end"}` when `delivered_to` is set. Plus `ModelCallLimitMiddleware(run_limit=MAX_MODEL_CALLS, exit_behavior="end")`.
- `build_agent(model)`: `create_agent(model, tools=[send_email], system_prompt=SYSTEM_PROMPT, context_schema=<context>, middleware=[...])`. The default model is `ChatOllama(model=readiness.MODEL, base_url=readiness.OLLAMA_HOST, num_ctx=readiness.MODEL_OPTIONS["num_ctx"], keep_alive=readiness.KEEP_ALIVE, temperature=0, client_kwargs={"timeout": MODEL_TIMEOUT_SECONDS})`, built once at module level (or lazily). `validate_model_on_init` stays off, so importing the module never calls Ollama.
- `route(email: str, message: str, agent=<default>) -> str`: create a fresh context, `invoke` with it, and return `context.delivered_to` if set, **whether or not `invoke` raised**. If nothing was delivered: a `TriageError` raised by the tool (`SendFailed`) passes through, `httpx.TimeoutException` raises `RoutingTimeout`, and anything else raises `NoDecision`. That includes the loop ending without a send and Ollama being unreachable. Don't classify by `OSError`: Ollama's `ConnectionError` is an `OSError` subclass and would be reported as a send failure. Log one line: outcome, department (if any), elapsed ms.
- Exceptions: `RoutingTimeout`, `SendFailed`, `NoDecision`, all subclasses of a `TriageError` base.

#### 3. Unit tests

**File**: `tests/test_triage.py` (new)

**Intent**: Prove each guardrail and failure path deterministically, with no Ollama and no SMTP server.

**Contract**: A scripted fake chat model: `GenericFakeChatModel` subclass whose `bind_tools` returns `self`, fed a list of `AIMessage`s with `tool_calls`. This exact pattern worked in this session's scratch probes (`probe2.py`, `probe3.py`), so start from it. `send_mail` is monkeypatched to capture `EmailMessage`s (or to raise).

**Timebox (last review):** the reviewer grades the working endpoint, the email in Mailpit and the README, not unit-test completeness. Write only the 5 necessary tests below. If scripting the fake model takes more than about 30–45 minutes, commit what passes, skip the rest, and go on to Phase 2. The live test in Phase 2 is the DoD proof and is never skipped.

Necessary (only 1–3 script the fake model):
- `test_valid_call_sends_one_email_with_injected_fields` (FR-005, FR-006): To = chosen address; Reply-To = sender; From and Subject are the constants; decoded body = message verbatim (allowing one trailing `\n`); `route` returns the address.
- `test_parallel_second_call_sends_nothing` (FR-012): one AI message with two valid calls → exactly one email, and `route` returns the first delivered address (success, despite the refused sibling).
- `test_no_tool_call_raises_no_decision_and_sends_nothing` (FR-007): a text-only AI reply.
- `test_smtp_failure_raises_send_failed_and_records_nothing` (FR-007): one valid tool call, `send_mail` raises `smtplib.SMTPException` → `SendFailed`, `delivered_to` stays `None`.
- `test_model_cannot_set_body_or_reply_to` (FR-012): the tool schema exposes `department` only, with an enum of exactly the five addresses. Schema check, no model.

Deferred, write only if time remains after Phase 2 passes, in this order. The behaviours themselves stay in the contract above; only their tests wait:
- `test_logs_contain_no_message_or_sender` (`caplog`): a success and a failure leave no message text or sender in any record. Until then, manual check 2.8 covers it.
- `test_default_model_matches_warm_up_settings`: the default `ChatOllama` has `num_ctx == MODEL_OPTIONS["num_ctx"]`, `keep_alive == KEEP_ALIVE` and model `== readiness.MODEL`.
- `test_invalid_address_sends_nothing_then_valid_call_succeeds`: `it@exmple.com` → no send, then `it@example.com` → one send (behaviour probed this session).
- `test_timeout_raises_routing_timeout`: the fake model raises `httpx.ReadTimeout`.
- `test_ollama_unreachable_raises_no_decision`: the fake model raises `ConnectionError` → `NoDecision`, not `SendFailed`.
- `test_failure_after_send_is_still_success`: a stub agent passed via `route(..., agent=stub)` whose `invoke` sets `delivered_to` and then raises → `route` returns the department.
- `test_model_call_limit_raises_no_decision`: repeated invalid calls → `NoDecision`, zero emails, at most `MAX_MODEL_CALLS` model turns (behaviour probed this session).

### Success Criteria:

#### Automated Verification:

- Dependencies lock and install: `uv sync --locked`
- Lint and format are clean: `uv run ruff check` and `uv run ruff format --check`
- All tests pass, existing readiness tests included: `uv run pytest`

#### Manual Verification:

- Read `SYSTEM_PROMPT` against PRD Business Logic: all four responsibilities, the fallback rule and the steering rule are present, and the code contains no keyword or rule-based routing

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase. "All tests pass" means the tests that exist: if the timebox in §3 cut the necessary set short, the passing subset doesn't block Phase 2. Say which tests were skipped.

---

## Phase 2: Endpoint, live check and docs

### Overview

Expose `route` over HTTP behind the readiness gate, prove both brief examples end to end against the real stack (computer → `help-desk@`, leave → `kadry@`), and give the reviewer a ready-to-paste sample request.

### Changes Required:

#### 1. Triage endpoint

**File**: `src/mail_triage_agent/app.py`

**Intent**: Add the public contract and map routing failures to explicit errors (FR-003, FR-006, FR-007).

**Contract**:
- `POST /api/v1/triage`, `dependencies=[Depends(readiness.require_ready)]`, sync `def`.
- Request model `TriageRequest {email: str, message: str}` (plain strings; S-03 tightens) with an OpenAPI example of the US-01 payload, so the docs at `/api/v1/docs` come pre-filled (FR-009).
- Response model `TriageResponse {department: str}`: the value `route` returns, which comes from the send record. It also carries an OpenAPI example `{"department": "help-desk@example.com"}`, so the docs show the expected response next to the pre-filled request.
- Errors as `HTTPException` with a fixed `detail` string that never echoes the input: `NoDecision` → 502 ("no department decision was produced; no email was sent"), `SendFailed` → 502 ("sending the email failed; no email was sent"), `RoutingTimeout` → 504 ("the model did not answer in time; no email was sent"). Not ready → the existing 503 from `require_ready`.

#### 2. Endpoint tests

**File**: `tests/test_triage_api.py` (new)

**Intent**: Prove the HTTP contract without the model.

**Contract**: Monkeypatch `triage.route` and `readiness.state`; no fake model. Three tests: 200 with `{"department": ...}` from `route`; one parametrized test where `NoDecision` and `SendFailed` → 502 and `RoutingTimeout` → 504, each with a fixed body containing no request content; 503 while not ready, with `route` never called. Deferred (only if time remains): asserting that `/api/v1/openapi.json` contains the US-01 request and response examples; manual checks 2.7 and 2.12 cover it until then.

#### 3. Opt-in live test

**File**: `tests/test_live.py` (new), `pyproject.toml` (pytest marker registration)

**Intent**: A repeatable end-to-end check of both brief examples against the running stack. S-02 reuses it and adds its own cases.

**Contract**: Marked `live` and skipped unless env `LIVE_STACK=1`, so CI never runs it. Run with `LIVE_STACK=1 uv run pytest -m live -s` (POSIX) or `$env:LIVE_STACK=1; uv run pytest -m live -s` (PowerShell). Parametrized over two cases, `("Nie działa mi komputer", "help-desk@example.com")` and `("Chciałbym zgłosić urlop na jutro", "kadry@example.com")`, × `run` in `range(LIVE_RUNS)` (env, default 5): 10 runs, and every run must pass, so one lucky run can't hide an unreliable model. Steps per run: count the Mailpit messages via its REST API on `http://localhost:8025/api/v1/messages`; POST `{"email": "jan.nowak@example.com", "message": <case message>}` to `http://localhost:8000/api/v1/triage`; assert 200 and the case's expected department; assert exactly one new Mailpit message and fetch it: To = the expected department, Reply-To = `jan.nowak@example.com`, From = `triage-agent@example.com`, Subject = `[Triage] New request`, text body = the message. Print the elapsed request time. It must not delete Mailpit messages. Uses stdlib `urllib` or the dev HTTP client already installed. No new dependency.

#### 4. README sample request

**File**: `README.md` (must stay UTF-8)

**Intent**: Replace the "Sample request" `TODO(next change)` marker with the brief's mandatory ready-to-paste request.

**Contract**: In this order: first the classic `curl -X POST http://localhost:8000/api/v1/triage -H "Content-Type: application/json" -d '{...}'` with the US-01 payload for bash/zsh (the brief asks for "cURL lub podobne", and reviewers most likely use Linux or macOS); then, below it, a Windows PowerShell variant that uses `Invoke-RestMethod -Method Post -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))`. Don't use `curl.exe` for this request: in Windows PowerShell 5.1 it strips the JSON's inner double quotes and sends "ł" as cp1250, which gives an invalid body and a 422 (verified with curl 8.4.0 against an echo server). Say that the existing "type `curl.exe`" hint applies to `/health` only. Then: the expected `200 {"department":"help-desk@example.com"}`, where to see the email (Mailpit `http://localhost:8025`, check To and Reply-To), the 502/504/503 meanings in one short list, a note that 504 fires when a single model call exceeds 90 s, and a pointer that the request can also be sent from `/api/v1/docs` (pre-filled). Add the endpoint to the URL table. The "Department boundaries" TODO stays (S-04). Remove "The request latency figure comes with the triage endpoint." only if S-02 records it; otherwise leave it.

#### 5. AGENTS.md current state

**File**: `AGENTS.md`

**Intent**: Keep the onboarding doc truthful: the endpoint, agent and tool now exist, and LangChain has been added.

**Contract**: The "Current state" section names `triage.py`, the `/api/v1/triage` endpoint and the live test (`LIVE_STACK=1 uv run pytest -m live -s`, PowerShell `$env:LIVE_STACK=1; uv run pytest -m live -s`), and moves those items out of "Still pending". The model comparison, the latency figure, input validation and the boundary table stay pending.

### Success Criteria:

#### Automated Verification:

- Lint and format are clean: `uv run ruff check` and `uv run ruff format --check`
- Unit and API tests pass (live test skipped): `uv run pytest`
- Compose config is valid and the API image builds: `docker compose config -q` and `docker compose build api`
- Live US-01 test passes against the running stack: `docker compose up -d --build --wait --wait-timeout 900`, then `LIVE_STACK=1 uv run pytest -m live -s` (PowerShell: `$env:LIVE_STACK=1; uv run pytest -m live -s`). Note: the 5/5 repeat requirement is item 2.11.
- README is still valid UTF-8: `uv run python -c "open('README.md', encoding='utf-8').read()"`
- Live US-01 test passes 5 of 5 consecutive runs (`LIVE_RUNS=5`); on any failure apply the in-change fix path and re-run (added after external review; makes the live test above repeatable)
- Live test passes 5 of 5 consecutive runs for the leave example too ("Chciałbym zgłosić urlop na jutro" → `kadry@example.com`); on any failure apply the in-change fix path and re-run (added after the second external review; with the item above, it covers both brief examples)

#### Manual Verification:

- The README sample curl, pasted verbatim, returns `{"department":"help-desk@example.com"}`, and Mailpit at `http://localhost:8025` shows one new email with the right To, `Reply-To`, From, subject and unaltered body
- The README Windows PowerShell variant, pasted verbatim into Windows PowerShell 5.1, returns the same response, and the Mailpit body shows "Nie działa mi komputer" with the "ł" intact
- `/api/v1/docs` shows example values for both the request and the response
- `/api/v1/docs` shows `POST /api/v1/triage` pre-filled with the US-01 example and "Try it out" succeeds
- `docker compose logs api` after a request shows the department and elapsed time, and neither the message text nor the sender address
- The elapsed time of a warm US-01 request is noted (input for S-02's latency figure)

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Testing Strategy

### Unit Tests:

Necessary set, timeboxed at about 30–45 minutes of fake-model work (see Phase 1 §3):
- Tool guardrails: closed-list enum, model cannot supply body or `Reply-To`, injected fields, parallel calls send once.
- Failure semantics: a text-only reply → `NoDecision`; SMTP failure → nothing recorded, `SendFailed`.
- HTTP mapping: 200/502/504/503 and fixed error bodies.

Deferred until time remains: privacy in logs (manual 2.8 for now), settings parity with the warm-up, correction after an invalid address, timeout, unreachable Ollama, failure after send, the model-call cap and the OpenAPI examples (manual 2.7/2.12 for now).

### Integration Tests:

- `tests/test_live.py` (opt-in, `LIVE_STACK=1`): both brief examples through the real stack (computer → `help-desk@`, leave → `kadry@`), 5 consecutive runs each (`LIVE_RUNS`), with each email read back from Mailpit's REST API.

### Manual Testing Steps:

1. `docker compose up -d --build --wait --wait-timeout 900`.
2. Paste the README curl. Expect `{"department":"help-desk@example.com"}`.
3. Open `http://localhost:8025`: one new email to `help-desk@example.com`, `Reply-To: jan.nowak@example.com`, body `Nie działa mi komputer`.
4. Send the same request with `"message":"Chciałbym zgłosić urlop na jutro"`. Expect `{"department":"kadry@example.com"}` and one new email there in Mailpit.
5. Repeat from `/api/v1/docs` "Try it out".
6. `docker compose logs api | tail`: department and timing only.

## Performance Considerations

Stopping right after the send saves one full CPU model turn per request. Temperature 0 and the shared `num_ctx` avoid a model reload. The 90 s timeout is a hang guard, not the 30 s NFR. S-02 measures against the NFR.

The 90 s timeout applies to **each model call**, not to the whole request (decided at plan review, F3). The usual path is one model call, because the agent stops right after the send. A request on the correction path (rejected address, then retry) makes at most `MAX_MODEL_CALLS = 3` calls, so its worst case is about 3 × 90 s before it fails with 504 or 502. The README states this.

## Migration Notes

None. No data, no schema. Rollback is reverting the change; the stack and readiness gate are untouched.

## References

- Roadmap slice: `context/foundation/roadmap.md` (S-01)
- PRD: `context/foundation/prd.md` (US-01, US-03 leave example, FR-001 to FR-007, FR-011, FR-012, NFRs)
- Deployment hand-off checklist: `context/changes/deployment/deployment-plan.md:214`
- Readiness gate and shared model settings: `src/mail_triage_agent/readiness.py:11-18`, `:77`
- Gate test pattern: `tests/test_readiness.py:58`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Agent and guarded send-email tool

#### Automated

- [x] 1.1 Dependencies lock and install: `uv sync --locked` — d5e910f
- [x] 1.2 Lint and format are clean: `uv run ruff check` and `uv run ruff format --check` — d5e910f
- [x] 1.3 All tests pass, existing readiness tests included: `uv run pytest` — d5e910f

#### Manual

- [x] 1.4 Read `SYSTEM_PROMPT` against PRD Business Logic: all four responsibilities, the fallback rule and the steering rule are present, and the code contains no keyword or rule-based routing — d5e910f

### Phase 2: Endpoint, live check and docs

#### Automated

- [x] 2.1 Lint and format are clean: `uv run ruff check` and `uv run ruff format --check`
- [x] 2.2 Unit and API tests pass (live test skipped): `uv run pytest`
- [x] 2.3 Compose config is valid and the API image builds: `docker compose config -q` and `docker compose build api`
- [x] 2.4 Live US-01 test passes against the running stack: `docker compose up -d --build --wait --wait-timeout 900`, then `LIVE_STACK=1 uv run pytest -m live -s` (PowerShell: `$env:LIVE_STACK=1; uv run pytest -m live -s`)
- [x] 2.5 README is still valid UTF-8: `uv run python -c "open('README.md', encoding='utf-8').read()"`
- [x] 2.11 Live US-01 test passes 5 of 5 consecutive runs (`LIVE_RUNS=5`); on any failure apply the in-change fix path and re-run
- [x] 2.13 Live test passes 5 of 5 consecutive runs for the leave example too ("Chciałbym zgłosić urlop na jutro" → `kadry@example.com`); on any failure apply the in-change fix path and re-run

#### Manual

- [x] 2.6 The README sample curl, pasted verbatim, returns `{"department":"help-desk@example.com"}`, and Mailpit shows one new email with the right To, `Reply-To`, From, subject and unaltered body
- [x] 2.7 `/api/v1/docs` shows `POST /api/v1/triage` pre-filled with the US-01 example and "Try it out" succeeds
- [x] 2.8 `docker compose logs api` after a request shows the department and elapsed time, and neither the message text nor the sender address
- [x] 2.9 The elapsed time of a warm US-01 request is noted (input for S-02's latency figure)
- [x] 2.10 The README Windows PowerShell variant, pasted verbatim into Windows PowerShell 5.1, returns the same response, and the Mailpit body shows "Nie działa mi komputer" with the "ł" intact
- [x] 2.12 `/api/v1/docs` shows example values for both the request and the response
