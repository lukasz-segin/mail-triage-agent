"""End-to-end check of the brief's examples against the running Compose stack.

Opt-in: `LIVE_STACK=1 uv run pytest -m live -s` (PowerShell: `$env:LIVE_STACK=1; uv run pytest -m live -s`).
Every one of the LIVE_RUNS (default 5) runs per case must pass.
"""

import json
import os
import time
import urllib.request

import pytest

API = os.environ.get("LIVE_API", "http://127.0.0.1:8000")
MAILPIT = os.environ.get("LIVE_MAILPIT", "http://127.0.0.1:8025")
SENDER = "jan.nowak@example.com"
LIVE_RUNS = int(os.environ.get("LIVE_RUNS", "5"))

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("LIVE_STACK") != "1", reason="needs the stack; set LIVE_STACK=1"
    ),
]


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.load(response)


def post_json(url: str, body: dict) -> tuple[int, dict]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return response.status, json.load(response)


def mailpit_total() -> int:
    return get_json(f"{MAILPIT}/api/v1/messages?limit=1")["messages_count"]


@pytest.mark.parametrize("run", range(LIVE_RUNS))
@pytest.mark.parametrize(
    ("message", "department"),
    [
        ("Nie działa mi komputer", "help-desk@example.com"),
        ("Chciałbym zgłosić urlop na jutro", "kadry@example.com"),
    ],
)
def test_request_arrives_at_owning_department(message, department, run):
    before = mailpit_total()

    started = time.monotonic()
    status, body = post_json(
        f"{API}/api/v1/triage", {"email": SENDER, "message": message}
    )
    elapsed = time.monotonic() - started
    print(f"\n{department} run {run}: {elapsed:.1f} s")

    assert status == 200
    assert body == {"department": department}
    assert mailpit_total() == before + 1

    # Newest first; the summary's ID points at the full message.
    latest = get_json(f"{MAILPIT}/api/v1/messages?limit=1")["messages"][0]
    sent = get_json(f"{MAILPIT}/api/v1/message/{latest['ID']}")
    assert [to["Address"] for to in sent["To"]] == [department]
    assert [r["Address"] for r in sent["ReplyTo"]] == [SENDER]
    assert sent["From"]["Address"] == "triage-agent@example.com"
    assert sent["Subject"] == "[Triage] New request"
    assert sent["Text"].rstrip("\r\n") == message
