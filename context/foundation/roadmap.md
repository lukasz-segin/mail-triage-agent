---
project: Mail Triage Agent
version: 1
status: draft
created: 2026-10-15
updated: 2026-10-15
prd_version: 1
main_goal: speed
top_blocker: time
milestone_id: reviewer-ready-poc
milestone_seq: 1
milestone_status: open
---

# Roadmap: Mail Triage Agent

> Derived from `context/foundation/prd.md` (v1) + auto-researched codebase baseline.
> Edit-in-place; archive when superseded.
> Slices below are listed in dependency order. The "At a glance" table is the index.

## Milestone

**M-1: Reviewer-ready proof of concept** — Status: open

- **Intent:** A reviewer clones the repo, starts it with one command, sends a free-text request and sees one email in the mail-capture UI at the right department with `Reply-To` set to the sender. Every PRD acceptance example routes correctly, and the README is complete.
- **Source materials:** `context/foundation/prd.md` (v1)
- **Done when:** every S-NN below is `done`.
- **Scope anchors:** US-01 to US-04; FR-001 to FR-012; all PRD non-functional requirements.

## Vision recap

An employee with a request doesn't know which of five overlapping department inboxes (kadry, HR, help-desk, IT, plus a catch-all) owns it, so requests get misrouted, duplicated or lost. The product reads the free-text message (Polish or English), lets a local AI model decide the owning department by intent rather than keywords, and forwards the original message there by email. When nothing matches, it goes to the fallback inbox instead of a guessed department.

## North star

**S-01: An employee's request reaches the right department** — the north star is the smallest end-to-end flow whose success proves the product works, so it goes first. Here that means one request, one model decision, one tool-driven email in the mail-capture UI with the right recipient and `Reply-To`. It is the PRD's primary success criterion verbatim, and every later slice only tunes or packages it.

## At a glance

| ID   | Change ID                     | Outcome (user can …)                                                                 | Prerequisites | PRD refs                                                              | Status   |
| ---- | ----------------------------- | ------------------------------------------------------------------------------------ | ------------- | --------------------------------------------------------------------- | -------- |
| S-01 | first-routed-request          | employee can submit a request and it arrives, unaltered, at the owning department     | —             | US-01, FR-001, FR-003, FR-004, FR-005, FR-006, FR-007, FR-011, FR-012 | ready    |
| S-02 | boundary-and-fallback-routing | employee's boundary and unclear requests route per the stated rules, in PL and EN    | S-01          | US-02, US-03, FR-004, FR-011                                          | proposed |
| S-03 | input-validation              | caller gets a clear error for bad input, and no email is sent                         | S-01          | US-04, FR-002                                                         | proposed |
| S-04 | reviewer-handoff              | reviewer can go from a fresh clone to a verified request using only the README        | S-02, S-03    | FR-008, FR-009, FR-010                                                | proposed |

## Baseline

What's already in place in the codebase as of 2026-10-15 (auto-researched + user-confirmed).
Foundations below assume these are present and do NOT re-scaffold them.

- **Frontend:** absent by design — no own UI; interactive API docs at `/api/v1/docs` (`src/mail_triage_agent/app.py`) and the Mailpit web UI are the only surfaces.
- **Backend / API:** partial — FastAPI app with `/health` and docs (`app.py`); model pull + warm-up and the `require_ready` "not ready" gate, plus the shared `MODEL` / `MODEL_OPTIONS` (`readiness.py`). No triage endpoint, agent or send-email tool yet.
- **Data:** absent by design — PRD forbids storing requests.
- **Auth:** absent by design — PRD Access Control: no authentication; the API is published on `127.0.0.1` only (`docker-compose.yml`).
- **Deploy / infra:** present — Compose stack (api, `alpine/ollama`, Mailpit) with a healthcheck that turns ready only after warm-up; `Dockerfile`; CI runs ruff, pytest and the image build (`.github/workflows/ci.yml`). Pending: the clean-clone rehearsal (Phase 6 of the `deployment` change).
- **Observability:** partial — stdlib logging configured (`src/mail_triage_agent/__init__.py`); nothing yet guards against message content or sender addresses reaching logs.

## Foundations

None. The baseline already provides the Compose stack, the readiness gate and CI. The only missing cross-cutting pieces (the agent, the send-email tool, the no-content logging rule) are first needed by S-01 and are introduced there.

## Slices

### S-01: An employee's request reaches the right department

- **Outcome:** user can submit `{ email, message }` and, for the US-01 example, see exactly one email in the mail-capture UI at `help-desk@example.com`. The email has the message verbatim, `Reply-To` = sender, the fixed `From` and subject, and the response names the department the tool actually delivered to. Picks up the `deployment` change's hand-off items for the endpoint: the readiness gate and the shared model settings.
- **Change ID:** first-routed-request
- **PRD refs:** US-01, FR-001, FR-003, FR-004, FR-005, FR-006, FR-007, FR-011, FR-012, NFR (no data leaves the environment; no content or sender in logs)
- **Prerequisites:** —
- **Parallel with:** —
- **Blockers:** —
- **Unknowns:**
  - Does the default candidate model call the send tool reliably with only the department as its argument? — Owner: user. Block: no (S-02 owns the final model choice).
