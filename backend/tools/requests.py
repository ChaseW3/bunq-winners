from decimal import Decimal
from backend.bunq_client import BunqClient
from backend.session.store import SessionStore


def request_money(
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
    return client.request_money(
        sess["primary_account_id"], iban, Decimal(amount), description, counterparty_name
    )


def list_request_inquiries(client: BunqClient, store: SessionStore, sid: str) -> list:
    sess = store.get(sid)
    return client.list_request_inquiries(sess["primary_account_id"])


def revoke_request_inquiry(
    client: BunqClient,
    store: SessionStore,
    sid: str,
    *,
    request_id: int,
) -> dict:
    sess = store.get(sid)
    return client.revoke_request_inquiry(request_id, sess["primary_account_id"])


def list_request_responses(client: BunqClient, store: SessionStore, sid: str) -> list:
    sess = store.get(sid)
    return client.list_request_responses(sess["primary_account_id"])


def accept_request(
    client: BunqClient,
    store: SessionStore,
    sid: str,
    *,
    request_response_id: int,
    amount: str,
) -> dict:
    sess = store.get(sid)
    return client.accept_request(request_response_id, Decimal(amount), sess["primary_account_id"])


def reject_request(
    client: BunqClient,
    store: SessionStore,
    sid: str,
    *,
    request_response_id: int,
) -> dict:
    sess = store.get(sid)
    return client.reject_request(request_response_id, sess["primary_account_id"])
