from decimal import Decimal
from backend.bunq_client import BunqClient
from backend.session.store import SessionStore


def create_bunqme_tab(
    client: BunqClient,
    store: SessionStore,
    sid: str,
    *,
    amount: str,
    description: str,
) -> dict:
    sess = store.get(sid)
    return client.create_bunqme_tab(sess["primary_account_id"], Decimal(amount), description)


def get_bunqme_tab(
    client: BunqClient,
    store: SessionStore,
    sid: str,
    *,
    tab_id: int,
) -> dict:
    sess = store.get(sid)
    return client.get_bunqme_tab(tab_id, sess["primary_account_id"])


def list_bunqme_tabs(client: BunqClient, store: SessionStore, sid: str) -> list:
    sess = store.get(sid)
    return client.list_bunqme_tabs(sess["primary_account_id"])


def cancel_bunqme_tab(
    client: BunqClient,
    store: SessionStore,
    sid: str,
    *,
    tab_id: int,
) -> dict:
    sess = store.get(sid)
    return client.cancel_bunqme_tab(tab_id, sess["primary_account_id"])
