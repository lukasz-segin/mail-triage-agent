import pytest
from fastapi.testclient import TestClient

from mail_triage_agent import readiness, triage
from mail_triage_agent.app import app

REQUEST = {"email": "jan.nowak@example.com", "message": "Nie działa mi komputer"}


@pytest.fixture(autouse=True)
def ready(monkeypatch):
    monkeypatch.setattr(readiness, "state", readiness.Readiness(status="ready"))


def test_returns_department_from_route(monkeypatch):
    monkeypatch.setattr(triage, "route", lambda email, message: "help-desk@example.com")

    response = TestClient(app).post("/api/v1/triage", json=REQUEST)

    assert response.status_code == 200
    assert response.json() == {"department": "help-desk@example.com"}


@pytest.mark.parametrize(
    ("error", "status"),
    [(triage.NoDecision, 502), (triage.SendFailed, 502), (triage.RoutingTimeout, 504)],
)
def test_routing_failures_map_to_fixed_errors(monkeypatch, error, status):
    def fail(email, message):
        raise error()

    monkeypatch.setattr(triage, "route", fail)

    response = TestClient(app).post("/api/v1/triage", json=REQUEST)

    assert response.status_code == status
    assert "no email was sent" in response.json()["detail"]
    assert REQUEST["email"] not in response.text
    assert REQUEST["message"] not in response.text


def test_503_while_not_ready_and_route_never_called(monkeypatch):
    monkeypatch.setattr(readiness, "state", readiness.Readiness())
    calls = []
    monkeypatch.setattr(triage, "route", lambda *args: calls.append(args))

    response = TestClient(app).post("/api/v1/triage", json=REQUEST)

    assert response.status_code == 503
    assert calls == []
