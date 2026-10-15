---
project: mail-triage-agent
researched_at: 2026-10-15
recommended_platform: Docker Compose (local, single machine)
runner_up: Podman with podman compose (local, single machine)
context_type: mvp
tech_stack:
  language: python 3.11
  framework: fastapi
  runtime: uvicorn on the official python image, plus ollama/ollama (CPU-only) and axllent/mailpit
---

## Recommendation

**Run locally with Docker Compose. There is no hosted deployment.**

The PRD fixes the platform before any scoring. The relevant NFRs are "no message content or sender address leaves the local environment", "single machine only" and "runs on a CPU-only laptop with 16 GB RAM". FR-008 asks for "one command after cloning", and `tech-stack.md` names `docker compose up -d` with three services. The developer confirmed during the interview that there will be no deployment and that the app runs locally in containers. Docker Compose is the only local option that satisfies the one-command start, healthcheck-gated readiness and reviewer familiarity at the same time.

Interview answers:
- Persistent connections: no. The API is request/response, but Ollama and Mailpit are long-running containers.
- Cost vs DX: no strong preference.
- Familiarity: not applicable, because there is no deployment.
- Reach: one machine.
- Co-location: all three services sit in one Compose file.

## Platform Comparison

Hard filters applied:
- **PRD local-only NFR and the "no deployment" decision.** All hosted candidates are dropped, whatever their features. A hosted target would send message content to a third party and would expose an unauthenticated endpoint that runs CPU inference.
- **Tech stack.** The platform must run a ~2 GB tool-calling model with Ollama next to an SMTP catcher. Edge and serverless runtimes (Cloudflare Workers, Vercel, Netlify) could not do this even without the first filter.

| Platform | CLI-first | Managed/Serverless | Agent-readable docs | Stable deploy API | MCP / Integration | Total |
|---|---|---|---|---|---|---|
| **Docker Compose** (Docker Engine in WSL2 or Docker Desktop) | Pass | Partial | Pass | Pass | Partial | 3 Pass, 2 Partial |
| Podman + `podman compose` | Pass | Partial | Partial | Partial | Fail | 1 Pass, 3 Partial, 1 Fail |
| Native host processes (`uv run` + native Ollama + Mailpit binary) | Pass | Fail | Pass | Fail | Fail | 2 Pass, 3 Fail |
| Cloudflare Workers + Pages | Dropped by hard filter: local-only NFR; Python plus a local LLM can't run on the edge runtime |||||
| Vercel | Dropped by hard filter: local-only NFR; serverless functions can't host Ollama |||||
| Netlify | Dropped by hard filter: local-only NFR; serverless functions can't host Ollama |||||
| Fly.io | Dropped by hard filter: local-only NFR |||||
| Railway | Dropped by hard filter: local-only NFR |||||
| Render | Dropped by hard filter: local-only NFR |||||

Notes per scored option:
- **Docker Compose.**
  - Every routine operation is a CLI command: `up -d --wait`, `ps`, `logs`, `down`, `build`.
  - Managed is "Partial". Compose handles networking between services, restart policies and health-gated startup, but the host OS, WSL2 memory and disk are the developer's to manage.
  - Docs are Markdown in the public `docker/docs` repository.
  - `up --wait` returns a non-zero exit code when services fail to become healthy. One caveat is listed in the risk register.
  - MCP is "Partial". Docker publishes MCP tooling, but its status wasn't checked and it isn't needed: the CLI covers everything at this scale.
- **Podman compose.**
  - Reads the same file and needs no daemon.
  - `depends_on: condition: service_healthy` behaves differently between `podman-compose` (Python) and `podman compose` (Go).
  - Health status can stay at `starting` when systemd isn't running, and one reported pitfall is that the default OCI image format drops `HEALTHCHECK`.
  - Reviewers are less likely to have it installed.
- **Native processes.**
  - The fastest loop for measuring models. Native Ollama 0.40.0 is already installed on the dev machine.
  - Needs three manual installs and has no single start command, so it fails FR-008.

### Shortlisted Platforms

#### 1. Docker Compose (Recommended)

This is the stack the brief and tech-stack hand-off specify, so it carries zero translation risk. `docker compose up -d --wait` is the "start and wait until ready" variant that FR-010 asks the README to document. Compose's health-gated `depends_on` is how the API waits for Ollama and Mailpit, and the API's own healthcheck is what makes "ready only after warm-up" (FR-003) visible to `--wait`.

#### 2. Podman + `podman compose`

It is a near drop-in, since the same `docker-compose.yml` should work. It scored lower because health-gated readiness, the core of FR-003 and FR-008, varies by implementation and environment, and because a reviewer is less likely to have Podman installed. It's worth it only if Docker can't be installed on a target machine.

#### 3. Native host processes

Useful during implementation for comparing `qwen2.5:3b` and `llama3.2:3b` quickly against the native Ollama already on the machine. It can't be the delivery path: it fails the one-command start and pushes three installs onto the reviewer.

## Anti-Bias Cross-Check: Docker Compose

