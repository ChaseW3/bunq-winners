from backend.bunq_client import BunqClient
from backend.session.store import SessionStore

def get_balance(client: BunqClient, store: SessionStore, sid: str) -> dict:
    sess = store.get(sid)
    aid = sess["primary_account_id"]
    bal = client.balance(aid)
    return {"account": "primary", "balance": f"{bal:.2f}", "currency": "EUR"}