- **Risk:** Carries most must-have FRs because the PRD has a single workflow and FR-005/006/007/012 are guardrails of that one send, so splitting them would ship an unguarded tool. Sequenced first because every other slice tunes or documents this flow.
- **Status:** ready

### S-02: Boundary and unclear requests route per the stated rules

- **Outcome:** user can send the US-02 and US-03 acceptance examples, in Polish and English, and each lands at the department the PRD boundaries name. "hello?" goes to `other@example.com`, the leave request to `kadry@example.com`, the broken computer to `help-desk@example.com`. The smallest candidate model that passes all of them in under 30 s on CPU is chosen, and the measured figure is recorded.
- **Change ID:** boundary-and-fallback-routing
- **PRD refs:** US-02, US-03, FR-004, FR-011, NFR (Polish and English; < 30 s per request on CPU)
- **Prerequisites:** S-01
- **Parallel with:** S-03
- **Blockers:** —
- **Unknowns:**
  - Which candidate model (per `tech-stack.md`) passes every US-01 to US-03 example under 30 s, both warm and after idle? — Owner: user. Block: no (resolved by measurement inside the slice).
- **Risk:** This is where a small CPU model is most likely to fail (kadry vs HR, help-desk vs IT, knowing when to fall back). Routing must improve only through the model's instructions, never through keyword rules (FR-011).
- **Status:** proposed

### S-03: Bad input is rejected with a clear error

- **Outcome:** user who submits a malformed email address, an empty or whitespace-only message, or a message over 2000 characters gets an error naming the problem, and no email appears in the mail-capture UI.
- **Change ID:** input-validation
- **PRD refs:** US-04, FR-002
- **Prerequisites:** S-01
- **Parallel with:** S-02
- **Blockers:** —
- **Unknowns:** —
- **Risk:** Small and low-risk; kept separate so S-01 stays focused on the send path. Rejection must happen before the model is called, so an invalid request costs no inference time.
- **Status:** proposed

### S-04: A reviewer can verify the product from the README alone

- **Outcome:** reviewer can follow the README on a fresh clone: start with one command (including a wait-until-ready variant), paste the sample request (or try it pre-filled in the interactive docs), and check the result against the department-boundary table with Polish and English examples. The README also records the architecture notes, the measured latency and the first-start time. Closes the `deployment` change's hand-off checklist: replaces the README's two `TODO(next change)` markers and runs its Phase 6 clean-clone rehearsal.
- **Change ID:** reviewer-handoff
- **PRD refs:** FR-008, FR-009, FR-010, NFR (< 15 min from fresh clone to first request served)
- **Prerequisites:** S-02, S-03
- **Parallel with:** —
- **Blockers:** —
- **Unknowns:** —
- **Risk:** Last because every figure it records depends on the final model. The rehearsal deletes the model volume and needs human approval, and a first-start over 15 minutes would surface only here.
- **Status:** proposed

## Backlog Handoff

| Roadmap ID | Change ID                     | Suggested issue title                                              | Ready for `/10x-plan` | Notes                                      |
| ---------- | ----------------------------- | ------------------------------------------------------------------ | --------------------- | ------------------------------------------ |
| S-01       | first-routed-request          | Route a request to its department via the agent's send-email tool  | yes                   | Run `/10x-plan first-routed-request`       |
| S-02       | boundary-and-fallback-routing | Route boundary and unclear requests correctly; pick and time model | no                    | After S-01                                 |
| S-03       | input-validation              | Reject malformed email, empty or over-long messages                | no                    | After S-01; can run alongside S-02         |
| S-04       | reviewer-handoff              | Complete README and rehearse a clean-clone run                     | no                    | After S-02 and S-03                        |

## Open Roadmap Questions

1. **If no candidate model meets both all US-01 to US-03 examples and < 30 s per request, which gives way?** — Owner: user. Block: none now; decide only if S-02's measurement forces it.

## Parked

- **Routing history or admin view** — Why parked: PRD Non-Goals; conflicts with the no-retention NFR.
- **Outbox or retry queue** — Why parked: PRD Non-Goals; noted in the README as a production-version item.
- **Learning from misroutes** — Why parked: PRD Non-Goals; department boundaries are fixed configuration.
- **Splitting multi-request messages** — Why parked: PRD Non-Goals; routed by the main request.
- **Sample-set scoring of routing accuracy** — Why parked: PRD Non-Goals; verification uses the US-01 to US-03 examples.
- **Production hardening (HA, load, sender verification)** — Why parked: PRD Non-Goals.
- **Required CI checks in branch protection** — Why parked: optional human step from the `deployment` change, not a PRD requirement; skipped under the speed goal.

## Milestone History

## Done
