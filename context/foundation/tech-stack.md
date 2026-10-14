---
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
---

## Why this stack

A solo developer building a small Python API against a hard deadline (2026-10-16) needs the vetted default for `(api, python)`: FastAPI passes all four agent-friendly gates and generates the Swagger/OpenAPI docs the brief requires at `/api/v1/docs`. AI support is added on top, because no Python starter includes it: a LangChain agent backed by a local `ollama/ollama` model (CPU-only; small tool-calling model such as `qwen2.5:3b` or `llama3.2:3b`, chosen by measurement). The agent must send the email through a dedicated send-email tool via tool calling. The tool accepts only the department, injects the body and `Reply-To` from the request, rejects addresses outside the five-address list, and runs at most once per request. The caller gets back the department from the tool's execution record. Deployment is self-host: one `docker-compose.yml` with the Python API on the official `python` image, Ollama and Mailpit (`axllent/mailpit`). `docker compose up -d` pulls and warms up the model, and a `/health` healthcheck marks the API ready only after warm-up. CI runs checks on GitHub Actions with manual promotion, since nothing is hosted. Scaffolding support is first-class, not yet battle-tested.
