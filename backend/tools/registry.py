from typing import Any, Callable
from backend.bunq_client import BunqClient
from backend.session.store import SessionStore

from backend.tools.accounts import (
    get_balance, list_accounts, get_account,
    list_savings_accounts, list_joint_accounts,
    create_account, update_account,
)
from backend.tools.payments import (
    list_recent_payments, get_payment, send_payment,
    create_draft_payment, list_draft_payments,
    confirm_draft_payment, cancel_pending, cancel_draft_payment,
)
from backend.tools.scheduled import (
    create_scheduled_payment, list_scheduled_payments, cancel_scheduled_payment,
)
from backend.tools.requests import (
    request_money, list_request_inquiries, revoke_request_inquiry,
    list_request_responses, accept_request, reject_request,
)
from backend.tools.cards import list_cards, update_card, list_card_transactions
from backend.tools.contacts import find_contact
from backend.tools.bunqme import (
    create_bunqme_tab, get_bunqme_tab, list_bunqme_tabs, cancel_bunqme_tab,
)
from backend.tools.notifications import list_webhooks, set_webhooks, clear_webhooks
from backend.tools.events import get_events, get_user_profile

# =============================================================================
# Tool schemas  (what Claude sees — drives tool selection)
# =============================================================================

SCHEMAS: list[dict[str, Any]] = [

    # ── user ─────────────────────────────────────────────────────────────
    {
        "name": "get_user_profile",
        "description": "Get the user's profile: name, email, phone, and account status.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },

    # ── accounts ─────────────────────────────────────────────────────────
    {
        "name": "get_balance",
        "description": "Return the balance of the user's primary account in EUR.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_accounts",
        "description": "List all monetary accounts with their balances and IBANs.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_account",
        "description": "Get full details of a specific account by ID.",
        "input_schema": {
            "type": "object",
            "properties": {"account_id": {"type": "integer"}},
            "required": ["account_id"],
        },
    },
    {
        "name": "list_savings_accounts",
        "description": "List savings and auto-save accounts only.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_joint_accounts",
        "description": "List joint accounts shared with another user.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "create_account",
        "description": "Create a new checking account.",
        "input_schema": {
            "type": "object",
            "properties": {"description": {"type": "string", "description": "Account name"}},
            "required": ["description"],
        },
    },
    {
        "name": "update_account",
        "description": "Rename an account or close it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "integer"},
                "description": {"type": "string"},
                "close": {"type": "boolean", "description": "Set true to close the account"},
            },
            "required": ["account_id"],
        },
    },

    # ── payments ─────────────────────────────────────────────────────────
    {
        "name": "list_recent_payments",
        "description": "List the most recent payments on the primary account.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 200}},
            "required": [],
        },
    },
    {
        "name": "get_payment",
        "description": "Get full details of a single payment by its ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "payment_id": {"type": "integer"},
                "account_id": {"type": "integer"},
            },
            "required": ["payment_id"],
        },
    },
    {
        "name": "send_payment",
        "description": (
            "Send an immediate payment. WARNING: money moves instantly. "
            "Prefer create_draft_payment + confirm_draft_payment for safety."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "iban": {"type": "string"},
                "amount": {"type": "string", "description": "EUR decimal e.g. '10.00'"},
                "description": {"type": "string"},
                "counterparty_name": {"type": "string"},
            },
            "required": ["iban", "amount", "description", "counterparty_name"],
        },
    },

    # ── draft payments ────────────────────────────────────────────────────
    {
        "name": "create_draft_payment",
        "description": (
            "Create a draft payment. Money does NOT move yet — the user must confirm. "
            "Always use this first when the user wants to send money. "
            "Read back the details, then call confirm_draft_payment only after explicit yes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "iban": {"type": "string"},
                "amount": {"type": "string", "description": "EUR decimal e.g. '25.00'"},
                "description": {"type": "string"},
                "counterparty_name": {"type": "string"},
            },
            "required": ["iban", "amount", "description", "counterparty_name"],
        },
    },
    {
        "name": "list_draft_payments",
        "description": "List all pending draft payments waiting to be confirmed or cancelled.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "confirm_draft_payment",
        "description": "Confirm a draft payment — this SENDS the money. Only call after explicit user confirmation.",
        "input_schema": {
            "type": "object",
            "properties": {"draft_id": {"type": "string"}},
            "required": ["draft_id"],
        },
    },
    {
        "name": "cancel_pending",
        "description": "Cancel the currently pending draft (user declined or changed mind).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "cancel_draft_payment",
        "description": "Cancel a specific draft payment by draft_id and remove it via the API.",
        "input_schema": {
            "type": "object",
            "properties": {"draft_id": {"type": "string"}},
            "required": ["draft_id"],
        },
    },

    # ── scheduled payments ────────────────────────────────────────────────
    {
        "name": "create_scheduled_payment",
        "description": "Set up a recurring or one-time future payment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "iban": {"type": "string"},
                "amount": {"type": "string"},
                "description": {"type": "string"},
                "counterparty_name": {"type": "string"},
                "start_date": {"type": "string", "description": "ISO 8601 datetime e.g. '2026-05-01T09:00:00'"},
                "recurrence": {
                    "type": "string",
                    "enum": ["ONCE", "DAILY", "WEEKLY", "MONTHLY", "YEARLY"],
                },
            },
            "required": ["iban", "amount", "description", "counterparty_name", "start_date", "recurrence"],
        },
    },
    {
        "name": "list_scheduled_payments",
        "description": "List all active scheduled or recurring payments.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "cancel_scheduled_payment",
        "description": "Cancel a scheduled or recurring payment.",
        "input_schema": {
            "type": "object",
            "properties": {"schedule_id": {"type": "integer"}},
            "required": ["schedule_id"],
        },
    },

    # ── request inquiries ─────────────────────────────────────────────────
    {
        "name": "request_money",
        "description": "Ask someone to pay you. They get a notification and can pay via bunq or a link.",
        "input_schema": {
            "type": "object",
            "properties": {
                "iban": {"type": "string"},
                "amount": {"type": "string"},
                "description": {"type": "string"},
                "counterparty_name": {"type": "string"},
            },
            "required": ["iban", "amount", "description", "counterparty_name"],
        },
    },
    {
        "name": "list_request_inquiries",
        "description": "List payment requests you've sent to others (outgoing).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "revoke_request_inquiry",
        "description": "Cancel an outgoing payment request before the recipient responds.",
        "input_schema": {
            "type": "object",
            "properties": {"request_id": {"type": "integer"}},
            "required": ["request_id"],
        },
    },

    # ── request responses ─────────────────────────────────────────────────
    {
        "name": "list_request_responses",
        "description": "List incoming payment requests others have sent to you.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "accept_request",
        "description": "Accept and pay an incoming payment request.",
        "input_schema": {
            "type": "object",
            "properties": {
                "request_response_id": {"type": "integer"},
                "amount": {"type": "string", "description": "Amount to pay in EUR"},
            },
            "required": ["request_response_id", "amount"],
        },
    },
    {
        "name": "reject_request",
        "description": "Decline an incoming payment request.",
        "input_schema": {
            "type": "object",
            "properties": {"request_response_id": {"type": "integer"}},
            "required": ["request_response_id"],
        },
    },

    # ── contacts ──────────────────────────────────────────────────────────
    {
        "name": "find_contact",
        "description": "Fuzzy-match a person in the user's contacts by name. Returns 0, 1, or many matches.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },

    # ── cards ─────────────────────────────────────────────────────────────
    {
        "name": "list_cards",
        "description": "List all cards (debit, credit) with their status and spending limits.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "update_card",
        "description": "Block, unblock, or update the spending limit of a card. status: 'BLOCKED' or 'ACTIVE'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "card_id": {"type": "integer"},
                "status": {"type": "string", "enum": ["ACTIVE", "BLOCKED"]},
                "spending_limit_eur": {"type": "string", "description": "New limit e.g. '500.00'"},
            },
            "required": ["card_id"],
        },
    },
    {
        "name": "list_card_transactions",
        "description": "List card transactions with merchant name and city (more detail than list_recent_payments).",
        "input_schema": {
            "type": "object",
            "properties": {"count": {"type": "integer", "minimum": 1, "maximum": 200}},
            "required": [],
        },
    },

    # ── bunq.me ───────────────────────────────────────────────────────────
    {
        "name": "create_bunqme_tab",
        "description": "Create a shareable payment link (bunq.me). Anyone can pay — no bunq account needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["amount", "description"],
        },
    },
    {
        "name": "get_bunqme_tab",
        "description": "Check if a bunq.me payment link has been paid.",
        "input_schema": {
            "type": "object",
            "properties": {"tab_id": {"type": "integer"}},
            "required": ["tab_id"],
        },
    },
    {
        "name": "list_bunqme_tabs",
        "description": "List all bunq.me payment links (open and closed).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "cancel_bunqme_tab",
        "description": "Cancel an open bunq.me payment link.",
        "input_schema": {
            "type": "object",
            "properties": {"tab_id": {"type": "integer"}},
            "required": ["tab_id"],
        },
    },

    # ── notifications ─────────────────────────────────────────────────────
    {
        "name": "list_webhooks",
        "description": "List currently registered webhook URLs.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "set_webhooks",
        "description": (
            "Register a webhook URL for real-time event notifications. "
            "Categories: PAYMENT, MUTATION, CARD_TRANSACTION_SUCCESSFUL, CARD_TRANSACTION_FAILED, "
            "REQUEST, DRAFT_PAYMENT, SCHEDULE_RESULT, BUNQME_TAB."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "webhook_url": {"type": "string", "description": "Public HTTPS URL"},
                "categories": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["webhook_url", "categories"],
        },
    },
    {
        "name": "clear_webhooks",
        "description": "Remove all registered webhook URLs.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },

    # ── events ────────────────────────────────────────────────────────────
    {
        "name": "get_events",
        "description": "Get the unified account activity feed (all event types combined).",
        "input_schema": {
            "type": "object",
            "properties": {"count": {"type": "integer", "minimum": 1, "maximum": 200}},
            "required": [],
        },
    },
]

