from backend.bunq_client import BunqClient
from backend.session.store import SessionStore


def list_webhooks(client: BunqClient, _store: SessionStore, _sid: str) -> list:
    return client.list_webhooks()


def set_webhooks(
    client: BunqClient,
    _store: SessionStore,
    _sid: str,
    *,
    webhook_url: str,
    categories: list[str],
) -> dict:
    return client.set_webhooks(webhook_url, categories)


def clear_webhooks(client: BunqClient, _store: SessionStore, _sid: str) -> dict:
    return client.clear_webhooks()
