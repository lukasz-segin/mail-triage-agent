---
bootstrapped_at: 2026-10-14T13:52:06Z
starter_id: fastapi
starter_name: FastAPI
project_name: mail-triage-agent
language_family: python
package_manager: uv
cwd_strategy: native-cwd
bootstrapper_confidence: first-class
phase_3_status: ok
audit_command: pip-audit
---

## Hand-off

```yaml
starter_id: fastapi
package_manager: uv
project_name: mail-triage-agent
hints:
  language_family: python
  team_size: solo
  deployment_target: self-host
  ci_provider: github-actions
  ci_default_flow: manual-promotion
  bootstrapper_confidence: first-class
  path_taken: standard
  quality_override: false
  self_check_answers: null
  has_auth: false
  has_payments: false
  has_realtime: false
  has_ai: true
  has_background_jobs: false
```

### Why this stack

A solo developer building a small Python API against a hard deadline (2026-10-16) needs the vetted default for `(api, python)`: FastAPI passes all four agent-friendly gates and generates the Swagger/OpenAPI docs the brief requires at `/api/v1/docs`. AI support is added on top, because no Python starter includes it: a LangChain agent backed by a local `ollama/ollama` model (CPU-only; small tool-calling model such as `qwen2.5:3b` or `llama3.2:3b`, chosen by measurement). The agent must send the email through a dedicated send-email tool via tool calling. The tool accepts only the department, injects the body and `Reply-To` from the request, rejects addresses outside the five-address list, and runs at most once per request. The caller gets back the department from the tool's execution record. Deployment is self-host: one `docker-compose.yml` with the Python API on the official `python` image, Ollama and Mailpit (`axllent/mailpit`). `docker compose up -d` pulls and warms up the model, and a `/health` healthcheck marks the API ready only after warm-up. CI runs checks on GitHub Actions with manual promotion, since nothing is hosted. Scaffolding support is first-class, not yet battle-tested.

## Pre-scaffold verification

| Signal      | Value   | Severity | Notes                                                                                           |
| ----------- | ------- | -------- | ----------------------------------------------------------------------------------------------- |
| npm package | not run | —        | non-JS starter                                                                                  |
| GitHub repo | not run | —        | card `docs_url` (https://fastapi.tiangolo.com) is not a GitHub URL; no recency signal available |

Toolchain note: `uv` 0.13.1 was installed by the user-approved `python -m pip install --user uv` during a prior failed run. Its script directory is not on PATH, so commands ran as `python -m uv`.

Prior attempt: an earlier run on 2026-10-14 failed at the scaffold step because the pre-existing `README.md` was UTF-16 and the `uv_build` backend requires UTF-8. The user removed `README.md` and the partial scaffold files before this run.

## Scaffold log

**Resolved invocation**: `uv init . && uv add fastapi uvicorn` (executed as `python -m uv init . && python -m uv add fastapi uvicorn`)
**Strategy**: native-cwd
**Exit code**: 0
**Pre-flight files-to-touch**: pyproject.toml, .python-version, README.md, src/ package or main.py, uv.lock, .venv/ (none pre-existing)
**Files written by CLI**: 5, plus `.venv/`: `.python-version`, `pyproject.toml`, `README.md` (empty), `src/mail_triage_agent/__init__.py`, `uv.lock`
**Pre-existing files preserved**: none overwritten; `.gitignore` untouched (uv skips `.gitignore` inside an existing git repo). `.venv/` is already covered by the existing `.gitignore`.

Layout note: `uv init` produced a packaged layout (`src/mail_triage_agent/`, `uv_build` backend, `mail-triage-agent` console script), not the flat `main.py` app layout.

Packages installed (15): annotated-doc 0.0.5, annotated-types 0.8.0, anyio 4.15.1, click 8.5.0, fastapi 0.143.1, h11 0.16.0, idna 3.20, mail-triage-agent 0.1.0 (editable project), opentelemetry-api 1.45.1, pydantic 2.14.1, pydantic-core 2.50.1, starlette 1.8.0, typing-extensions 4.16.0, typing-inspection 0.4.4, uvicorn 0.54.0.

## Post-scaffold audit

**Tool**: pip-audit (run ephemerally via `uv tool run pip-audit -r <uv export, no project> --disable-pip --format json`, because pip-audit is not installed locally)
**Summary**: 0 CRITICAL, 0 HIGH, 0 MODERATE, 0 LOW (14 locked dependencies scanned; "No known vulnerabilities found")
**Direct vs transitive**: not distinguished by this tool (direct dependencies: fastapi, uvicorn)

#### CRITICAL findings

None.

#### HIGH findings

None.

#### MODERATE findings

None.

#### LOW / INFO findings

None.

## Hints recorded but not acted on

| Hint                    | Value            |
| ----------------------- | ---------------- |
| bootstrapper_confidence | first-class      |
| quality_override        | false            |
| path_taken              | standard         |
| self_check_answers      | null             |
| team_size               | solo             |
| deployment_target       | self-host        |
| ci_provider             | github-actions   |
| ci_default_flow         | manual-promotion |
| has_auth                | false            |
| has_payments            | false            |
| has_realtime            | false            |
| has_ai                  | true             |
| has_background_jobs     | false            |

## Next steps

Next: a future skill will set up agent context (CLAUDE.md, AGENTS.md). For now, your project is scaffolded and verified — happy hacking.

Useful manual steps in the meantime:
- `git init` (if you have not already) to start your own repo history.
- Review any `.scaffold` siblings the conflict policy created and decide which version of each file to keep.
- Address audit findings per your project's risk tolerance — the full breakdown is in this log.