### Devil's Advocate: Weaknesses

1. **Docker isn't installed on the dev machine, and the deadline is tomorrow.** On 2026-10-15, `docker` was missing from the Windows PATH and from WSL Ubuntu-22.04. Until it is installed, nothing about the compose setup can be checked end to end.
2. **The WSL2 memory cap is 7 GB.** WSL2 gives its VM half of host RAM by default, and this 16 GB host reports 7 GB inside WSL. The Q4_K_M models are 1.9 GB (`qwen2.5:3b`) and 2.0 GB (`llama3.2:3b`) on disk, and they need more resident memory once loaded with context. Add the LangChain API and Mailpit and it should fit, but the headroom is thin. A larger context window or a second loaded model would cause OOM-kills.
3. **The disk budget is at risk.** The PRD allows 10 GB of free disk. I couldn't confirm the official `ollama/ollama` image size (it bundles GPU runtime libraries). Unofficial rebuilds are about 3–4 GB compressed. Add the ~2 GB model and the Python image, and the budget is tight.
4. **The Ollama image has no curl and no health endpoint.** A curl-based healthcheck stays unhealthy forever. A one-shot model-pull container combined with `docker compose up --wait` has been reported to return exit 1 even when the one-shot exits 0 (Compose v2.34.0). That would make the README's "wait until ready" command report failure on a working stack.
5. **Port 11434 collides with native Ollama.** Native Ollama is installed on this host and listens on 11434. Publishing the containerized Ollama on the same host port either fails to bind or quietly sends tests to the wrong server.

### Pre-Mortem: How This Could Fail

The demo was due Friday. On Thursday afternoon Docker Desktop was installed in a hurry and needed a reboot. The compose file worked on the second try, but the Ollama healthcheck called curl, which the image doesn't ship, so it stayed unhealthy until it was patched to `ollama list`. Model pulling then moved into a one-shot init container, and `docker compose up --wait` started exiting 1 even though everything was running. The README's "wait until ready" command now lied, and nobody noticed because everyone re-ran it by hand. The reviewer, on a 16 GB laptop, started the stack and sent a request: 12 s. After a coffee break the next request took 48 s, because Ollama's default keep-alive had unloaded the model while `/health` still reported ready. On a second reviewer's machine, `docker system df` showed the images and model eating most of the 10 GB budget. The review notes read: "one-command start unreliable; latency NFR not met after idle." None of this was a platform failure. Each was a small, untested assumption that a clean-machine run the day before would have caught.

### Unknown Unknowns

- **Readiness goes stale.** Ollama unloads an idle model after about 5 minutes by default (`OLLAMA_KEEP_ALIVE`). After that, "ready" no longer means "warm", and the next request pays the reload cost against the 30 s target. Set `OLLAMA_KEEP_ALIVE=-1` on the Ollama service.
- **`--wait` and exited containers.** `docker compose up --wait` waits for services to be *running or healthy*, so a container that has already exited doesn't count. Have the API pull and warm up the model over Ollama's HTTP API at startup, and make the API's healthcheck the readiness signal. Don't add an init service.
- **WSL2 memory is set outside Docker.** On Windows the limit comes from `%UserProfile%\.wslconfig` (`[wsl2] memory=`) followed by `wsl --shutdown`, not from Docker Desktop's settings. Reviewers on Windows inherit the same 50% default.
- **Docker on macOS can't use the Apple GPU.** That matches the PRD's CPU-only premise, but latency measured on this Windows/WSL2 machine won't transfer exactly to an Apple-silicon reviewer. Record the hardware next to the measured figure in the README.
- **CRLF line endings in containers.** Shell scripts committed from Windows with CRLF fail inside Linux containers with `/bin/sh^M: not found`. **Already mitigated**: `.gitattributes` contains `* text=auto eol=lf`.

## Operational Story

There's no hosted environment, so "operations" means one developer machine and each reviewer's machine.

- **Preview deploys**: none. Each branch is checked out and run locally with `docker compose up -d --build --wait`. There are no preview URLs and nothing is exposed beyond `localhost`.
- **Secrets**: none needed. Ollama and Mailpit need no credentials, and the department addresses and `From` are fixed configuration in code. Non-secret settings (model tag, ports) go in `docker-compose.yml`. If a `.env` is ever added it stays git-ignored, and no keys are committed.
- **Rollback**:
  - Code: `git checkout <previous-commit>`, then `docker compose up -d --build --wait`. This takes about a minute with cached layers.
  - Model: change the pinned model tag back and restart.
  - There's no database and no migrations, so no data caveats apply. The model cache lives in a named volume, which `down -v` deletes, forcing a ~2 GB re-download.
- **Approval**:
  - The agent may run `docker compose up/down/build/ps/logs`, `docker stats` and `docker system df`, and may send test requests.
  - A human must install Docker, edit `.wslconfig` and restart WSL, run `docker compose down -v`, run `docker system prune`, and stop or uninstall the native Ollama app.
