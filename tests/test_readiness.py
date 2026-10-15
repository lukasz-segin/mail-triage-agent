import asyncio

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from ollama import ResponseError

from mail_triage_agent import readiness
from mail_triage_agent.app import app


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    monkeypatch.setattr(readiness, "state", readiness.Readiness())


class FakeOllama:
    def __init__(self, model_present=True, chat_failures=0):
        self.model_present = model_present
        self.chat_failures = chat_failures
        self.calls = []

    async def show(self, model):
        self.calls.append("show")
        if not self.model_present:
            raise ResponseError("model not found", 404)

    async def pull(self, model):
        self.calls.append("pull")
        self.model_present = True

    async def chat(self, model, messages, options, keep_alive):
        self.calls.append("chat")
        self.chat_options, self.chat_keep_alive = options, keep_alive
        if self.chat_failures:
            self.chat_failures -= 1
            raise ConnectionError("ollama not reachable")


def test_health_is_503_while_starting():
    # No `with`, so the lifespan (real warm-up) does not run.
    response = TestClient(app).get("/health")

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "10"
    assert response.json()["detail"]["status"] == "starting"


def test_health_is_200_when_ready():
    readiness.state.status = "ready"

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "model": readiness.MODEL}


def test_require_ready_blocks_other_routes_until_ready():
    gated = FastAPI()

    @gated.post("/triage", dependencies=[Depends(readiness.require_ready)])
    def triage():
        return {"ok": True}

    client = TestClient(gated)
    assert client.post("/triage").status_code == 503
    readiness.state.status = "ready"
    assert client.post("/triage").status_code == 200


def test_warm_up_pulls_missing_model_then_is_ready():
    fake = FakeOllama(model_present=False)

    asyncio.run(readiness.warm_up(fake))

    assert fake.calls == ["show", "pull", "chat"]
    assert fake.chat_options["num_ctx"] == readiness.MODEL_OPTIONS["num_ctx"]
    assert fake.chat_keep_alive == -1
    assert readiness.state.status == "ready"


def test_warm_up_skips_pull_when_model_present():
    fake = FakeOllama(model_present=True)

    asyncio.run(readiness.warm_up(fake))

    assert "pull" not in fake.calls
    assert readiness.state.status == "ready"


def test_warm_up_retries_until_success(monkeypatch):
    seen_errors = []

    async def no_sleep(_):
        seen_errors.append(readiness.state.last_error)

    monkeypatch.setattr(readiness.asyncio, "sleep", no_sleep)
    fake = FakeOllama(chat_failures=2)

    asyncio.run(readiness.warm_up(fake))

    assert fake.calls.count("chat") == 3
    assert seen_errors == ["ConnectionError: ollama not reachable"] * 2
    assert readiness.state.status == "ready"
    assert readiness.state.last_error is None
