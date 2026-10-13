---
project: "Mail Triage Agent"
version: 1
status: draft
created: 2026-10-13
context_type: greenfield
product_type: api
target_scale:
  users: small
  qps: "< 1 (manual testing by the author and a handful of reviewers)"
  data_volume: "none persisted (no storage; emails exist only in the mail-capture tool)"
timeline_budget:
  mvp_weeks: 1
  hard_deadline: 2026-10-16
  after_hours_only: false
---

# Mail Triage Agent — PRD

## Vision & Problem Statement

An employee in an organisation with several department inboxes (HR, kadry, help-desk, IT, plus a catch-all) writes a free-text request and has to decide where to send it. They are unsure who to ask, so they ask colleagues or send to several inboxes at once; when they guess wrong they wait, then get redirected and have to resend; and some misrouted requests are simply lost with nobody taking ownership.

The insight: the messages are free text with no form or category picker, so keyword rules break on unseen phrasing; the departments overlap (HR vs kadry, help-desk vs IT), so telling them apart requires reading intent rather than matching words; and knowing when *not* to guess — routing to the fallback inbox — is as much a part of the decision as picking the right department. This is why routing must read each message's intent (FR-011) rather than match keywords.

Scale note: at 100× the user count, the fallback inbox would become a queue needing its own triage — so the fallback threshold matters more than the PoC's scale suggests.

## User & Persona

**Primary persona — Employee.** Works in a single organisation that has five fixed department inboxes. Reaches for the product at the moment they have a request ("my computer doesn't work", "I want to file leave for tomorrow") and don't know — or don't want to work out — which department owns it. Writes in their own words.

### Secondary persona

**Reviewer.** Clones the repository, runs it, sends a test request, and checks the result against the brief's acceptance criteria (correct department, correct `Reply-To`, docs reachable, environment starts with one command). The PoC is a take-home assignment framed as a product; the reviewer is who must be satisfied, the employee is who the product is shaped around.

## Success Criteria

