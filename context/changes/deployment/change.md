---
change_id: deployment
title: Run the stack locally with Docker Compose
status: planned
created: 2026-10-15
---

# Run the stack locally with Docker Compose

Adds the Dockerfile and `docker-compose.yml` (api, `alpine/ollama`, `axllent/mailpit`), plus the model pull and warm-up gate behind `/health`, as described in `context/foundation/infrastructure.md`. The triage endpoint and agent are out of scope and come in the next change.

Plan and progress: [deployment-plan.md](deployment-plan.md).
