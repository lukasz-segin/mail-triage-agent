<!-- PLAN-REVIEW-REPORT -->
# Plan Review: First Routed Request Implementation Plan

- **Plan**: context/changes/first-routed-request/plan.md
- **Mode**: Deep (second pass, after two rounds of external feedback)
- **Date**: 2026-10-15
- **Verdict**: SOUND
- **Findings**: 0 critical, 0 warnings, 3 observations

The first pass (same date) found 4 warnings and 2 observations, all fixed in the plan: the PowerShell sample request, failure classification, per-call timeout, SMTP timeout, the failure-after-send test and Progress titles. This report replaces it.

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | PASS |
| Lean Execution | PASS |
| Architectural Fitness | PASS |
| Blind Spots | PASS |
| Plan Completeness | PASS |

## Grounding

6/6 paths ✓, symbols unchanged since pass 1 ✓, Progress↔Phase ✓ (Phase 1: 3 automated + 1 manual; Phase 2: 7 automated + 6 manual; titles unchanged), brief↔plan ✓ apart from the wording in F1. Verified now: Mailpit v1.31.6 `--max` default = 500 messages.

Note (not a finding): with `temperature=0` and identical input, Ollama is close to deterministic, so 5/5 mainly guards against run-to-run noise and the first request after startup, not against different phrasings; S-02's variants cover that.

## Findings

### F1 — Some text still says only US-01 is tested

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: plan.md Phase 2 Overview; plan-brief.md "Testing" row
- **Detail**: Both say "prove US-01" or "proves US-01 repeatably", but the live test now covers both brief examples. Progress titles 2.4 and 2.11 are immutable; this is prose only.
- **Fix**: Change both to "both brief examples (computer → help-desk@, leave → kadry@)".
- **Decision**: FIXED (with the test-trimming edit)

### F2 — Mailpit's 500-message cap breaks the "exactly one new email" check

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Phase 2 §3 live test contract
- **Detail**: The test asserts that the message count grew by one. Mailpit keeps at most 500 messages by default and deletes the oldest, so once the inbox is full the count stays at 500 and every run fails for a reason unrelated to routing. Each live session adds 10 emails, and S-02 adds more cases.
- **Fix**: Find new messages by ID: read the newest IDs before the request, then assert exactly one ID afterwards that wasn't there before, and fetch that message.
- **Decision**: PENDING

### F3 — The README sample shows only the first brief example

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 2 §4 README contract
- **Detail**: A reviewer will try both brief examples, and S-01 proves both, but the README gives a ready-to-paste request only for US-01; the leave example reaches the README only with S-04's table.
- **Fix**: Under the US-01 curl, add one line: the same request with "Chciałbym zgłosić urlop na jutro" → `{"department":"kadry@example.com"}`.
- **Decision**: PENDING
