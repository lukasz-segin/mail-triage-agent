# First Routed Request — Plan Brief

> Full plan: `context/changes/first-routed-request/plan.md`

## What & Why

Roadmap slice S-01: an employee submits `{email, message}` and the request arrives, unaltered, at the owning department. A LangChain agent on the local Ollama model decides the department by reading the intent, and sends the email through a guarded `send_email` tool. This is the PRD's primary success criterion, proven on both examples the brief gives ("Nie działa mi komputer" → `help-desk@`, "Chciałbym zgłosić urlop na jutro" → `kadry@`), because those are what a reviewer will try first. The send guardrails ship with it because an unguarded tool must never ship.

## Starting Point

The Compose stack (api, `alpine/ollama`, Mailpit) runs and becomes healthy. `readiness.py` provides the `require_ready` "not ready" gate and the shared `MODEL`/`MODEL_OPTIONS`. The API only serves `/health` and the docs. There's no LangChain, no agent, no tool and no SMTP code yet.

## Desired End State

`POST /api/v1/triage` with the US-01 example returns `{"department":"help-desk@example.com"}`, and with the leave example returns `{"department":"kadry@example.com"}`. Each time Mailpit shows exactly one email there with the body verbatim, `Reply-To` = sender, the fixed `From` and subject. Not ready → 503, no decision → 502, model timeout → 504, and none of these sends anything. The live test passes 5 of 5 consecutive runs for each of the two brief examples. The README has a ready-to-paste sample curl, and `/api/v1/docs` is pre-filled with the request and shows an example response.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) |
| --- | --- | --- |
| Tool argument | `department: Literal[<five addresses>]`, plus a re-check in the tool | The model sees the closed list as an enum, and the record is the address the PRD expects. |
| Send budget | Only real sends count; rejected calls let the model correct itself | FR-012 limits emails, not attempts; a typo shouldn't fail the request. |
| Termination | A `before_model` hook ends the loop once a send is recorded (not `return_direct`) | Saves a CPU model turn and removes failure points after delivery; `return_direct` was shown to block correction. |
| Retry cap | `ModelCallLimitMiddleware(run_limit=3, exit_behavior="end")` | A model that keeps getting rejected can't loop forever. |
| No tool call | 502 "no decision", no email, no re-prompt | Exactly FR-007. |
| Tool-calling reliability | S-01 is done only when both brief examples pass 5/5 in the live test; fix by prompt, then `llama3.2:3b` | A 502 or a wrong department fails the reviewer's DoD; it can't wait for S-02 (external review). |
| Live test cases | The brief's two examples (computer → `help-desk@`, leave → `kadry@`) in S-01; "hello?", English variants and the final-model regression check stay in S-02 | A reviewer tries exactly these two; S-02 is sequenced late and most exposed to running out of time (second external review). |
| Prompt | Full PRD boundaries in S-01: five addresses with responsibilities, ownership wins, steering ignored, "call `send_email` exactly once" | Without them "Nie działa mi komputer" could go to `it@`; S-02 only verifies and adjusts. |
| Success rule | `route` returns the recorded department even if the agent raised after the send | FR-007: once delivered, the request succeeded (the parallel-call probe made this real). |
| API contract | `POST /api/v1/triage` → `{"department": ...}`; 502/504/503 with fixed bodies | Sits next to `/api/v1/docs`; no resource noun, since nothing is stored. |
| Timeout | 90 s per Ollama call → 504; SMTP 10 s → 502 | Hang guards; usual path is 1 model call, worst case 3 × 90 s on the correction path (plan review F3). |
| Failure classification | Tool raises `SendFailed` itself; `route` never classifies by `OSError` | Ollama's `ConnectionError` is an `OSError` and would read as a send failure (plan review F2). |
| README sample | bash/zsh `curl` first; Windows `Invoke-RestMethod` with UTF-8 bytes second, not `curl.exe` | The brief asks for cURL and reviewers likely use Linux or macOS; PS 5.1 + curl.exe strips JSON quotes and sends "ł" as cp1250 → 422 (verified; plan review F1). |
| Swagger examples | Request and response models both carry the US-01 example | "Try it out" is pre-filled, and the reviewer sees the expected answer. |
| Model settings | `ChatOllama` with warm-up's `num_ctx`, `keep_alive=-1`, `temperature=0` | Same `num_ctx` avoids a reload; temperature 0 gives stable routing on repeats. |
| Testing | 5 core tests (3 with a scripted fake model, plus SMTP failure and the tool schema) + 3 API tests in CI, fake-model work timeboxed at 30–45 min; other unit tests deferred; the opt-in live test via Mailpit's API (both brief examples, 5/5) is the DoD proof | The reviewer grades the endpoint, the email and the README, not unit-test completeness; guardrails can't be forced from a real model (last review). |
| README | Sample curl now; boundary table stays for S-04 | The brief's mandatory sample request exists as soon as S-01 merges. |

