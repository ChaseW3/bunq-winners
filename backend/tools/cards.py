from decimal import Decimal
from backend.bunq_client import BunqClient
from backend.session.store import SessionStore


def list_cards(client: BunqClient, _store: SessionStore, _sid: str) -> list:
    return client.list_cards()


def update_card(
    client: BunqClient,
    _store: SessionStore,
    _sid: str,
    *,
    card_id: int,
    status: str | None = None,
    spending_limit_eur: str | None = None,
) -> dict:
    limit = Decimal(spending_limit_eur) if spending_limit_eur else None
    return client.update_card(card_id, status, limit)


def list_card_transactions(
    client: BunqClient,
    store: SessionStore,
    sid: str,
    *,
    count: int = 25,
) -> list:
    sess = store.get(sid)
    return client.list_card_transactions(sess["primary_account_id"], limit=count)
