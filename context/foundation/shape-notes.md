---
project: "Mail Triage Agent"
context_type: greenfield
created: 2026-10-13
updated: 2026-10-13
product_type: api
target_scale:
  users: small
timeline_budget:
  mvp_weeks: 1
  hard_deadline: 2026-10-16
  after_hours_only: false
checkpoint:
  current_phase: 8
  phases_completed: [1, 2, 3, 4, 5, 6, 7]
  gray_areas_resolved:
    - topic: "context type"
      decision: "greenfield — repo holds only toolkit setup (2 commits), no product code"
    - topic: "primary audience"
      decision: "both — take-home assignment, shaped around a believable end user"
    - topic: "persona scope"
      decision: "employee in a single organisation with five fixed department inboxes"
    - topic: "pain category"
      decision: "requests land in the wrong inbox (coordination overhead)"
    - topic: "auth strategy"
      decision: "none — anyone who can reach the endpoint may submit"
    - topic: "sender address handling"
      decision: "must be a syntactically valid address; ownership not verified (spoofing accepted as PoC limitation)"
    - topic: "roles"
      decision: "flat model, no roles; department list is fixed configuration"
    - topic: "endpoint response"
      decision: "synchronous — caller waits until the email is sent and receives the chosen department"
    - topic: "readiness after startup"
      decision: "requests are not served until the model is loaded; nothing is routed while loading"
    - topic: "MVP estimate"
      decision: "1 week or less; no scope-down needed"
    - topic: "department boundaries"
      decision: "kadry = personnel admin (leave, contracts, documents); HR = hiring & development; help-desk = user-facing HW/SW problems; IT = infrastructure, access, systems"
    - topic: "domain rule"
      decision: "owner-or-fallback classification into exactly one of five inboxes"
    - topic: "multi-request messages"
      decision: "route by the main (dominant/first) request"
    - topic: "routing steering in message text"
      decision: "ignored; route by content; explicit hint counts only if it agrees with content"
    - topic: "product type"
      decision: "API / backend service"
    - topic: "target scale"
      decision: "small — the author and a handful of reviewers"
    - topic: "timing"
      decision: "hard deadline 2026-10-16 08:30; day-job hours (not after-hours)"
    - topic: "deadline vs scope"
      decision: "FR-011 (sample-message set) demoted to nice-to-have to fit the deadline"
    - topic: "fallback trigger"
      decision: "fallback only when the request matches none of the four department responsibilities"
    - topic: "hardware floor"
      decision: "CPU-only laptop with 16 GB RAM and 10 GB free disk"
    - topic: "sample-set accuracy target"
      decision: ">= 80% correct routing (stretch goal, FR-011 nice-to-have)"
  frs_drafted: 11
  quality_check_status: accepted
---

# Shape Notes

Seed: `idea-notes.md` (PoC brief for an AI-based message categorization and routing system).

## Vision & Problem Statement

An employee in an organisation with several department inboxes (HR, kadry, help-desk, IT, plus a catch-all) writes a free-text request and has to decide where to send it. They are unsure who to ask, so they ask colleagues or send to several inboxes at once; when they guess wrong they wait, then get redirected and have to resend; and some misrouted requests are simply lost with nobody taking ownership.

The insight: the messages are free text with no form or category picker, so keyword rules break on unseen phrasing; the departments overlap (HR vs kadry, help-desk vs IT), so telling them apart requires reading intent rather than matching words; and knowing when *not* to guess — routing to the fallback inbox — is as much a part of the decision as picking the right department.

Scale note: at 100× the user count, the fallback inbox would become a queue needing its own triage — so the fallback threshold matters more than the PoC's scale suggests.

## User & Persona

**Primary persona — Employee.** Works in a single organisation that has five fixed department inboxes. Reaches for the product at the moment they have a request ("my computer doesn't work", "I want to file leave for tomorrow") and don't know — or don't want to work out — which department owns it. Writes in their own words.

### Secondary persona

**Reviewer.** Clones the repository, runs it, sends a test request, and checks the result against the brief's acceptance criteria (correct department, correct `Reply-To`, docs reachable, environment starts with one command). The PoC is a take-home assignment framed as a product; the reviewer is who must be satisfied, the employee is who the product is shaped around.

## Success Criteria

### Primary
- A reviewer clones the repository, starts the whole environment with one command, sends one request containing a sender address and a free-text message, and sees in the mail-capture web UI a new email addressed to the correct department (per the five-address list) with `Reply-To` set to the original sender. The request's response names the chosen department.