# =============================================================================
# Dispatch table  (routes tool name → implementation function)
# =============================================================================

def tool_schemas() -> list[dict[str, Any]]:
    return SCHEMAS


def dispatch(client: BunqClient, store: SessionStore, sid: str, name: str, args: dict[str, Any]) -> Any:
    fns: dict[str, Callable[..., Any]] = {
        # user
        "get_user_profile":          lambda: get_user_profile(client, store, sid),
        # accounts
        "get_balance":               lambda: get_balance(client, store, sid),
        "list_accounts":             lambda: list_accounts(client, store, sid),
        "get_account":               lambda: get_account(client, store, sid, **args),
        "list_savings_accounts":     lambda: list_savings_accounts(client, store, sid),
        "list_joint_accounts":       lambda: list_joint_accounts(client, store, sid),
        "create_account":            lambda: create_account(client, store, sid, **args),
        "update_account":            lambda: update_account(client, store, sid, **args),
        # payments
        "list_recent_payments":      lambda: list_recent_payments(client, store, sid, limit=args.get("limit", 5)),
        "get_payment":               lambda: get_payment(client, store, sid, **args),
        "send_payment":              lambda: send_payment(client, store, sid, **args),
        # drafts
        "create_draft_payment":      lambda: create_draft_payment(client, store, sid, **args),
        "list_draft_payments":       lambda: list_draft_payments(client, store, sid),
        "confirm_draft_payment":     lambda: confirm_draft_payment(client, store, sid, draft_id=args["draft_id"]),
        "cancel_pending":            lambda: cancel_pending(client, store, sid),
        "cancel_draft_payment":      lambda: cancel_draft_payment(client, store, sid, **args),
        # scheduled
        "create_scheduled_payment":  lambda: create_scheduled_payment(client, store, sid, **args),
        "list_scheduled_payments":   lambda: list_scheduled_payments(client, store, sid),
        "cancel_scheduled_payment":  lambda: cancel_scheduled_payment(client, store, sid, **args),
        # request inquiries
        "request_money":             lambda: request_money(client, store, sid, **args),
        "list_request_inquiries":    lambda: list_request_inquiries(client, store, sid),
        "revoke_request_inquiry":    lambda: revoke_request_inquiry(client, store, sid, **args),
        # request responses
        "list_request_responses":    lambda: list_request_responses(client, store, sid),
        "accept_request":            lambda: accept_request(client, store, sid, **args),
        "reject_request":            lambda: reject_request(client, store, sid, **args),
        # contacts
        "find_contact":              lambda: find_contact(client, args["query"]),
        # cards
        "list_cards":                lambda: list_cards(client, store, sid),
        "update_card":               lambda: update_card(client, store, sid, **args),
        "list_card_transactions":    lambda: list_card_transactions(client, store, sid, **args),
        # bunq.me
        "create_bunqme_tab":         lambda: create_bunqme_tab(client, store, sid, **args),
        "get_bunqme_tab":            lambda: get_bunqme_tab(client, store, sid, **args),
        "list_bunqme_tabs":          lambda: list_bunqme_tabs(client, store, sid),
        "cancel_bunqme_tab":         lambda: cancel_bunqme_tab(client, store, sid, **args),
        # notifications
        "list_webhooks":             lambda: list_webhooks(client, store, sid),
        "set_webhooks":              lambda: set_webhooks(client, store, sid, **args),
        "clear_webhooks":            lambda: clear_webhooks(client, store, sid),
        # events
        "get_events":                lambda: get_events(client, store, sid, **args),
    }
    if name not in fns:
        raise KeyError(f"Unknown tool: {name!r}")
    return fns[name]()