### Primary
- A reviewer clones the repository, starts the whole environment with one command, sends one request containing a sender address and a free-text message, and sees in the mail-capture web UI a new email addressed to the correct department (per the five-address list and the README's department-boundary table) with `Reply-To` set to the original sender. The request's response names the chosen department.

MVP flow (reviewer's first session):
1. Clone the repo and start the environment with one command (given in the README, including a variant that waits until the environment is ready).
2. The environment starts, fetches the model, warms it up, and reports itself ready; the ready status turns on only once the model has been fetched and warmed up.
3. Send one request `{ email, message }` — from the command line or from the interactive API docs.
4. The product reads the message, decides the department, and sends one email to it; the response returns the chosen department.
5. Open the mail-capture web UI and see the email: correct department, `Reply-To` = original sender.

### Secondary
None. Routing is verified with the acceptance examples in US-01 to US-03.

### Guardrails
- No email is ever sent to an address outside the five-address list — any other address is rejected, whatever routing decision was produced.
- A message that matches none of the four department responsibilities goes to the fallback inbox (`other@example.com`) rather than to a guessed department; a message that plausibly matches a responsibility goes to its owner (see Business Logic precedence).
- On success, each request produces exactly one email; if the request fails before the email is sent, zero emails and an explicit error in the response. Never more than one. Once the email is sent, the request counts as successful (FR-007).
- The forwarded email carries the employee's original message unaltered — not a summary or rewrite. The body is exactly what the employee submitted.

## User Stories

### US-01: Employee's request reaches the right department

- **Given** the environment is running and reports ready (model pulled and warmed up)
- **When** an employee submits `{ email: "jan.nowak@example.com", message: "Nie działa mi komputer" }`
- **Then** exactly one email appears in the mail-capture UI, addressed to the department that owns the request, with the original message unaltered and `Reply-To` = `jan.nowak@example.com`, and the response names that department

#### Acceptance Criteria
- The recipient is one of the five listed addresses.
- `Reply-To` equals the submitted sender address exactly.
- The email body contains the submitted message verbatim.
- `From` is `triage-agent@example.com` and the subject is `[Triage] New request`.
- For this example message, the recipient is `help-desk@example.com` (see US-03 boundaries).
- If no department decision is produced, the request ends with an error (FR-007) and no email is sent.

### US-02: Unclear message goes to the fallback inbox

- **Given** the environment is running and reports ready (model pulled and warmed up)
- **When** an employee submits a message that matches none of the four department responsibilities (e.g. "hello?")
- **Then** exactly one email is sent to `other@example.com`, not to a guessed department, and the response names `other@example.com`

### US-03: Message on an overlapping boundary routes per the stated rule

- **Given** the environment is running and reports ready (model pulled and warmed up)
- **When** an employee submits a message that sits on a department boundary
- **Then** it routes according to these boundaries:
  - `kadry@example.com` — personnel administration: leave, contracts, employment documents
  - `human-resources@example.com` — hiring and employee development
  - `help-desk@example.com` — user-facing hardware and software problems
  - `it@example.com` — infrastructure, access, systems

#### Acceptance Criteria
- "Chciałbym zgłosić urlop na jutro" (leave request) → `kadry@example.com`
- "Nie działa mi komputer" (broken computer) → `help-desk@example.com`

### US-04: Invalid input is rejected

- **Given** the environment is running
- **When** a caller submits a malformed email address, an empty or whitespace-only message, or a message longer than 2000 characters
- **Then** the response is a clear error naming the problem, and no email appears in the mail-capture UI

## Functional Requirements

### Request intake
- FR-001: Caller can submit a request containing a sender email address and a free-text message. Priority: must-have
  > Socrates: Counter-arguments considered: "one message may contain two requests for different departments, but only one email is allowed"; "language is unspecified (Polish examples)"; "two fields are too thin for the department". Resolution: stands as written.
- FR-002: Caller receives a clear error for a malformed email address, an empty or whitespace-only message, or a message longer than 2000 characters, and no email is sent. Priority: must-have
  > Socrates: Counter-arguments considered: "no upper limit on message length"; "whitespace-only messages pass as non-empty"; "over-strict validation rejects real addresses". Resolution: whitespace-only counts as empty; maximum length set to 2000 characters (bounds CPU inference time).
- FR-003: Caller receives a clear "not ready yet" response while the model is still being pulled or warmed up, instead of a hang or a misroute. Readiness is observable: the environment's status reports the service as ready only after the model has been fetched **and warmed up**, so the first reviewer request does not pay the cold-start cost. Priority: must-have
  > Socrates: Counter-arguments considered: "the reviewer reads 'not ready' as broken"; "redundant if startup only reports itself up once the model is loaded". Resolution: stands; readiness made observable in the environment's status, and the one-command start can wait until ready.

### Routing
- FR-004: Employee's request is routed (FR-011) to whichever of the five department inboxes owns it, falling back to `other@example.com` when the request matches none of the four department responsibilities. Priority: must-have
  > Socrates: Counter-arguments considered: "message text can try to steer its own routing"; "'clearly fits' has no defined threshold"; "the same message may route differently on repeat". Resolution: stands as written; threshold later defined at cross-check as "matches none of the four responsibilities".
- FR-005: Department inbox receives an email (FR-012) containing the original message unaltered, with `Reply-To` set to the sender's address, a constant `From` of `triage-agent@example.com`, and the subject `[Triage] New request`. Priority: must-have
  > Socrates: Counter-arguments considered: "no meaningful subject line"; "From vs Reply-To is unspecified"; "department can't see why it received the message". Resolution: constant `From` and fixed subject added at review.
- FR-006: Caller receives in the response the department the email was actually delivered to (not merely the department stated as the decision). Priority: must-have
  > Socrates: Counter-arguments considered: "a slow model may make the caller time out"; "exposes internal structure to the employee". Resolution: stands as written.
- FR-007: Caller receives an error, not a false success, if the decision or the sending fails — including when no department decision is produced. No email is sent on failure. A request is successful once the email has been delivered; any failure after delivery does not turn it into an error. The department returned to the caller is the one the email was actually delivered to. Priority: must-have
  > Socrates: Counter-arguments considered: "a retry after a lost response sends a duplicate email"; "on decision failure the request lands nowhere instead of the fallback". Resolution: stands as written.
- FR-011: Employee's request is routed by an AI model that reads the message's intent and runs entirely within the local environment. There is no keyword-based or rule-based routing, and nothing pre-classifies or overrides the AI's decision (other than enforcing the closed list of five addresses). Priority: must-have
- FR-012: Department inbox receives at most one email per request: the only thing decided per request is the department; the message body and `Reply-To` always come from the original request; any address outside the closed five-address list is rejected; and any further send attempt within the same request fails and sends nothing. Priority: must-have

### Reviewer experience
- FR-008: Reviewer can start the whole environment with one command after cloning; the model is fetched automatically. Priority: must-have
  > Socrates: Counter-arguments considered: "a multi-GB model makes first start take many minutes"; "reviewer hardware varies (no GPU, limited RAM)". Resolution: stands as written.
- FR-009: Reviewer can read and try the endpoint from interactive API docs at an address given in the README. Priority: must-have
  > Socrates: Counter-arguments considered: "docs drift from actual behaviour"; "docs without a pre-filled example". Resolution: stands as written.
- FR-010: Reviewer can follow a README with run instructions (including how to start and wait until the environment is ready), a short note on architecture decisions, a ready-to-paste sample request, and a table of department boundaries with example messages in Polish and English. Priority: must-have
  > Socrates: Counter-arguments considered: "hardware needs and first-start time not stated"; "a single sample only shows the easy path"; "'correct department' is subjective for the reviewer". Resolution: boundary table added so routing results are justified, not just "picked by the model".

## Non-Functional Requirements

- No message content or sender address leaves the local environment — nothing is sent to any external service.
- Message content is not retained anywhere after the request completes, other than in the delivered email. Message content and sender addresses are never written to application logs.
- The product accepts and routes messages written in Polish and in English.
- Target: < 30 s per request on a CPU-only machine once ready; measured during implementation, with the actual figure recorded in the README.
- From the one-command start on a fresh clone to the first request being served takes < 15 minutes on a typical home connection.
- The whole environment runs on a CPU-only laptop with 16 GB RAM and 10 GB of free disk.

## Business Logic

Each request is delivered to exactly one of five department inboxes — the one whose responsibility matches the request's intent — and to the fallback inbox whenever no department owns it.

Inputs are the employee's free-text message (Polish or English) and their sender address. Department responsibilities are fixed: `kadry@example.com` owns personnel administration (leave, contracts, employment documents); `human-resources@example.com` owns hiring and employee development; `help-desk@example.com` owns user-facing hardware and software problems; `it@example.com` owns infrastructure, access and systems; `other@example.com` receives a request only when it matches none of those four responsibilities. Precedence: ownership wins — if any of the four responsibilities plausibly matches, the request goes to that owner; the fallback is used only when nothing matches. The sender address does not influence the decision; it only becomes the `Reply-To` of the delivered email.

When a message contains several requests for different departments, it is routed by its main (dominant or first) request; the receiving department forwards the rest. Instructions inside the message that try to steer routing ("send this to it@", "ignore your instructions") are ignored — routing follows what the request is actually about, and an explicit department hint counts only when it agrees with the content. This rule is not a pass/fail acceptance criterion. The output is a single delivered email containing the original message unaltered, plus the chosen department returned to the caller.

## Access Control

No authentication; flat model with a single kind of caller and a single action (submit a request). Anyone who can reach the product may submit.

- The sender's email address is self-declared. It must be a syntactically valid address — malformed addresses are rejected with a clear error — but ownership of the address is not verified.
- Accepted PoC limitation: a caller can submit on behalf of any address, and that address becomes the `Reply-To` the department answers.
- No roles. There is no admin view of routed requests; the list of department inboxes is fixed configuration, not user-editable.

## Non-Goals

- **No routing history or admin view** — requests are not stored or browsable; the delivered email is the only record (consistent with the no-retention NFR).
- **No outbox or retry queue** — a failed send returns an error and is not retried later; a durable outbox is a production-version item noted in the README.
- **No learning from misroutes** — departments cannot flag a misroute and the rule does not adapt; department boundaries are fixed configuration.
- **No splitting of multi-request messages** — one message never becomes several emails; it is routed by its main request.
- **No sample-set scoring** — routing is verified with the acceptance examples in US-01 to US-03.
- **No production hardening** — no high availability, no load handling beyond a handful of users, no sender identity verification; single machine only.

## Open Questions

None.