MVP flow (reviewer's first session):
1. Clone the repo and start the environment with one command.
2. The environment starts, fetches the model, and reports itself ready.
3. Send one request `{ email, message }` — via curl or the interactive docs at `/api/v1/docs`.
4. The product reads the message, decides the department, and sends an email to it; the response returns the chosen department.
5. Open the mail-capture web UI and see the email: correct department, `Reply-To` = original sender.

### Secondary
- A small set of sample messages — including ambiguous ones (HR vs kadry, help-desk vs IT) and fallback cases — routes correctly in ≥ 80% of cases. (Stretch goal; backed by FR-011, which is nice-to-have.)

### Guardrails
- No email is ever sent to an address outside the five-address list, even if a different address is suggested during the decision.
- Unclear or off-topic messages go to the fallback inbox (`other@example.com`), not to a confidently wrong department.
- Each request produces exactly one email — never zero (silent drop), never more than one.
- The forwarded email carries the employee's original message unaltered — not a summary or rewrite.

## User Stories

### US-01: Employee's request reaches the right department

- **Given** the environment is running and the model is loaded
- **When** an employee submits `{ email: "jan.nowak@example.com", message: "Nie działa mi komputer" }`
- **Then** exactly one email appears in the mail-capture UI, addressed to the department that owns the request, with the original message unaltered and `Reply-To` = `jan.nowak@example.com`, and the response names that department

#### Acceptance Criteria
- The recipient is one of the five listed addresses.
- `Reply-To` equals the submitted sender address exactly.
- The email body contains the submitted message verbatim.
- For this example message, the recipient is `help-desk@example.com` (see US-03 boundaries).

### US-02: Unclear message goes to the fallback inbox

- **Given** the environment is running and the model is loaded
- **When** an employee submits a message that matches none of the four department responsibilities (e.g. "hello?")
- **Then** exactly one email is sent to `other@example.com`, not to a guessed department, and the response names `other@example.com`

### US-03: Message on an overlapping boundary routes per the stated rule

- **Given** the environment is running and the model is loaded
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
- **When** a caller submits a malformed email address or an empty message
- **Then** the response is a clear error naming the problem, and no email appears in the mail-capture UI

## Functional Requirements

### Request intake
- FR-001: Caller can submit a request containing a sender email address and a free-text message. Priority: must-have
  > Socrates: Counter-arguments considered: "one message may contain two requests for different departments, but only one email is allowed"; "language is unspecified (Polish examples)"; "two fields are too thin for the department". Resolution: stands as written.
- FR-002: Caller receives a clear error for a malformed email address or an empty message, and no email is sent. Priority: must-have
  > Socrates: Counter-arguments considered: "no upper limit on message length"; "whitespace-only messages pass as non-empty"; "over-strict validation rejects real addresses". Resolution: stands as written.
- FR-003: Caller receives a clear "not ready yet" response while the model is still loading, instead of a hang or a misroute. Priority: must-have
  > Socrates: Counter-arguments considered: "the reviewer reads 'not ready' as broken"; "redundant if startup only reports itself up once the model is loaded". Resolution: stands as written.

### Routing
- FR-004: Product decides which of the five department inboxes owns the request, falling back to `other@example.com` when the request matches none of the four department responsibilities. Priority: must-have
  > Socrates: Counter-arguments considered: "message text can try to steer its own routing"; "'clearly fits' has no defined threshold"; "the same message may route differently on repeat". Resolution: stands as written; threshold later defined at cross-check as "matches none of the four responsibilities".
- FR-005: Department inbox receives an email containing the original message unaltered, with `Reply-To` set to the sender's address. Priority: must-have
  > Socrates: Counter-arguments considered: "no meaningful subject line"; "From vs Reply-To is unspecified"; "department can't see why it received the message". Resolution: stands as written.
- FR-006: Caller receives the chosen department in the response. Priority: must-have
  > Socrates: Counter-arguments considered: "a slow model may make the caller time out"; "exposes internal structure to the employee". Resolution: stands as written.
- FR-007: Caller receives an error, not a false success, if the decision or the sending fails. Priority: must-have
  > Socrates: Counter-arguments considered: "a retry after a lost response sends a duplicate email"; "on decision failure the request lands nowhere instead of the fallback". Resolution: stands as written.

### Reviewer experience
- FR-008: Reviewer can start the whole environment with one command after cloning; the model is fetched automatically. Priority: must-have
  > Socrates: Counter-arguments considered: "a multi-GB model makes first start take many minutes"; "reviewer hardware varies (no GPU, limited RAM)". Resolution: stands as written.
- FR-009: Reviewer can read and try the endpoint from interactive API docs at `/api/v1/docs`. Priority: must-have
  > Socrates: Counter-arguments considered: "docs drift from actual behaviour"; "docs without a pre-filled example". Resolution: stands as written.
- FR-010: Reviewer can follow a README with run instructions, a short note on architecture decisions, and a ready-to-paste sample request. Priority: must-have
  > Socrates: Counter-arguments considered: "hardware needs and first-start time not stated"; "a single sample only shows the easy path". Resolution: stands as written.
- FR-011: Reviewer can run the sample-message set and see how many messages routed correctly. Priority: nice-to-have
  > Socrates: Counter-arguments considered: "results vary between runs"; "tuned and graded on the same set"; "beyond the brief's acceptance checklist". Resolution: stands as written.
  > Cross-check (2026-10-13): demoted to nice-to-have — the 1-week estimate does not fit the 2026-10-16 08:30 deadline; must-haves now match the brief's acceptance checklist.

## Non-Functional Requirements

- No message content or sender address leaves the local environment — nothing is sent to any external service.
- Message content is not retained anywhere after the request completes, other than in the delivered email.
- Messages written in Polish and in English route equally well.
- Once the model is loaded, a single request completes (response returned, email delivered) in < 30 s on a CPU-only reviewer machine.
- From `docker compose up -d` on a fresh clone to the first request being served takes < 15 minutes on a typical home connection.
- The whole environment runs on a CPU-only laptop with 16 GB RAM and 10 GB of free disk.

## Business Logic

Each request is delivered to exactly one of five department inboxes — the one whose responsibility matches the request's intent — and to the fallback inbox whenever no department clearly owns it.

Inputs are the employee's free-text message (Polish or English) and their sender address. Department responsibilities are fixed: `kadry@example.com` owns personnel administration (leave, contracts, employment documents); `human-resources@example.com` owns hiring and employee development; `help-desk@example.com` owns user-facing hardware and software problems; `it@example.com` owns infrastructure, access and systems; `other@example.com` receives a request only when it matches none of those four responsibilities — anything plausibly owned goes to its owner. The sender address does not influence the decision; it only becomes the `Reply-To` of the delivered email.

When a message contains several requests for different departments, it is routed by its main (dominant or first) request; the receiving department forwards the rest. Instructions inside the message that try to steer routing ("send this to it@", "ignore your instructions") are ignored — routing follows what the request is actually about, and an explicit department hint counts only when it agrees with the content. The output is a single delivered email containing the original message unaltered, plus the chosen department returned to the caller.

## Access Control

No authentication; flat model with a single kind of caller and a single action (submit a request). Anyone who can reach the endpoint may submit.

- The sender's email address is self-declared. It must be a syntactically valid address — malformed addresses are rejected with a clear error — but ownership of the address is not verified.
- Accepted PoC limitation: a caller can submit on behalf of any address, and that address becomes the `Reply-To` the department answers.
- No roles. There is no admin view of routed requests; the list of department inboxes is fixed configuration, not user-editable.

## Non-Goals

- **No routing history or admin view** — requests are not stored or browsable; the delivered email is the only record (consistent with the no-retention NFR).
- **No learning from misroutes** — departments cannot flag a misroute and the rule does not adapt; department boundaries are fixed configuration.
- **No splitting of multi-request messages** — one message never becomes several emails; it is routed by its main request.
- **Sample-message set scoring is not required for the MVP** — FR-011 is nice-to-have; it ships only if time remains before the deadline.
- **No production hardening** — no high availability, no load handling beyond a handful of users, no sender identity verification; single machine only.

## Open Questions

None open. Resolved at cross-check (2026-10-13):

- ~~Correct-routing rate on the sample set~~ → ≥ 80%.
- ~~RAM and disk floor~~ → 16 GB RAM, 10 GB free disk.
- ~~Fallback trigger~~ → only when the request matches none of the four department responsibilities.

## Timeline

Hard deadline: 2026-10-16 08:30 (day-job hours). MVP estimate: ≤ 1 week. The estimate exceeds the ~2.5 working days available; FR-011 was demoted to nice-to-have so the remaining must-haves match the brief's acceptance checklist. Schedule risk remains and should be watched during planning.

## Quality cross-check

Run 2026-10-13 — all elements present (Access Control, Business Logic one-sentence rule, project artifacts, timeline-cost, Non-Goals; preserved behavior n/a for greenfield). No gaps.

## Forward: tech-stack

Informational — not part of the PRD schema. Binding constraints from the seed brief (`idea-notes.md`) for the tech-stack selection step:

- The whole environment is containerised and defined in a single `docker-compose.yml`; `docker compose up -d` on a fresh clone must start everything, fetch model weights, and become ready to accept requests.
- Required containers: API service written in PHP or Python on the official `php` / `python` image; a mail-capture tool (e.g. `mailhog/mailhog` or equivalent) with a web UI; Ollama running locally (`ollama/ollama` or `alpine/ollama`), CPU or GPU at the implementer's discretion.
- The routing decision is made by an AI agent connected to the local Ollama instance, and the email **must** be sent by the agent through a dedicated tool via tool/function calling.
- API documentation in Swagger/OpenAPI served at `/api/v1/docs`.
- Optional suggestion from the brief: for Python, consider `pydantic-ai` or `langchain` for agent and function-calling support.

## Forward: technical-roadmap

Informational — not part of the PRD schema.

- README must contain: run instructions, a short description of architectural decisions, and a sample request (cURL or similar) for quick endpoint testing.
- A sample-message set (including HR/kadry and help-desk/IT boundary cases and fallback cases) backs FR-011 and the Secondary success criterion.
