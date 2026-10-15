import smtplib
import typing

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from mail_triage_agent import triage

SENDER = "jan.nowak@example.com"
MESSAGE = "Nie działa mi komputer"


class ScriptedModel(GenericFakeChatModel):
    """Replays scripted AI messages; tool binding is a no-op."""

    def bind_tools(self, tools, **kwargs):
        return self


def agent_replying(*replies: AIMessage):
    return triage.build_agent(ScriptedModel(messages=iter(replies)))


def call(department: str, call_id: str = "call-1") -> dict:
    return {"name": "send_email", "args": {"department": department}, "id": call_id}


@pytest.fixture
def sent(monkeypatch) -> list:
    outbox = []
    monkeypatch.setattr(triage, "send_mail", outbox.append)
    return outbox


def test_valid_call_sends_one_email_with_injected_fields(sent):
    agent = agent_replying(
        AIMessage(content="", tool_calls=[call("help-desk@example.com")])
    )

    assert triage.route(SENDER, MESSAGE, agent=agent) == "help-desk@example.com"

    assert len(sent) == 1
    msg = sent[0]
    assert msg["To"] == "help-desk@example.com"
    assert msg["Reply-To"] == SENDER
    assert msg["From"] == triage.FROM_ADDRESS
    assert msg["Subject"] == triage.SUBJECT
    assert msg.get_content() in (MESSAGE, MESSAGE + "\n")


def test_parallel_second_call_sends_nothing(sent):
    agent = agent_replying(
        AIMessage(
            content="",
            tool_calls=[
                call("kadry@example.com", "call-1"),
                call("human-resources@example.com", "call-2"),
            ],
        )
    )

    department = triage.route(SENDER, "Chciałbym zgłosić urlop na jutro", agent=agent)

    assert len(sent) == 1
    assert department == sent[0]["To"]


def test_no_tool_call_raises_no_decision_and_sends_nothing(sent):
    agent = agent_replying(AIMessage(content="Please contact the help desk."))

    with pytest.raises(triage.NoDecision):
        triage.route(SENDER, MESSAGE, agent=agent)

    assert sent == []


def test_smtp_failure_raises_send_failed_and_records_nothing(monkeypatch):
    agent = agent_replying(
        AIMessage(content="", tool_calls=[call("help-desk@example.com")])
    )
    contexts = []
    real_context = triage.TriageContext

    def tracking_context(**kwargs):
        contexts.append(real_context(**kwargs))
        return contexts[-1]

    def refuse(msg):
        raise smtplib.SMTPException("server said no")

    monkeypatch.setattr(triage, "TriageContext", tracking_context)
    monkeypatch.setattr(triage, "send_mail", refuse)

    with pytest.raises(triage.SendFailed):
        triage.route(SENDER, MESSAGE, agent=agent)

    assert contexts[0].delivered_to is None


def test_model_cannot_set_body_or_reply_to():
    schema = triage.send_email.tool_call_schema.model_json_schema()

    assert set(schema["properties"]) == {"department"}
    assert set(schema["properties"]["department"]["enum"]) == set(
        typing.get_args(triage.Department)
    )
    assert len(triage.DEPARTMENTS) == 5
