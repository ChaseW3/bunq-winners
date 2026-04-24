from backend.bunq_client import BunqClient
from backend.session.store import SessionStore


def get_events(client: BunqClient, _store: SessionStore, _sid: str, *, count: int = 25) -> list:
    return client.list_events(limit=count)


def get_user_profile(client: BunqClient, _store: SessionStore, _sid: str) -> dict:
    return client.get_user_profile()
