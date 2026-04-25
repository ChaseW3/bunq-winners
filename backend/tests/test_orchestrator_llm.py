import pytest
from backend.orchestrator.llm import run_llm_turn
from backend.session.store import SessionStore
from backend.tests.fakes import FakeBunqClient


class ScriptedLLM:
    """Fake LLMClient that replays a pre-scripted list of responses."""

    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def messages_create(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("ScriptedLLM ran out of scripted responses")
        return self._responses.pop(0)


def _tool_use(tid: str, name: str, inp: dict) -> dict:
    return {"type": "tool_use", "id": tid, "name": name, "input": inp}


def _text(s: str) -> dict:
    return {"type": "text", "text": s}


@pytest.fixture
def session() -> tuple[SessionStore, str]:
    store = SessionStore()
    sid = store.create(bunq_user_id=1, primary_account_id=42)
    return store, sid


def test_reasons_over_recent_payments(session):
    store, sid = session
    llm = ScriptedLLM([
        {"content": [_tool_use("t1", "list_recent_payments", {"limit": 10})], "stop_reason": "tool_use"},
        {"content": [_text("About 65 euros at Albert Heijn and a 40 euro Uber.")], "stop_reason": "end_turn"},
    ])
    out = run_llm_turn(llm, FakeBunqClient(), store, sid, user_text="what did I spend this week?")
    assert "Albert Heijn" in out["reply"]
    assert len(out["tool_calls"]) == 1
    assert out["tool_calls"][0]["name"] == "list_recent_payments"
    assert out["tool_calls"][0]["input"] == {"limit": 10}
    assert out["tool_calls"][0]["is_error"] is False


def test_reasons_over_savings_balance(session):
    store, sid = session
    llm = ScriptedLLM([
        {"content": [_tool_use("t1", "list_savings_accounts", {})], "stop_reason": "tool_use"},
        {"content": [_text("Your savings account has 3,400 euros.")], "stop_reason": "end_turn"},
    ])
    out = run_llm_turn(llm, FakeBunqClient(), store, sid, user_text="how's my savings?")
    assert "3,400" in out["reply"]
    assert out["tool_calls"][0]["name"] == "list_savings_accounts"


def test_combines_multiple_read_tools(session):
    store, sid = session
    llm = ScriptedLLM([
        {"content": [_tool_use("t1", "get_balance", {})], "stop_reason": "tool_use"},
        {"content": [_tool_use("t2", "list_scheduled_payments", {})], "stop_reason": "tool_use"},
        {"content": [_text("You have 1,247 euros and 50 euros scheduled.")], "stop_reason": "end_turn"},
    ])
    out = run_llm_turn(llm, FakeBunqClient(), store, sid, user_text="can I afford dinner tonight?")
    names = [c["name"] for c in out["tool_calls"]]
    assert names == ["get_balance", "list_scheduled_payments"]


def test_draft_flow_still_requires_confirmation(session):
    store, sid = session
    client = FakeBunqClient()
    llm = ScriptedLLM([
        {"content": [_tool_use("t1", "create_draft_payment", {
            "iban": "NL00BUNQ0000000002", "amount": "20.00",
            "description": "pizza", "counterparty_name": "Finn Bunq",
        })], "stop_reason": "tool_use"},
        {"content": [_text("Sending twenty euros to Finn Bunq. Say yes to confirm.")], "stop_reason": "end_turn"},
    ])
    out = run_llm_turn(llm, client, store, sid, user_text="send 20 to Finn for pizza")
    assert client.confirmed == []
    assert len(client.draft_calls) == 1
    assert store.get(sid)["pending_draft"]["draft_id"] == "draft-1"
    assert "confirm" in out["reply"].lower()


def test_tool_error_is_captured_and_loop_continues(session):
    store, sid = session

    class BoomClient(FakeBunqClient):
        def list_savings_accounts(self):
            raise RuntimeError("api down")

    llm = ScriptedLLM([
        {"content": [_tool_use("t1", "list_savings_accounts", {})], "stop_reason": "tool_use"},
        {"content": [_text("Sorry — I couldn't reach savings right now.")], "stop_reason": "end_turn"},
    ])
    out = run_llm_turn(llm, BoomClient(), store, sid, user_text="savings?")
    assert out["tool_calls"][0]["is_error"] is True
    assert "couldn't" in out["reply"]


def test_system_prompt_includes_reasoning_guidance(session):
    store, sid = session
    llm = ScriptedLLM([
        {"content": [_text("ok")], "stop_reason": "end_turn"},
    ])
    run_llm_turn(llm, FakeBunqClient(), store, sid, user_text="hi")
    system_sent = llm.calls[0]["system"]
    assert "Summarize" in system_sent or "summariz" in system_sent.lower()
    assert "confirm_draft_payment" in system_sent


def test_accessibility_events_includes_full_amount_when_amount_in_reply(session):
    store, sid = session
    llm = ScriptedLLM([
        {"content": [_text("Your balance is one thousand two hundred forty-seven euros.")], "stop_reason": "end_turn"},
    ])
    out = run_llm_turn(llm, FakeBunqClient(), store, sid, user_text="what's my balance?")
    events = out["accessibility_events"]
    types = [e["type"] for e in events]
    assert "SPEECH" in types


def test_accessibility_events_includes_voice_confirm_on_draft(session):
    store, sid = session
    llm = ScriptedLLM([
        {"content": [_tool_use("t1", "create_draft_payment", {
            "iban": "NL00BUNQ0000000002", "amount": "20.00",
            "description": "pizza", "counterparty_name": "Finn Bunq",
        })], "stop_reason": "tool_use"},
        {"content": [_text("Sending twenty euros to Finn Bunq. Say confirm to proceed, or cancel to stop.")], "stop_reason": "end_turn"},
    ])
    out = run_llm_turn(llm, FakeBunqClient(), store, sid, user_text="send 20 to Finn for pizza")
    events = out["accessibility_events"]
    event_types = [(e["type"], e["event"]) for e in events]
    assert ("ACTION", "voice-confirm") in event_types
    assert ("SPEECH", "readback") in event_types


def test_accessibility_events_includes_error_on_tool_failure(session):
    store, sid = session

    class BoomClient(FakeBunqClient):
        def list_savings_accounts(self):
            raise RuntimeError("api down")

    llm = ScriptedLLM([
        {"content": [_tool_use("t1", "list_savings_accounts", {})], "stop_reason": "tool_use"},
        {"content": [_text("Sorry — I couldn't reach savings right now.")], "stop_reason": "end_turn"},
    ])
    out = run_llm_turn(llm, BoomClient(), store, sid, user_text="savings?")
    events = out["accessibility_events"]
    types = [e["type"] for e in events]
    assert "ERROR" in types


def test_system_prompt_includes_lynn_accessibility_rules(session):
    store, sid = session
    llm = ScriptedLLM([
        {"content": [_text("ok")], "stop_reason": "end_turn"},
    ])
    run_llm_turn(llm, FakeBunqClient(), store, sid, user_text="hi")
    system_sent = llm.calls[0]["system"]
    assert "Lynn" in system_sent
    assert "NATO" in system_sent or "phonetic" in system_sent.lower()
    assert "confirm_draft_payment" in system_sent
    assert "as shown above" not in system_sent
