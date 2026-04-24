from backend.bunq_client import BunqClient
from backend.session.store import SessionStore


def get_balance(client: BunqClient, store: SessionStore, sid: str) -> dict:
    sess = store.get(sid)
    bal = client.balance(sess["primary_account_id"])
    return {"account": "primary", "balance": f"{bal:.2f}", "currency": "EUR"}


def list_accounts(client: BunqClient, _store: SessionStore, _sid: str) -> list:
    return client.list_accounts()


def get_account(client: BunqClient, _store: SessionStore, _sid: str, *, account_id: int) -> dict:
    return client.get_account(account_id)


def list_savings_accounts(client: BunqClient, _store: SessionStore, _sid: str) -> list:
    return client.list_savings_accounts()


def list_joint_accounts(client: BunqClient, _store: SessionStore, _sid: str) -> list:
    return client.list_joint_accounts()


def create_account(client: BunqClient, _store: SessionStore, _sid: str, *, description: str) -> dict:
    return client.create_account(description)


def update_account(
    client: BunqClient,
    _store: SessionStore,
    _sid: str,
    *,
    account_id: int,
    description: str | None = None,
    close: bool = False,
) -> dict:
    return client.update_account(account_id, description, close)
