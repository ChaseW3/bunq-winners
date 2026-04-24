from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

@dataclass(frozen=True)
class Contact:
    id: str
    name: str
    iban: str

@dataclass(frozen=True)
class PaymentSummary:
    date: str
    counterparty: str
    amount: Decimal
    description: str

@dataclass(frozen=True)
class DraftResult:
    draft_id: str

@dataclass(frozen=True)
class ConfirmResult:
    status: str
    new_balance: Decimal

class BunqClient(Protocol):
    def primary_account_id(self) -> int: ...
    def balance(self, account_id: int | None = None) -> Decimal: ...
    def recent_payments(self, account_id: int | None = None, limit: int = 5) -> list[PaymentSummary]: ...
    def list_contacts(self) -> list[Contact]: ...
    def create_draft_payment(self, account_id: int, iban: str, amount: Decimal, description: str) -> DraftResult: ...
    def confirm_draft_payment(self, draft_id: str) -> ConfirmResult: ...
