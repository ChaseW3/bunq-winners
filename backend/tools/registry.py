from typing import Any, Callable
from backend.bunq_client import BunqClient
from backend.session.store import SessionStore
from backend.tools.balance import get_balance
from backend.tools.payments import (
    list_recent_payments, create_draft_payment,
    confirm_draft_payment, cancel_pending,
)
from backend.tools.contacts import find_contact

SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "get_balance",
        "description": "Return the balance of the user's primary account in EUR.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_recent_payments",
        "description": "List the most recent payments on the primary account.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 20}},
            "required": [],
        },
    },
    {
        "name": "find_contact",
        "description": "Fuzzy-match a person in the user's contacts by name. Returns 0, 1, or many matches.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "create_draft_payment",
        "description": "Create a draft (unconfirmed) payment. The user must confirm before it is sent.",
        "input_schema": {
            "type": "object",
            "properties": {
                "iban": {"type": "string"},
                "amount": {"type": "string", "description": "Amount in EUR as a decimal string, e.g. '20.00'"},
                "description": {"type": "string"},
                "counterparty_name": {"type": "string"},
            },
            "required": ["iban", "amount", "description", "counterparty_name"],
        },
    },
    {
        "name": "confirm_draft_payment",
        "description": "Confirm a previously created draft payment. Only call after the user explicitly agrees.",
        "input_schema": {
            "type": "object",
            "properties": {"draft_id": {"type": "string"}},
            "required": ["draft_id"],
        },
    },
    {
        "name": "cancel_pending",
        "description": "Cancel the currently pending draft payment. Call when the user declines or changes their mind.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

def tool_schemas() -> list[dict[str, Any]]:
    return SCHEMAS

def dispatch(client: BunqClient, store: SessionStore, sid: str, name: str, args: dict[str, Any]) -> Any:
    fns: dict[str, Callable[..., Any]] = {
        "get_balance": lambda: get_balance(client, store, sid),
        "list_recent_payments": lambda: list_recent_payments(client, store, sid, limit=args.get("limit", 5)),
        "find_contact": lambda: find_contact(client, args["query"]),
        "create_draft_payment": lambda: create_draft_payment(client, store, sid, **args),
        "confirm_draft_payment": lambda: confirm_draft_payment(client, store, sid, draft_id=args["draft_id"]),
        "cancel_pending": lambda: cancel_pending(client, store, sid),
    }
    if name not in fns:
        raise KeyError(name)
    return fns[name]()
