<!-- BEGIN @przeprogramowani/10x-cli -->

## 10xDevs AI Toolkit — Module 1, Lesson 1

Bootstrap a greenfield project end-to-end with the **shaping chain**:

```
/10x-init  →  /10x-shape  →  /10x-prd  →  (10x-tech-stack-selector)  →  (bootstrapper)
```

The first three skills ship in this lesson; the last two are the next links in the chain.

### Task Router — Where to start

| Skill | Use it when |
| --- | --- |
| **Project setup** | |
| `/10x-init` | The project directory is fresh. Scaffolds `context/foundation/lessons.md` and `docs/reference/contract-surfaces.md` so the rest of the workflow has somewhere to write. Run this once per project. |
| **Discovery** | |
| `/10x-shape` | You have an idea and need to turn it into structured shape-notes BEFORE writing a PRD. Greenfield only. Walks vision → persona/access → MVP → FRs (with Socratic challenge) → business logic & data → stack-openness sketch. Surfaces empty-CRUD and MVP-too-big anti-patterns by name. Output: `context/foundation/shape-notes.md` with a resumable `checkpoint:` block. |
| **Document generation** | |
| `/10x-prd` | You have shape-notes (or raw notes) and want a schema-conformant `context/foundation/prd.md`. Generates against the locked schema, routes every gap verbatim into `## Open Questions`, and refuses to invent domain decisions. On collision, prompts overwrite vs. versioned save (`prd-vN.md`). |

### How the chain hands off

