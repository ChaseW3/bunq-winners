from decimal import Decimal
from backend.bunq_client import BunqClient
from backend.session.store import SessionStore


def list_recent_payments(client: BunqClient, store: SessionStore, sid: str, limit: int = 5) -> list[dict]:
    sess = store.get(sid)
    ps = client.recent_payments(sess["primary_account_id"], limit=limit)
    return [
        {"date": p.date, "counterparty": p.counterparty,
         "amount": f"{p.amount:.2f}", "description": p.description}
        for p in ps
    ]


def get_payment(
    client: BunqClient,
    store: SessionStore,
    sid: str,
    *,
    payment_id: int,
    account_id: int | None = None,
) -> dict:
    sess = store.get(sid)
    aid = account_id or sess["primary_account_id"]
    return client.get_payment(payment_id, aid)


def send_payment(
    client: BunqClient,
    store: SessionStore,
    sid: str,
    *,
    iban: str,
    amount: str,
    description: str,
    counterparty_name: str,
) -> dict:
    sess = store.get(sid)
    return client.send_payment(
        sess["primary_account_id"], iban, Decimal(amount), description, counterparty_name
    )


def create_draft_payment(
    client: BunqClient,
    store: SessionStore,
    sid: str,
    *,
    iban: str,
    amount: str,
    description: str,
    counterparty_name: str,
) -> dict:
    sess = store.get(sid)
    amt = Decimal(amount)
    draft = client.create_draft_payment(sess["primary_account_id"], iban, amt, description)
    store.set_pending_draft(sid, {
        "draft_id": draft.draft_id,
        "amount": f"{amt:.2f}",
        "counterparty": counterparty_name,
        "source": "voice",
    })
    return {"draft_id": draft.draft_id}


def list_draft_payments(client: BunqClient, store: SessionStore, sid: str) -> list:
    sess = store.get(sid)
    return client.list_draft_payments(sess["primary_account_id"])


def confirm_draft_payment(client: BunqClient, store: SessionStore, sid: str, *, draft_id: str) -> dict:
    sess = store.get(sid)
    pending = sess["pending_draft"]
    if not pending or pending["draft_id"] != draft_id:
        raise ValueError(f"No pending draft matches {draft_id}")
    result = client.confirm_draft_payment(draft_id)
    store.clear_pending_draft(sid)
    return {"status": result.status, "new_balance": f"{result.new_balance:.2f}"}


def cancel_pending(client: BunqClient, store: SessionStore, sid: str) -> dict:
    """Cancel the in-memory pending draft (clears UI state, no API call needed)."""
    store.clear_pending_draft(sid)
    return {"status": "cancelled"}


def cancel_draft_payment(
    client: BunqClient,
    store: SessionStore,
    sid: str,
    *,
    draft_id: str,
    account_id: int | None = None,
) -> dict:
    sess = store.get(sid)
    aid = account_id or sess["primary_account_id"]
    result = client.cancel_draft_payment(draft_id, aid)
    if sess.get("pending_draft") and sess["pending_draft"].get("draft_id") == draft_id:
        store.clear_pending_draft(sid)
    return result
