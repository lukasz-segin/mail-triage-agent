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
> Slices below are listed in work sequence (see "Sequence"). Prerequisites name the hard dependencies. The "At a glance" table is the index.

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

| ID   | Change ID                     | Issue                                                               | Outcome (user can …)                                                                 | Prerequisites | PRD refs                                                              | Status   |
| ---- | ----------------------------- | ------------------------------------------------------------------- | ------------------------------------------------------------------------------------ | ------------- | --------------------------------------------------------------------- | -------- |
| S-01 | first-routed-request          | [#6](https://github.com/lukasz-segin/mail-triage-agent/issues/6) | employee can submit a request and it arrives, unaltered, at the owning department     | —             | US-01, US-03 (leave example), FR-001, FR-003, FR-004, FR-005, FR-006, FR-007, FR-011, FR-012 | done |
| S-03 | input-validation              | [#8](https://github.com/lukasz-segin/mail-triage-agent/issues/8) | caller gets a clear error for bad input, and no email is sent                         | S-01          | US-04, FR-002                                                         | proposed |
| S-04 | reviewer-handoff              | [#9](https://github.com/lukasz-segin/mail-triage-agent/issues/9) | reviewer can check any routing result against the README's boundary table and notes   | S-01, S-03    | FR-009, FR-010                                                        | done |
| S-02 | boundary-and-fallback-routing | [#7](https://github.com/lukasz-segin/mail-triage-agent/issues/7) | employee's boundary and unclear requests route per the stated rules, in PL and EN    | S-01          | US-02, US-03, FR-004, FR-011                                          | proposed |
| S-05 | submission-rehearsal          | [#10](https://github.com/lukasz-segin/mail-triage-agent/issues/10) | reviewer can go from a fresh clone to a verified request in under 15 minutes          | S-02, S-04    | FR-008, NFR (< 15 min)                                                | done |

### Sequence

Work order: **S-01 → S-03 → S-04 → S-02 → S-05** (deadline 2026-10-16 08:30).

Actual order before the deadline: **S-01 → S-04 → S-05**. S-04 moved ahead of S-03 because it closes the brief's last README requirement (architecture notes); the README lists missing input validation under "Known limitations" instead of documenting validation errors. S-05 ran on S-01's model (`qwen2.5:3b`) because S-02 was skipped: both brief examples pass 10 of 10, and "hello?" lands at `other@`. S-03 and S-02 stay open, so M-1 stays open. Prerequisites are hard dependencies; the sequence is priority. The must-have validation and docs land before S-02's open-ended model tuning, so they exist even if tuning runs long. S-02 still depends only on S-01, and S-05 runs last because its figures depend on the final model.

### Issue convention

Each slice has exactly one GitHub issue, linked in the table above and in the slice's `- **Issue:**` line. The issue and the slice close together:

- A PR that only advances a slice (one phase of several) says `Part of #N` in its description, which leaves the issue open.
- The PR that completes the slice says `Closes #N`, so merging it into `main` closes the issue.
- A slice is `done` only when its issue is closed. When `/10x-archive` flips a slice to `done`, check the issue (`gh issue view N`). If it's still open, for example because the closing PR lacked the keyword, close it by hand: `gh issue close N --comment "Done in #<PR>"`.
- A slice added later gets its issue when it's added, and the number is recorded here and in the slice body.
- Milestone M-1 closes when every slice's issue is closed.

## Baseline

What's already in place in the codebase as of 2026-10-15 (auto-researched + user-confirmed).
Foundations below assume these are present and do NOT re-scaffold them.

- **Frontend:** absent by design — no own UI; interactive API docs at `/api/v1/docs` (`src/mail_triage_agent/app.py`) and the Mailpit web UI are the only surfaces.
- **Backend / API:** partial — FastAPI app with `/health` and docs (`app.py`); model pull + warm-up and the `require_ready` "not ready" gate, plus the shared `MODEL` / `MODEL_OPTIONS` (`readiness.py`). No triage endpoint, agent or send-email tool yet.
- **Data:** absent by design — PRD forbids storing requests.
- **Auth:** absent by design — PRD Access Control: no authentication; the API is published on `127.0.0.1` only (`docker-compose.yml`).
- **Deploy / infra:** present — Compose stack (api, `alpine/ollama`, Mailpit) with a healthcheck that turns ready only after warm-up; `Dockerfile`; CI runs ruff, pytest and the image build (`.github/workflows/ci.yml`). Pending: the clean-clone rehearsal (Phase 6 of the `deployment` change), now slice S-05.
- **Observability:** partial — stdlib logging configured (`src/mail_triage_agent/__init__.py`); nothing yet guards against message content or sender addresses reaching logs.

## Foundations

None. The baseline already provides the Compose stack, the readiness gate and CI. The only missing cross-cutting pieces (the agent, the send-email tool, the no-content logging rule) are first needed by S-01 and are introduced there.

## Slices

### S-01: An employee's request reaches the right department

- **Outcome:** user can submit `{ email, message }` and, for both examples the brief gives, see exactly one email in the mail-capture UI at the owning department: "Nie działa mi komputer" → `help-desk@example.com`, "Chciałbym zgłosić urlop na jutro" → `kadry@example.com`. The email has the message verbatim, `Reply-To` = sender, the fixed `From` and subject, and the response names the department the tool actually delivered to. The system prompt carries the full PRD boundaries from the start, and the live test passes 5 of 5 consecutive runs for each of the two examples, because a reviewer will try exactly these. Picks up the `deployment` change's hand-off items for the endpoint: the readiness gate and the shared model settings.
- **Change ID:** first-routed-request
- **Issue:** [#6](https://github.com/lukasz-segin/mail-triage-agent/issues/6)
- **PRD refs:** US-01, US-03 (leave example), FR-001, FR-003, FR-004, FR-005, FR-006, FR-007, FR-011, FR-012, NFR (no data leaves the environment; no content or sender in logs)
- **Prerequisites:** —
- **Parallel with:** —
- **Blockers:** —
- **Unknowns:**
  - Does the default candidate model call the send tool reliably with only the department as its argument, and route both brief examples correctly (including kadry vs HR for the leave request)? — Owner: user. Block: **yes for S-01**: resolved inside S-01 (live test 5/5 per example; tighten the prompt, then switch to `llama3.2:3b`). S-02 still owns the final model choice across all examples.
- **Risk:** Carries most must-have FRs because the PRD has a single workflow and FR-005/006/007/012 are guardrails of that one send, so splitting them would ship an unguarded tool. Sequenced first because every other slice tunes or documents this flow.
- **Status:** done

### S-03: Bad input is rejected with a clear error

- **Outcome:** user who submits a malformed email address, an empty or whitespace-only message, or a message over 2000 characters gets an error naming the problem, and no email appears in the mail-capture UI.
- **Change ID:** input-validation
- **Issue:** [#8](https://github.com/lukasz-segin/mail-triage-agent/issues/8)
- **PRD refs:** US-04, FR-002
- **Prerequisites:** S-01
- **Parallel with:** S-02 (by dependency; sequenced before it)
- **Blockers:** —
- **Unknowns:** —
- **Risk:** Small and low-risk; kept separate so S-01 stays focused on the send path. Rejection must happen before the model is called, so an invalid request costs no inference time.
- **Status:** proposed

### S-04: A reviewer can check routing against the README

- **Outcome:** reviewer can check any routing result against the README's department-boundary table (five addresses, their PRD responsibilities, Polish and English example messages) and read short notes on the architecture decisions and the error responses, including S-03's validation errors. The architecture notes say explicitly that the agent sends the email itself by calling the `send_email` tool, and that the tool deliberately exposes only the department as an argument: the message body and `Reply-To` are injected from the original request, so the model can't alter the employee's message or the reply address, and can't send outside the five allowed inboxes. They also say in one sentence why a leave request goes to `kadry@`, not `human-resources@`: per the PRD, kadry owns personnel administration (leave, contracts, employment documents), and HR owns hiring and employee development. Docs only. Replaces the README's remaining `TODO(next change)` marker. The latency figure stays with S-02; the first-start time and the clean-clone rehearsal moved to S-05.
- **Change ID:** reviewer-handoff
- **Issue:** [#9](https://github.com/lukasz-segin/mail-triage-agent/issues/9)
- **PRD refs:** FR-009, FR-010
- **Prerequisites:** S-01, S-03
- **Parallel with:** S-02 (by dependency; sequenced before it)
- **Blockers:** —
- **Unknowns:** —
- **Risk:** Low: static content from the PRD, independent of the model. Sequenced before S-02 so the must-have README exists even if model tuning runs long.
- **Status:** done

### S-02: Boundary and unclear requests route per the stated rules

- **Outcome:** user can send the US-02 and US-03 acceptance examples, in Polish and English, and each lands at the department the PRD boundaries name. New in this slice: "hello?" goes to `other@example.com`, and the English variants route like their Polish originals. The two Polish brief examples (leave → `kadry@`, broken computer → `help-desk@`) are first proven in S-01; here they are re-checked on the final model. The smallest candidate model that passes all of them in under 30 s on CPU is chosen, and the measured figure is recorded in the README. Starts from S-01's full-boundary prompt; adjusts the prompt or the model only if an example fails.
- **Change ID:** boundary-and-fallback-routing
- **Issue:** [#7](https://github.com/lukasz-segin/mail-triage-agent/issues/7)
- **PRD refs:** US-02, US-03, FR-004, FR-011, NFR (Polish and English; < 30 s per request on CPU)
- **Prerequisites:** S-01
- **Parallel with:** — (sequenced after S-04)
- **Blockers:** —
- **Unknowns:**
  - Which candidate model (per `tech-stack.md`) passes every US-01 to US-03 example under 30 s, both warm and after idle? — Owner: user. Block: no (resolved by measurement inside the slice).
- **Risk:** This is where a small CPU model is most likely to fail (kadry vs HR, help-desk vs IT, knowing when to fall back). Routing must improve only through the model's instructions, never through keyword rules (FR-011). Open-ended, so it is sequenced after the must-have docs.
- **Status:** proposed

### S-05: A fresh clone serves its first request in under 15 minutes

- **Outcome:** reviewer can follow the README on a fresh clone: start with one command (including the wait-until-ready variant), paste the sample request verbatim, and see the email in Mailpit, within 15 minutes of starting. The first-start time and its hardware are recorded in the README. This is Phase 6 of the `deployment` change.
- **Change ID:** submission-rehearsal
- **Issue:** [#10](https://github.com/lukasz-segin/mail-triage-agent/issues/10)
- **PRD refs:** FR-008, NFR (< 15 min from fresh clone to first request served)
- **Prerequisites:** S-02, S-04
- **Parallel with:** —
- **Blockers:** —
- **Unknowns:** —
- **Risk:** Last because its figures depend on the final model chosen in S-02. The rehearsal deletes the model volume (`docker compose down -v`) and needs human approval, and a first start over 15 minutes would surface only here.
- **Status:** done

## Backlog Handoff

| Roadmap ID | Change ID                     | Issue | Issue title                                                                  | Ready for `/10x-plan` | Notes                                              |
| ---------- | ----------------------------- | ----- | ---------------------------------------------------------------------------- | --------------------- | -------------------------------------------------- |
| S-01       | first-routed-request          | #6    | S-01: Route a request to its department via the agent's send-email tool      | yes                   | Done: PR #12, archived                            |
| S-03       | input-validation              | #8    | S-03: Reject malformed email, empty or over-long messages                    | no                    | After S-01                                         |
| S-04       | reviewer-handoff              | #9    | S-04: Complete the README: department table and architecture notes           | no                    | Done: PR #13 (docs only, no change folder)         |
| S-02       | boundary-and-fallback-routing | #7    | S-02: Route boundary and unclear requests correctly; pick and time the model | no                    | After S-01; sequenced after S-04                   |
| S-05       | submission-rehearsal          | #10   | S-05: Rehearse a clean-clone run before submission                           | no                    | Done on S-01's model; no change folder             |

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
- **S-01: user can submit `{ email, message }` and, for both examples the brief gives, see exactly one email in the mail-capture UI at the owning department: "Nie działa mi komputer" → `help-desk@example.com`, "Chciałbym zgłosić urlop na jutro" → `kadry@example.com`. The email has the message verbatim, `Reply-To` = sender, the fixed `From` and subject, and the response names the department the tool actually delivered to. The system prompt carries the full PRD boundaries from the start, and the live test passes 5 of 5 consecutive runs for each of the two examples, because a reviewer will try exactly these. Picks up the `deployment` change's hand-off items for the endpoint: the readiness gate and the shared model settings.** — Archived 2026-10-15 → `context/archive/2026-10-15-first-routed-request/`. Lesson: —.
- **S-04: reviewer can check any routing result against the README's boundary table and notes** — Done 2026-10-16 in PR #13 (no change folder). README gained the department table (PL/EN examples, each routed once), architecture notes and known limitations; S-03 hadn't shipped, so missing validation is listed as a limitation. Lesson: —.
- **S-05: reviewer can go from a fresh clone to a verified request in under 15 minutes** — Done 2026-10-16 (no change folder). Fresh clone of `main` with a fresh model volume: healthy after 217 s (README records 247 s), both brief examples passed the live test, the README curl worked verbatim from WSL. Ran before S-02, on `qwen2.5:3b`. Lesson: —.
