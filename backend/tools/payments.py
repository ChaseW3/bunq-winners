from decimal import Decimal
from backend.bunq_client import BunqClient
from backend.session.store import SessionStore

def list_recent_payments(client: BunqClient, store: SessionStore, sid: str, limit: int = 5) -> list[dict]:
    sess = store.get(sid)
    ps = client.recent_payments(sess["primary_account_id"], limit=limit)
    return [
        {"date": p.date, "counterparty": p.counterparty, "amount": f"{p.amount:.2f}", "description": p.description}
        for p in ps
    ]

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

def confirm_draft_payment(client: BunqClient, store: SessionStore, sid: str, *, draft_id: str) -> dict:
    sess = store.get(sid)
    pending = sess["pending_draft"]
    if not pending or pending["draft_id"] != draft_id:
        raise ValueError(f"No pending draft matches {draft_id}")
    result = client.confirm_draft_payment(draft_id)
    store.clear_pending_draft(sid)
    return {"status": result.status, "new_balance": f"{result.new_balance:.2f}"}

def cancel_pending(client: BunqClient, store: SessionStore, sid: str) -> dict:
    store.clear_pending_draft(sid)
    return {"status": "cancelled"}
