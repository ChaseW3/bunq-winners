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


class RealBunqClient:
    def __init__(self) -> None:
        self._primary_account_id: int | None = None

    def primary_account_id(self) -> int:
        if self._primary_account_id is None:
            from bunq.sdk.model.generated.endpoint import MonetaryAccountBankApiObject
            accounts = MonetaryAccountBankApiObject.list().value
            active = [a for a in accounts if a.status == "ACTIVE"]
            if not active:
                raise RuntimeError("No active monetary account")
            self._primary_account_id = active[0].id_
        return self._primary_account_id

    def balance(self, account_id: int | None = None) -> Decimal:
        from bunq.sdk.model.generated.endpoint import MonetaryAccountBankApiObject
        aid = account_id or self.primary_account_id()
        acc = MonetaryAccountBankApiObject.get(aid).value
        return Decimal(acc.balance.value)

    def recent_payments(self, account_id: int | None = None, limit: int = 5) -> list[PaymentSummary]:
        from bunq.sdk.model.generated.endpoint import PaymentApiObject
        aid = account_id or self.primary_account_id()
        page = PaymentApiObject.list(monetary_account_id=aid, params={"count": str(limit)}).value
        results = []
        for p in page:
            name = ""
            if p.counterparty_alias:
                name = getattr(p.counterparty_alias, "display_name", "") or ""
                if not name:
                    label = getattr(p.counterparty_alias, "label_monetary_account", None)
                    if label:
                        name = getattr(label, "iban", "") or ""
            results.append(PaymentSummary(
                date=p.created,
                counterparty=name,
                amount=Decimal(p.amount.value),
                description=p.description or "",
            ))
        return results

    def list_contacts(self) -> list[Contact]:
        return []

    def create_draft_payment(self, account_id: int, iban: str, amount: Decimal, description: str) -> DraftResult:
        from bunq.sdk.model.generated.endpoint import DraftPaymentApiObject
        from bunq.sdk.model.generated.object_ import AmountObject, PointerObject, DraftPaymentEntryObject
        entry = DraftPaymentEntryObject(
            amount=AmountObject(value=str(amount), currency="EUR"),
            counterparty_alias=PointerObject(type_="IBAN", value=iban),
            description=description or "bunq Voice",
        )
        draft_id = DraftPaymentApiObject.create(
            entries=[entry],
            number_of_required_accepts=1,
            monetary_account_id=account_id,
        ).value
        return DraftResult(draft_id=str(draft_id))

    def confirm_draft_payment(self, draft_id: str) -> ConfirmResult:
        from bunq.sdk.model.generated.endpoint import DraftPaymentApiObject
        DraftPaymentApiObject.update(
            draft_payment_id=int(draft_id),
            monetary_account_id=self.primary_account_id(),
            status="ACCEPTED",
        )
        return ConfirmResult(status="OK", new_balance=self.balance())