- `/10x-init` produces the workflow v2 scaffold (`context/foundation/`, `lessons.md`, `contract-surfaces.md`). `/10x-shape` requires this and will offer to delegate to `/10x-init` if it's missing.
- `/10x-shape` writes `context/foundation/shape-notes.md` with frontmatter `checkpoint:` (current_phase, phases_completed, frs_drafted, quality_check_status). On re-entry, it resumes from the next unfinished phase.
- `/10x-prd` reads `shape-notes.md` (default) or any path you pass, scores the input on a 4-signal heuristic, warns on thin input, and writes `context/foundation/prd.md` against the schema at `skills/10x-shape/references/prd-schema.md` (frontmatter aligned 1:1 with 10x-tech-stack-selector's Q1–Q7).

### What the PRD captures (and what it does NOT)

- **Captured**: vision, persona, success criteria, user stories (Given/When/Then), FRs (FR-NNN), NFRs, business logic (one-sentence rule first), data model, access control, durable implementation decisions, testing strategy, deployment & CI/CD strategy, non-goals, open questions.
- **NOT captured (deliberate)**: framework choices, database choices, file paths, deployment platform. Stack openness is binding — only `product_type` and `tech_preferences.language_family` capture stack-shaped intent. Frameworks are 10x-tech-stack-selector's job.

### Anti-patterns surfaced during shaping

- **Empty-CRUD**: business logic that reduces to "users add and remove records" with no domain rule. `/10x-shape` names it explicitly and prompts for a real rule shape (recommendation, prioritization, classification, validation, scoring, workflow, calculation).
- **MVP-too-big**: first-flow estimate exceeds ~1 week of after-hours work, or > 4 distinct user actions before user-visible value, or requires multiple integrations before payoff. Skill names the expensive pieces and offers concrete scope-down moves.

Both are **soft gates**: they warn but allow override. Overrides are recorded in the checkpoint and surfaced in the PRD's `## Open Questions`.

### Foundation paths used by this lesson

- `context/foundation/shape-notes.md` — `/10x-shape` output
- `context/foundation/prd.md` (or `prd-vN.md`) — `/10x-prd` output
- `context/foundation/lessons.md` — recurring rules & pitfalls (scaffolded by `/10x-init`)
- `docs/reference/contract-surfaces.md` — load-bearing names registry (scaffolded by `/10x-init`)

### Universal language

The shipped skills carry no 10xDevs / cohort / certification references. The mechanics (Socratic challenge, gray-area discovery, recommended-answer fatigue mitigation, soft quality gate) are universal indicators of a well-scoped greenfield project.

Skills must not write to `context/archive/`. Archived changes are immutable; if a resolved target path starts with `context/archive/`, abort with: "This change is archived. Open a new change with `/10x-new` instead."

## 10xDevs AI Toolkit — Module 1, Lesson 2

Pick a starter and a stack for the PRD you wrote in Lesson 1, with the **stack chain**:

```
(/10x-init  →  /10x-shape  →  /10x-prd)  →  /10x-tech-stack-selector  →  (bootstrapper)
```

The PRD chain ships from Lesson 1 (re-included in this lesson so you can fix the PRD mid-flight). `/10x-tech-stack-selector` is the lesson's main topic; `/10x-bootstrapper` is the next link, taught in Lesson 3.

### Task Router — Where to start

| Skill | Use it when |
| --- | --- |
| **Stack selection (lesson focus)** | |
| `/10x-tech-stack-selector` | You have a PRD at `context/foundation/prd.md` and need to pick a starter. Opens with an explicit choice (take the recommended default for your `(product_type, language_family)` cell, or design your own), walks the follow-up question set when you design your own, applies four agent-friendly quality gates, reasons over the language-aware starter registry, and writes `context/foundation/tech-stack.md`. Optional `[path-to-prd]` argument lets you point at a non-default PRD location (e.g., `/10x-tech-stack-selector @context/foundation/prd-v2.md`); without it the skill defaults to `context/foundation/prd.md`. Use AFTER `/10x-prd`, BEFORE `/10x-bootstrapper`. |
| **Re-run upstream if needed** | |
| `/10x-init` / `/10x-shape` / `/10x-prd` | Bundled so you can fix the PRD mid-flight. If `/10x-tech-stack-selector` surfaces a gap (e.g., a Functional Requirement that forces a feature your recommended starter doesn't carry), re-run `/10x-prd` to amend the PRD before the stack pick. |

### How the chain hands off

- `/10x-tech-stack-selector` reads `context/foundation/prd.md` frontmatter (`product_type`, `target_scale`, `timeline_budget`) as priors. If the PRD is absent, it refuses with a one-sentence redirect to `/10x-shape` — no inline mini-PRD fallback.
- The skill writes `context/foundation/tech-stack.md` with a 4-key frontmatter (`starter_id`, `package_manager`, `project_name`, `hints`) plus a one-paragraph `## Why this stack` body. The hand-off is intentionally minimal — bootstrapper does not parse rationale, only fields.
- `/10x-bootstrapper` (Lesson 3) reads `tech-stack.md` and the registry to scaffold the project.

### What tech-stack-selector captures (and what it does NOT)

- **Captured**: starter pick (registry-shaped), language family, package manager (open string per ecosystem — `pnpm`, `uv`, `bundle`, `cargo`, etc.), team size, deployment target (drawn from the chosen starter's `deployment_defaults`), CI/CD provider + flow, bootstrapper confidence (`verified | first-class | best-effort`), path taken (standard | custom), self-check answers (custom path), quality override (set when the user proceeds with a starter that failed ≥1 agent-friendly gate), feature flags (auth/payments/realtime/AI/background-jobs).
- **NOT captured (deliberate)**: strategic test plan, strategic deployment plan, strategic implementation decisions. Those are downstream of stack selection — a future technical-roadmap concern, not yet planned. Tech-stack-selector owns *framework-shaped* test/deploy/CI choices because those are inseparable from stack pick; what defers is the *strategic* layer ("we TDD on X surface", "preview environment per PR").

### The opening choice (load-bearing)

The first question is an explicit choice — never silent. The skill names the recommended starter for your `(product_type, language_family)` cell up front and asks for explicit confirmation:

- **Standard path** — accept the recommended default. The skill skips the feature audit, team profile, tech preferences, and framework-variant questions; it asks only the deployment, CI/CD, and project-name questions. The hand-off records `path_taken: standard` under `hints`.
- **Custom path** — design your own. The skill walks the full follow-up set (feature audit, team profile, tech preferences, deployment, CI/CD, framework variant), drills into a testing-runner question only when the chosen starter leaves it ambiguous, and closes with a 5-point readiness self-check (from prework lesson 4.1) before locking in. The hand-off records `path_taken: custom` and populates `self_check_answers`.

The recommended-default-per-cell map is multi-language: web/JS and saas/JS both → 10x-astro-starter (the 10x-branded starter leads whenever it competes in a JS cell); api/JS → hono; api/Python → fastapi; web/Python → django; web/Ruby → rails; api/Go → go; api/Rust → axum; mobile/Dart → flutter; desktop/Rust → tauri; etc. Cells with no vetted default carry `<none>` and force the custom path.

### Quality gates (agent-friendly criteria)

Every starter card carries four booleans the LLM filters against:

1. **Typed** — explicit types/schemas the agent can reason from without running the program.
2. **Convention-based** — strong opinions on layout, routing, configuration.
3. **Popular in training data** — assessed *per language family*, not globally (Django is popular within Python training data; Spring within Java; etc.).
4. **Well-documented** — current, version-pinned, link-able docs.

Candidates failing any gate are excluded from the unprompted recommendation set. If you explicitly name a failing starter as your preference, the skill challenges that pick — surfacing the strongest higher-criteria alternative AND the compensation path (CLAUDE.md instructions that patch the gaps) — and asks you to confirm or pivot. Confirming the known-friction pick records the override on the hand-off so bootstrapper can adjust.

### Bootstrapper confidence

Every recommendation surfaces `bootstrapper_confidence` verbatim — never silently elided:

- **`verified`** — bootstrapper has been run end-to-end on this stack; scaffolding will be smooth.
- **`first-class`** — registered with a valid CLI, expected to work but not battle-tested; expect mostly-smooth scaffolding with occasional manual steps.
- **`best-effort`** — limited support; manual steps likely; expect friction (and bootstrapper's CLAUDE.md generation compensates with extra ecosystem-specific context).

This is the heads-up before running `/10x-bootstrapper` so you know what to expect.

### Foundation paths used by this lesson

- `context/foundation/prd.md` — input (from Lesson 1)
- `context/foundation/tech-stack.md` — output (the chain hand-off)
- `context/foundation/lessons.md` — recurring rules & pitfalls
- `docs/reference/contract-surfaces.md` — load-bearing names registry

### Universal language

The shipped skill carries no 10xDevs / cohort / certification references. The recommended-default registry is multi-language (JS, Python, Ruby, Java, Go, Rust, PHP, .NET, Dart) and the cohort's `10x-astro-starter` is one card in the JS+web cell — not "the" recommended path for everyone.

Skills must not write to `context/archive/`. Archived changes are immutable; if a resolved target path starts with `context/archive/`, abort with: "This change is archived. Open a new change with `/10x-new` instead."

<!-- END @przeprogramowani/10x-cli -->
