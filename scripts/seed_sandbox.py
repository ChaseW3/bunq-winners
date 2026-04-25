"""
Seed the bunq sandbox primary account with a batch of test payments so the
voice agent has real transaction history to reason over.

Mechanics (sandbox-specific):
  1. Request money from ``sugardaddy@bunq.com`` — bunq's sandbox sugar-daddy
     auto-accepts and credits your balance.
  2. Create or reuse a sub-account ("Seed Sink") on this user. Sandbox rejects
     payments to IBANs that don't resolve to a real sandbox account, so we use
     a sub-account of our own as the sink.
  3. Self-transfer from primary → sink, one payment per fixture row. The
     merchant name goes in both the counterparty pointer ``name`` and the
     payment ``description`` so the LLM sees it in the transaction history.

Usage:
    uv run python scripts/seed_sandbox.py                 # topup + full fixture
    uv run python scripts/seed_sandbox.py --count 10      # only first 10 payments
    uv run python scripts/seed_sandbox.py --no-topup      # skip the sugar-daddy topup
    uv run python scripts/seed_sandbox.py --topup-amount 2000

Requires BUNQ_API_KEY in env. BUNQ_ENVIRONMENT must be SANDBOX.
"""
import argparse
import os
import sys
import time
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from backend.bunq_client.bootstrap import ensure_context
from backend.bunq_client.client import RealBunqClient

SUGAR_DADDY_EMAIL = "sugardaddy@bunq.com"
SINK_DESCRIPTION = "Seed Sink"

# (counterparty_name, amount_eur, description)
FIXTURE: list[tuple[str, str, str]] = [
    ("Albert Heijn",   "18.75", "groceries"),
    ("Albert Heijn",   "22.30", "groceries"),
    ("Albert Heijn",   "24.60", "groceries"),
    ("Albert Heijn",   "31.40", "groceries"),
    ("Albert Heijn",   "19.30", "groceries"),
    ("Jumbo",          "15.20", "groceries"),
    ("Uber",           "14.20", "taxi"),
    ("Uber",           "40.00", "taxi"),
    ("Uber Eats",      "22.80", "takeaway"),
    ("Thuisbezorgd",   "28.50", "takeaway"),
    ("Starbucks",       "4.80", "coffee"),
    ("Starbucks",       "4.80", "coffee"),
    ("KPN",            "47.82", "internet bill"),
    ("Netflix",        "11.99", "subscription"),
    ("Spotify",        "10.99", "subscription"),
    ("Apple",           "0.99", "iCloud"),
    ("Bol.com",        "67.00", "electronics"),
    ("Hema",            "9.95", "stationery"),
    ("NS",             "12.40", "train"),
    ("Shell",          "52.10", "fuel"),
    ("Gym Amsterdam",  "39.00", "gym monthly"),
    ("Sophie van Dijk",  "25.00", "dinner split"),
]


def _iban_of(acc) -> str | None:
    for al in (acc.alias or []):
        t = getattr(al, "type_", None) or getattr(al, "type", None)
        if t == "IBAN":
            return al.value
    return None


def topup_from_sugar_daddy(amount: Decimal) -> int:
    from bunq.sdk.model.generated.endpoint import RequestInquiryApiObject
    from bunq.sdk.model.generated.object_ import AmountObject, PointerObject
    req_id = RequestInquiryApiObject.create(
        amount_inquired=AmountObject(value=str(amount), currency="EUR"),
        counterparty_alias=PointerObject(type_="EMAIL", value=SUGAR_DADDY_EMAIL, name="Sugar Daddy"),
        description="seed topup",
        allow_bunqme=False,
    ).value
    return req_id


def find_or_create_sink() -> tuple[int, str]:
    """Return (account_id, iban) for the sink sub-account, creating it if needed."""
    from bunq.sdk.model.generated.endpoint import MonetaryAccountBankApiObject
    accounts = MonetaryAccountBankApiObject.list().value
    for a in accounts:
        if a.description == SINK_DESCRIPTION and a.status == "ACTIVE":
            iban = _iban_of(a)
            if iban:
                return a.id_, iban
    new_id = MonetaryAccountBankApiObject.create(currency="EUR", description=SINK_DESCRIPTION).value
    sink = MonetaryAccountBankApiObject.get(new_id).value
    iban = _iban_of(sink)
    if not iban:
        raise RuntimeError("created sink but it has no IBAN alias")
    return new_id, iban


def send_to_sink(sink_iban: str, name: str, amount: Decimal, description: str) -> int:
    from bunq.sdk.model.generated.endpoint import PaymentApiObject
    from bunq.sdk.model.generated.object_ import AmountObject, PointerObject
    # Sandbox overrides the counterparty name with the owner's display name when
    # the IBAN is self-owned, so the merchant is preserved in the description.
    merged_description = f"{name} — {description}"
    return PaymentApiObject.create(
        amount=AmountObject(value=str(amount), currency="EUR"),
        counterparty_alias=PointerObject(type_="IBAN", value=sink_iban, name=name),
        description=merged_description,
    ).value


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-topup", action="store_true", help="skip the sugar-daddy topup step")
    ap.add_argument("--topup-amount", default="3000.00", help="how much to top up (default 3000.00)")
    ap.add_argument("--count", type=int, default=len(FIXTURE), help="how many fixture payments to send")
    ap.add_argument("--delay", type=float, default=0.2, help="seconds between requests")
    args = ap.parse_args()

    env = os.environ.get("BUNQ_ENVIRONMENT", "SANDBOX")
    if env.upper() != "SANDBOX":
        sys.exit(f"refusing to seed a non-sandbox environment (BUNQ_ENVIRONMENT={env})")

    ensure_context(os.environ["BUNQ_API_KEY"], env)
    client = RealBunqClient()
    primary_id = client.primary_account_id()
    print(f"primary account: {primary_id}   starting balance: {client.balance()} EUR")

    if not args.no_topup:
        req_id = topup_from_sugar_daddy(Decimal(args.topup_amount))
        print(f"  → topup request {req_id} for {args.topup_amount} EUR (sugar-daddy auto-accepts)")
        time.sleep(1.5)
        print(f"  → balance after topup: {client.balance()} EUR")

    sink_id, sink_iban = find_or_create_sink()
    print(f"sink account: {sink_id}   iban: {sink_iban}")

    to_send = FIXTURE[: args.count]
    print(f"sending {len(to_send)} payments to sink…")
    sent = 0
    for i, (name, amount, desc) in enumerate(to_send, 1):
        try:
            pid = send_to_sink(sink_iban, name, Decimal(amount), desc)
            print(f"  [{i:2d}/{len(to_send)}] -{amount:>6} EUR → {name:<15} ({desc})  id={pid}")
            sent += 1
        except Exception as e:
            print(f"  [{i:2d}/{len(to_send)}] FAILED → {name}: {type(e).__name__}: {str(e)[:140]}")
        time.sleep(args.delay)

    print(f"done. sent {sent}/{len(to_send)}. final balance: {client.balance()} EUR")


if __name__ == "__main__":
    main()