- **Logs**:
  - `docker compose ps` shows health status.
  - `docker compose logs -f api` (or `ollama`, `mailpit`) shows each service's log.
  - `curl http://localhost:8000/health` shows readiness.
  - The Mailpit UI at `http://localhost:8025` shows delivered email.
  - Application logs must never contain message content or sender addresses (PRD NFR), so the `api` logs show request outcomes and departments only.

## Risk Register

| Risk | Source | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| Docker not installed on dev machine; deadline 2026-10-16 | Devil's advocate | H | H | Install Docker first (Engine in WSL Ubuntu-22.04 via Docker's apt repo with `docker-compose-plugin`, or Docker Desktop with the WSL2 backend). Confirm `docker compose version` reports v2 before writing any compose code. |
| WSL2 VM capped at 7 GB; model plus API OOM-killed | Devil's advocate | M | H | Measure with `docker stats` while a request runs. If it's tight, raise `memory=` in `.wslconfig` (human step). Keep Ollama's context window at the default and load one model only. |
| Images plus model exceed the 10 GB disk NFR | Devil's advocate | M | M | Use `python:3.11-slim` (still the official image). Run `docker system df` after the first full start and record the figure in the README. |
| Ollama healthcheck fails (no curl, no `/api/health`) | Devil's advocate | H | M | Use `ollama list` as the Ollama healthcheck command. Use Python `urllib` (not curl) in the API healthcheck, because slim images lack curl. |
| `up --wait` exits 1 because of a one-shot init container | Devil's advocate / Unknown unknowns | M | H | Use no one-shot services. The API pulls and warms up the model at startup over Ollama's HTTP API, and its `/health` healthcheck is what `--wait` gates on. |
| Host port 11434 conflicts with native Ollama | Devil's advocate | H | M | Don't publish Ollama's port. The API reaches it at `http://ollama:11434` on the Compose network. Publish only 8000 (API) and 8025 (Mailpit UI). |
| Model unloaded after idle; request exceeds 30 s while `/health` says ready | Pre-mortem / Unknown unknowns | H | H | Set `OLLAMA_KEEP_ALIVE=-1` on the Ollama service. Measure latency again after 10 minutes idle before recording the README figure. |
| Latency measured on WSL2 doesn't hold on a reviewer's Apple-silicon machine | Unknown unknowns | M | M | Record the CPU, RAM and OS next to the measured figure in the README, and state it as "measured on". Check that all three images publish arm64. |
| README "wait until ready" command never run on a clean machine | Pre-mortem | M | H | Before submission: `docker compose down -v`, then a fresh `git clone`, then the exact README command, timed against the 15-minute NFR. |
| CRLF line endings break container scripts | Unknown unknowns | L | M | Already mitigated by `.gitattributes` (`* text=auto eol=lf`). |
| `podman compose` health-gated waits differ (if a reviewer uses Podman) | Research finding | L | M | Document Docker Compose v2 as the supported runtime in the README. Podman is best effort. |

## Getting Started

1. **Install Docker** (human step). Either install Docker Engine inside WSL Ubuntu-22.04 from Docker's official apt repository (`docker-ce`, `docker-ce-cli`, `containerd.io`, `docker-compose-plugin`), or install Docker Desktop with the WSL2 backend. Then confirm:
   - `docker compose version` reports Compose v2.
   - `docker run --rm hello-world` succeeds.
2. **Write `docker-compose.yml` with three services:**
   - `api`: built from the official `python:3.11-slim` image with uv. Publish `8000`. It depends on `ollama` and `mailpit` with `condition: service_healthy`. Its healthcheck calls `/health` through Python `urllib`.
   - `ollama`: `ollama/ollama` with a named volume at `/root/.ollama` and `OLLAMA_KEEP_ALIVE=-1`. No published port. Healthcheck `["CMD", "ollama", "list"]`.
   - `mailpit`: pin a tag of `axllent/mailpit`. Publish `8025` only; SMTP `1025` stays internal. The built-in `/mailpit readyz` healthcheck covers it.
3. **Make readiness real.** On startup the API pulls the chosen model over Ollama's HTTP API and runs one warm-up generation. `/health` returns ready only after both succeed, and requests before that get an explicit "not ready" response (FR-003).
4. **Start and verify:**
   - `docker compose up -d --build --wait`, then `docker compose ps` (all healthy).
   - Open `http://localhost:8000/api/v1/docs`.
   - Send the US-01 sample request.
   - Confirm the email in `http://localhost:8025`.
5. **Measure and record:**
   - Compare `qwen2.5:3b` and `llama3.2:3b` on the US-01 to US-03 examples. Native Ollama is a quick way to shortlist; confirm the winner in the container.
   - Record latency (warm and after idle), `docker stats` peak memory and `docker system df` disk in the README.

## Out of Scope

The following were not evaluated in this research:
- Docker image configuration (the Dockerfile itself)
- CI/CD pipeline setup (GitHub Actions checks are noted in `tech-stack.md` only)
- Hosted or production deployment of any kind (excluded by the PRD's local-only NFR and the developer's "no deployment" decision)
- Production-scale architecture (multi-region, HA, DR)
