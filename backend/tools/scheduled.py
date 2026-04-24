from decimal import Decimal
from backend.bunq_client import BunqClient
from backend.session.store import SessionStore


def create_scheduled_payment(
    client: BunqClient,
    store: SessionStore,
    sid: str,
    *,
    iban: str,
    amount: str,
    description: str,
    counterparty_name: str,
    start_date: str,
    recurrence: str,
) -> dict:
    sess = store.get(sid)
    return client.create_scheduled_payment(
        sess["primary_account_id"], iban, Decimal(amount),
        description, counterparty_name, start_date, recurrence,
    )


def list_scheduled_payments(client: BunqClient, store: SessionStore, sid: str) -> list:
    sess = store.get(sid)
    return client.list_scheduled_payments(sess["primary_account_id"])


def cancel_scheduled_payment(
    client: BunqClient,
    store: SessionStore,
    sid: str,
    *,
    schedule_id: int,
) -> dict:
    sess = store.get(sid)
    return client.cancel_scheduled_payment(schedule_id, sess["primary_account_id"])
