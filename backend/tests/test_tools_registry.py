import pytest
from backend.session.store import SessionStore
from backend.tools.registry import SCHEMAS, tool_schemas, dispatch
from backend.tests.fakes import FakeBunqClient


@pytest.fixture
def session() -> tuple[SessionStore, str]:
    store = SessionStore()
    sid = store.create(bunq_user_id=1, primary_account_id=42)
    return store, sid


def test_schemas_and_dispatch_agree():
    schema_names = {s["name"] for s in tool_schemas()}
    sample_args = {
        "get_account": {"account_id": 42},
        "get_payment": {"payment_id": 1},
        "send_payment": {"iban": "NL00BUNQ0000000001", "amount": "10.00", "description": "x", "counterparty_name": "X"},
        "create_draft_payment": {"iban": "NL00BUNQ0000000001", "amount": "10.00", "description": "x", "counterparty_name": "X"},
        "confirm_draft_payment": {"draft_id": "1"},
        "cancel_draft_payment": {"draft_id": "1"},
        "create_scheduled_payment": {"iban": "NL00", "amount": "1.00", "description": "x", "counterparty_name": "X", "start_date": "2026-05-01T09:00:00", "recurrence": "ONCE"},
        "cancel_scheduled_payment": {"schedule_id": 1},
        "request_money": {"iban": "NL00", "amount": "5.00", "description": "x", "counterparty_name": "X"},
        "revoke_request_inquiry": {"request_id": 11},
        "accept_request": {"request_response_id": 1, "amount": "5.00"},
        "reject_request": {"request_response_id": 1},
        "find_contact": {"query": "finn"},
        "update_card": {"card_id": 7, "status": "BLOCKED"},
        "create_bunqme_tab": {"amount": "10.00", "description": "x"},
        "get_bunqme_tab": {"tab_id": 1},
        "cancel_bunqme_tab": {"tab_id": 1},
        "set_webhooks": {"webhook_url": "https://example.test/hook", "categories": ["PAYMENT"]},
        "create_account": {"description": "Holiday"},
        "update_account": {"account_id": 42, "description": "Main"},
    }

    store = SessionStore()
    sid = store.create(bunq_user_id=1, primary_account_id=42)
    client = FakeBunqClient()

    for name in sorted(schema_names):
        if name in {"confirm_draft_payment"}:
            # needs a matching pending draft in session state
            store.set_pending_draft(sid, {"draft_id": "1", "amount": "10.00", "counterparty": "X"})
            client.draft_calls.append((42, "NL", "10.00", "x"))
        args = sample_args.get(name, {})
        dispatch(client, store, sid, name, args)
        if name == "confirm_draft_payment":
            store.clear_pending_draft(sid)


def test_dispatch_unknown_tool_raises(session):
    store, sid = session
    with pytest.raises(KeyError):
        dispatch(FakeBunqClient(), store, sid, "nonexistent_tool", {})


def test_read_only_tools_return_data(session):
    store, sid = session
    client = FakeBunqClient()
    assert dispatch(client, store, sid, "list_accounts", {}) == client._accounts
    assert dispatch(client, store, sid, "list_savings_accounts", {})[0]["description"] == "Rainy day"
    assert dispatch(client, store, sid, "list_cards", {})[0]["id"] == 7
    assert dispatch(client, store, sid, "list_scheduled_payments", {})[0]["id"] == 1
    assert dispatch(client, store, sid, "list_request_inquiries", {})[0]["counterparty"] == "Finn Bunq"
    assert dispatch(client, store, sid, "get_events", {"count": 5})[0]["action"] == "CREATED"
    payments = dispatch(client, store, sid, "list_recent_payments", {"limit": 3})
    assert len(payments) == 3