## Scope

**In scope:** LangChain dependencies; `triage.py` (closed list, full-boundary prompt, SMTP send, guarded tool, middleware, `route`); `POST /api/v1/triage` behind `require_ready`; unit, API and opt-in live tests (both brief examples passing 5/5, including the leave example → `kadry@`, US-03); tool-calling reliability (prompt, then a model switch if needed); the README sample request; Swagger request and response examples; the AGENTS.md current-state update; no message or sender in logs.

**Out of scope:** FR-002 input validation (S-03); "hello?" (US-02), the English variants, the final-model regression check, the final model choice and the latency figure (S-02); the README boundary table and architecture notes, including the tool-design explanation (S-04); re-prompting at runtime; retries or outbox; any storage.

## Architecture / Approach

`app.py` → `triage.route(email, message)` → `create_agent(ChatOllama, [send_email], middleware=[stop-after-send, model-call-limit])` invoked with a per-request context (sender, message, `delivered_to`, lock). The model sees only the message and the `department` enum. The tool injects the body and `Reply-To` from the context, sends via `smtplib` to Mailpit, and records `delivered_to` under a lock only after SMTP succeeds. `route` returns `delivered_to` or raises `NoDecision`, `SendFailed` or `RoutingTimeout`, which the endpoint maps to 502/502/504.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Agent and guarded tool | `triage.py` and core guardrail tests against fakes (timeboxed) | Fake-model scripting; timeboxed at 30–45 min, then go on to Phase 2 |
| 2. Endpoint, live check, docs | `/api/v1/triage`, live test passing 5/5 for both brief examples, README curl, AGENTS.md | `qwen2.5:3b` not calling the tool reliably; fixed inside this phase (prompt, then `llama3.2:3b`) |

**Prerequisites:** none; the stack and readiness gate exist.
**Estimated effort:** ~1 session across 2 phases.

## Open Risks & Assumptions

- The default `qwen2.5:3b` may answer in text instead of calling the tool. The live test (5/5) catches it, and S-01 fixes it: first the prompt, then a switch to `llama3.2:3b` (compose `OLLAMA_MODEL`, the readiness default, README mentions). If neither reaches 5/5, stop and decide with the user.
- The leave example can land at `human-resources@` instead of `kadry@` (kadry vs HR overlap). Same live test, same fix path: sharpen the boundary wording from the PRD text, then switch the model.
- CI unit coverage is deliberately thin: 5 core tests + 3 API tests. Seven guardrail tests (logs, settings parity, correction, timeout, Ollama unreachable, failure after send, call limit) are deferred until time remains; the behaviours are still implemented, and the probes plus manual checks cover them for now.
- S-01 accepts unvalidated strings until S-03; a CR/LF in `email` fails safely (no send) but not as a clean 4xx.
- Ollama runs one request at a time (`OLLAMA_NUM_PARALLEL=1`), so concurrent requests queue. That's acceptable at less than 1 QPS.

## Success Criteria (Summary)

- The README curl for US-01 returns `help-desk@example.com`, the leave example returns `kadry@example.com`, and Mailpit shows one email per request with the right recipient, `Reply-To`, `From`, subject and verbatim body.
- No path ever sends to an address outside the five or sends twice, and every failure returns an explicit error with no email (proved in CI).
- Logs show only the department and timing, never message content or sender.
