from decimal import Decimal
from backend.bunq_client import Contact, PaymentSummary, DraftResult, ConfirmResult

class FakeBunqClient:
    def __init__(self) -> None:
        self.draft_calls: list[tuple] = []
        self.confirmed: list[str] = []
        self._balance = Decimal("1247.00")
        self._contacts = [
            Contact(id="c1", name="Michelle Weng", iban="NL00BUNQ0000000001"),
            Contact(id="c2", name="Finn Bunq", iban="NL00BUNQ0000000002"),
            Contact(id="c3", name="Jan Bakker", iban="NL00BUNQ0000000003"),
        ]
        self._payments = [
            PaymentSummary(date="2026-04-22", counterparty="Albert Heijn", amount=Decimal("-22.30"), description="groceries"),
            PaymentSummary(date="2026-04-21", counterparty="Uber", amount=Decimal("-14.80"), description=""),
        ]

    def primary_account_id(self) -> int:
        return 42

    def balance(self, account_id: int | None = None) -> Decimal:
        return self._balance

    def recent_payments(self, account_id: int | None = None, limit: int = 5) -> list[PaymentSummary]:
        return self._payments[:limit]

    def list_contacts(self) -> list[Contact]:
        return list(self._contacts)

    def create_draft_payment(self, account_id: int, iban: str, amount: Decimal, description: str) -> DraftResult:
        self.draft_calls.append((account_id, iban, amount, description))
        return DraftResult(draft_id=f"draft-{len(self.draft_calls)}")

    def confirm_draft_payment(self, draft_id: str) -> ConfirmResult:
        self.confirmed.append(draft_id)
        self._balance -= Decimal("20.00")
        return ConfirmResult(status="OK", new_balance=self._balance)
