from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

# ---------------------------------------------------------------------------
# Shared data-transfer objects
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# BunqClient Protocol  (what tools and tests depend on)
# ---------------------------------------------------------------------------

class BunqClient(Protocol):
    # ── accounts ──────────────────────────────────────────────────────────
    def primary_account_id(self) -> int: ...
    def balance(self, account_id: int | None = None) -> Decimal: ...
    def list_accounts(self) -> list[dict[str, Any]]: ...
    def get_account(self, account_id: int) -> dict[str, Any]: ...
    def list_savings_accounts(self) -> list[dict[str, Any]]: ...
    def list_joint_accounts(self) -> list[dict[str, Any]]: ...
    def create_account(self, description: str) -> dict[str, Any]: ...
    def update_account(self, account_id: int, description: str | None, close: bool) -> dict[str, Any]: ...
    # ── payments ──────────────────────────────────────────────────────────
    def recent_payments(self, account_id: int | None = None, limit: int = 5) -> list[PaymentSummary]: ...
    def get_payment(self, payment_id: int, account_id: int | None = None) -> dict[str, Any]: ...
    def send_payment(self, account_id: int, iban: str, amount: Decimal, description: str, counterparty_name: str) -> dict[str, Any]: ...
    # ── draft payments ────────────────────────────────────────────────────
    def create_draft_payment(self, account_id: int, iban: str, amount: Decimal, description: str) -> DraftResult: ...
    def confirm_draft_payment(self, draft_id: str) -> ConfirmResult: ...
    def cancel_draft_payment(self, draft_id: str, account_id: int | None = None) -> dict[str, Any]: ...
    def list_draft_payments(self, account_id: int | None = None) -> list[dict[str, Any]]: ...
    # ── scheduled payments ────────────────────────────────────────────────
    def create_scheduled_payment(self, account_id: int, iban: str, amount: Decimal, description: str, counterparty_name: str, start_date: str, recurrence: str) -> dict[str, Any]: ...
    def list_scheduled_payments(self, account_id: int | None = None) -> list[dict[str, Any]]: ...
    def cancel_scheduled_payment(self, schedule_id: int, account_id: int | None = None) -> dict[str, Any]: ...
    # ── request inquiries ─────────────────────────────────────────────────
    def request_money(self, account_id: int, iban: str, amount: Decimal, description: str, counterparty_name: str) -> dict[str, Any]: ...
    def list_request_inquiries(self, account_id: int | None = None) -> list[dict[str, Any]]: ...
    def revoke_request_inquiry(self, request_id: int, account_id: int | None = None) -> dict[str, Any]: ...
    # ── request responses ─────────────────────────────────────────────────
    def list_request_responses(self, account_id: int | None = None) -> list[dict[str, Any]]: ...
    def accept_request(self, request_response_id: int, amount: Decimal, account_id: int | None = None) -> dict[str, Any]: ...
    def reject_request(self, request_response_id: int, account_id: int | None = None) -> dict[str, Any]: ...
    # ── cards ─────────────────────────────────────────────────────────────
    def list_contacts(self) -> list[Contact]: ...
    def list_cards(self) -> list[dict[str, Any]]: ...
    def update_card(self, card_id: int, status: str | None, card_limit: Decimal | None) -> dict[str, Any]: ...
    def list_card_transactions(self, account_id: int | None = None, limit: int = 25) -> list[dict[str, Any]]: ...
    # ── bunq.me ───────────────────────────────────────────────────────────
    def create_bunqme_tab(self, account_id: int, amount: Decimal, description: str) -> dict[str, Any]: ...
    def get_bunqme_tab(self, tab_id: int, account_id: int | None = None) -> dict[str, Any]: ...
    def list_bunqme_tabs(self, account_id: int | None = None) -> list[dict[str, Any]]: ...
    def cancel_bunqme_tab(self, tab_id: int, account_id: int | None = None) -> dict[str, Any]: ...
    # ── notifications ─────────────────────────────────────────────────────
    def list_webhooks(self) -> list[dict[str, Any]]: ...
    def set_webhooks(self, webhook_url: str, categories: list[str]) -> dict[str, Any]: ...
    def clear_webhooks(self) -> dict[str, Any]: ...
    # ── events ────────────────────────────────────────────────────────────
    def list_events(self, limit: int = 25) -> list[dict[str, Any]]: ...
    # ── user ──────────────────────────────────────────────────────────────
    def get_user_profile(self) -> dict[str, Any]: ...

# ---------------------------------------------------------------------------
# RealBunqClient — uses the bunq Python SDK (signing handled by BunqContext)
# ---------------------------------------------------------------------------

class RealBunqClient:
    def __init__(self) -> None:
        self._primary_account_id: int | None = None

    # ── internal helpers ──────────────────────────────────────────────────

    def _aid(self, account_id: int | None) -> int:
        return account_id if account_id is not None else self.primary_account_id()

    def primary_account_id(self) -> int:
        if self._primary_account_id is None:
            from bunq.sdk.model.generated.endpoint import MonetaryAccountBankApiObject
            accounts = MonetaryAccountBankApiObject.list().value
            active = [a for a in accounts if a.status == "ACTIVE"]
            if not active:
                raise RuntimeError("No active monetary account")
            self._primary_account_id = active[0].id_
        return self._primary_account_id

    @staticmethod
    def _fmt_alias(alias_list: list | None) -> dict:
        if not alias_list:
            return {}
        out: dict = {}
        for a in alias_list:
            t = getattr(a, "type_", None) or getattr(a, "type", None)
            v = getattr(a, "value", None)
            if t and v:
                out[t] = v
        return out

    # ── accounts ──────────────────────────────────────────────────────────

    def balance(self, account_id: int | None = None) -> Decimal:
        from bunq.sdk.model.generated.endpoint import MonetaryAccountBankApiObject
        acc = MonetaryAccountBankApiObject.get(self._aid(account_id)).value
        return Decimal(acc.balance.value)

    def list_accounts(self) -> list[dict[str, Any]]:
        from bunq.sdk.model.generated.endpoint import MonetaryAccountBankApiObject
        accounts = MonetaryAccountBankApiObject.list().value
        return [
            {
                "id": a.id_,
                "description": a.description,
                "balance": str(a.balance.value) if a.balance else None,
                "currency": a.currency,
                "status": a.status,
                "iban": self._fmt_alias(a.alias).get("IBAN"),
            }
            for a in accounts
        ]

    def get_account(self, account_id: int) -> dict[str, Any]:
        from bunq.sdk.model.generated.endpoint import MonetaryAccountBankApiObject
        a = MonetaryAccountBankApiObject.get(account_id).value
        return {
            "id": a.id_,
            "description": a.description,
            "balance": str(a.balance.value) if a.balance else None,
            "currency": a.currency,
            "status": a.status,
            "iban": self._fmt_alias(a.alias).get("IBAN"),
        }

    def list_savings_accounts(self) -> list[dict[str, Any]]:
        from bunq.sdk.model.generated.endpoint import MonetaryAccountSavingsApiObject
        accounts = MonetaryAccountSavingsApiObject.list().value
        return [
            {"id": a.id_, "description": a.description,
             "balance": str(a.balance.value) if a.balance else None,
             "status": a.status}
            for a in accounts
        ]

    def list_joint_accounts(self) -> list[dict[str, Any]]:
        from bunq.sdk.model.generated.endpoint import MonetaryAccountJointApiObject
        accounts = MonetaryAccountJointApiObject.list().value
        return [
            {"id": a.id_, "description": a.description,
             "balance": str(a.balance.value) if a.balance else None,
             "status": a.status}
            for a in accounts
        ]

    def create_account(self, description: str) -> dict[str, Any]:
        from bunq.sdk.model.generated.endpoint import MonetaryAccountBankApiObject
        new_id = MonetaryAccountBankApiObject.create(currency="EUR", description=description).value
        return {"created": True, "id": new_id, "description": description}

    def update_account(self, account_id: int, description: str | None, close: bool) -> dict[str, Any]:
        from bunq.sdk.model.generated.endpoint import MonetaryAccountBankApiObject
        kwargs: dict[str, Any] = {}
        if description:
            kwargs["description"] = description
        if close:
            kwargs["status"] = "CANCELLED"
        MonetaryAccountBankApiObject.update(account_id, **kwargs)
        return {"updated": True, "account_id": account_id}

    # ── payments ──────────────────────────────────────────────────────────

    def recent_payments(self, account_id: int | None = None, limit: int = 5) -> list[PaymentSummary]:
        from bunq.sdk.model.generated.endpoint import PaymentApiObject
        aid = self._aid(account_id)
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

    def get_payment(self, payment_id: int, account_id: int | None = None) -> dict[str, Any]:
        from bunq.sdk.model.generated.endpoint import PaymentApiObject
        p = PaymentApiObject.get(payment_id, monetary_account_id=self._aid(account_id)).value
        return {
            "id": p.id_,
            "amount": str(p.amount.value),
            "currency": p.amount.currency,
            "description": p.description,
            "type": p.type_,
            "counterparty": getattr(p.counterparty_alias, "display_name", None),
            "created": p.created,
        }

    def send_payment(self, account_id: int, iban: str, amount: Decimal, description: str, counterparty_name: str) -> dict[str, Any]:
        from bunq.sdk.model.generated.endpoint import PaymentApiObject
        from bunq.sdk.model.generated.object_ import AmountObject, PointerObject
        payment_id = PaymentApiObject.create(
            amount=AmountObject(value=str(amount), currency="EUR"),
            counterparty_alias=PointerObject(type_="IBAN", value=iban, name=counterparty_name),
            description=description,
            monetary_account_id=account_id,
        ).value
        return {"sent": True, "payment_id": payment_id}

    # ── draft payments ────────────────────────────────────────────────────

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

    def cancel_draft_payment(self, draft_id: str, account_id: int | None = None) -> dict[str, Any]:
        from bunq.sdk.model.generated.endpoint import DraftPaymentApiObject
        DraftPaymentApiObject.update(
            draft_payment_id=int(draft_id),
            monetary_account_id=self._aid(account_id),
            status="CANCELLED",
        )
        return {"cancelled": True, "draft_id": draft_id}

    def list_draft_payments(self, account_id: int | None = None) -> list[dict[str, Any]]:
        from bunq.sdk.model.generated.endpoint import DraftPaymentApiObject
        drafts = DraftPaymentApiObject.list(monetary_account_id=self._aid(account_id)).value
        return [
            {"id": d.id_, "status": d.status,
             "entries": [
                 {"amount": str(e.amount.value), "description": e.description}
                 for e in (d.entries or [])
             ]}
            for d in drafts
        ]

    # ── scheduled payments ────────────────────────────────────────────────

    def create_scheduled_payment(self, account_id: int, iban: str, amount: Decimal, description: str, counterparty_name: str, start_date: str, recurrence: str) -> dict[str, Any]:
        from bunq.sdk.model.generated.endpoint import SchedulePaymentApiObject
        from bunq.sdk.model.generated.object_ import AmountObject, PointerObject, SchedulePaymentEntryObject, ScheduleObject
        entry = SchedulePaymentEntryObject(
            amount=AmountObject(value=str(amount), currency="EUR"),
            counterparty_alias=PointerObject(type_="IBAN", value=iban, name=counterparty_name),
            description=description,
        )
        schedule = ScheduleObject(
            time_start=start_date,
            recurrence_unit=recurrence.upper(),
            recurrence_size=1,
        )
        schedule_id = SchedulePaymentApiObject.create(
            payment=entry,
            schedule=schedule,
            monetary_account_id=account_id,
        ).value
        return {"created": True, "schedule_id": schedule_id}

    def list_scheduled_payments(self, account_id: int | None = None) -> list[dict[str, Any]]:
        from bunq.sdk.model.generated.endpoint import SchedulePaymentApiObject
        items = SchedulePaymentApiObject.list(monetary_account_id=self._aid(account_id)).value
        return [
            {"id": s.id_, "status": s.object_.status if s.object_ else None,
             "amount": str(s.object_.payment.amount.value) if s.object_ and s.object_.payment else None}
            for s in items
        ]

    def cancel_scheduled_payment(self, schedule_id: int, account_id: int | None = None) -> dict[str, Any]:
        from bunq.sdk.model.generated.endpoint import SchedulePaymentApiObject
        SchedulePaymentApiObject.delete(schedule_id, monetary_account_id=self._aid(account_id))
        return {"cancelled": True, "schedule_id": schedule_id}

    # ── request inquiries ─────────────────────────────────────────────────

    def request_money(self, account_id: int, iban: str, amount: Decimal, description: str, counterparty_name: str) -> dict[str, Any]:
        from bunq.sdk.model.generated.endpoint import RequestInquiryApiObject
        from bunq.sdk.model.generated.object_ import AmountObject, PointerObject
        req_id = RequestInquiryApiObject.create(
            amount_inquired=AmountObject(value=str(amount), currency="EUR"),
            counterparty_alias=PointerObject(type_="IBAN", value=iban, name=counterparty_name),
            description=description,
            allow_bunqme=True,
            monetary_account_id=account_id,
        ).value
        return {"request_id": req_id, "amount": str(amount), "iban": iban}

    def list_request_inquiries(self, account_id: int | None = None) -> list[dict[str, Any]]:
        from bunq.sdk.model.generated.endpoint import RequestInquiryApiObject
        items = RequestInquiryApiObject.list(monetary_account_id=self._aid(account_id)).value
        return [
            {"id": r.id_, "status": r.status,
             "amount": str(r.amount_inquired.value) if r.amount_inquired else None,
             "description": r.description,
             "counterparty": getattr(r.counterparty_alias, "display_name", None)}
            for r in items
        ]

    def revoke_request_inquiry(self, request_id: int, account_id: int | None = None) -> dict[str, Any]:
        from bunq.sdk.model.generated.endpoint import RequestInquiryApiObject
        RequestInquiryApiObject.update(
            request_inquiry_id=request_id,
            monetary_account_id=self._aid(account_id),
            status="REVOKED",
        )
        return {"revoked": True, "request_id": request_id}

    # ── request responses ─────────────────────────────────────────────────

    def list_request_responses(self, account_id: int | None = None) -> list[dict[str, Any]]:
        from bunq.sdk.model.generated.endpoint import RequestResponseApiObject
        items = RequestResponseApiObject.list(monetary_account_id=self._aid(account_id)).value
        return [
            {"id": r.id_, "status": r.status,
             "amount": str(r.amount_inquired.value) if r.amount_inquired else None,
             "description": r.description,
             "from": getattr(r.counterparty_alias, "display_name", None)}
            for r in items
        ]

    def accept_request(self, request_response_id: int, amount: Decimal, account_id: int | None = None) -> dict[str, Any]:
        from bunq.sdk.model.generated.endpoint import RequestResponseApiObject
        from bunq.sdk.model.generated.object_ import AmountObject
        RequestResponseApiObject.update(
            request_response_id=request_response_id,
            monetary_account_id=self._aid(account_id),
            amount_responded=AmountObject(value=str(amount), currency="EUR"),
            status="ACCEPTED",
        )
        return {"accepted": True, "request_response_id": request_response_id}

    def reject_request(self, request_response_id: int, account_id: int | None = None) -> dict[str, Any]:
        from bunq.sdk.model.generated.endpoint import RequestResponseApiObject
        RequestResponseApiObject.update(
            request_response_id=request_response_id,
            monetary_account_id=self._aid(account_id),
            status="REJECTED",
        )
        return {"rejected": True, "request_response_id": request_response_id}

    # ── cards ─────────────────────────────────────────────────────────────

    def list_contacts(self) -> list[Contact]:
        return []

    def list_cards(self) -> list[dict[str, Any]]:
        from bunq.sdk.model.generated.endpoint import CardDebitApiObject
        cards = CardDebitApiObject.list().value
        return [
            {"id": c.id_, "type": "MASTERCARD", "status": c.status,
             "second_line": c.second_line,
             "card_limit": str(c.card_limit.value) if c.card_limit else None}
            for c in cards
        ]

    def update_card(self, card_id: int, status: str | None, card_limit: Decimal | None) -> dict[str, Any]:
        from bunq.sdk.model.generated.endpoint import CardDebitApiObject
        from bunq.sdk.model.generated.object_ import AmountObject
        kwargs: dict[str, Any] = {}
        if status:
            kwargs["status"] = status
        if card_limit is not None:
            kwargs["card_limit"] = AmountObject(value=str(card_limit), currency="EUR")
        CardDebitApiObject.update(card_id, **kwargs)
        return {"updated": True, "card_id": card_id}

    def list_card_transactions(self, account_id: int | None = None, limit: int = 25) -> list[dict[str, Any]]:
        from bunq.sdk.model.generated.endpoint import MasterCardActionApiObject
        items = MasterCardActionApiObject.list(
            monetary_account_id=self._aid(account_id),
            params={"count": str(limit)},
        ).value
        return [
            {"id": m.id_, "amount": str(m.amount_local.value) if m.amount_local else None,
             "merchant": getattr(m, "merchant_name", None),
             "city": getattr(m, "city", None),
             "status": getattr(m, "authorisation_status", None),
             "created": m.created}
            for m in items
        ]

    # ── bunq.me ───────────────────────────────────────────────────────────

    def create_bunqme_tab(self, account_id: int, amount: Decimal, description: str) -> dict[str, Any]:
        from bunq.sdk.model.generated.endpoint import BunqMeTabApiObject
        from bunq.sdk.model.generated.object_ import AmountObject, BunqMeTabEntryObject
        entry = BunqMeTabEntryObject(
            amount_inquired=AmountObject(value=str(amount), currency="EUR"),
            description=description,
        )
        tab_id = BunqMeTabApiObject.create(
            bunqme_tab_entry=entry,
            status="OPENED",
            monetary_account_id=account_id,
        ).value
        return {"tab_id": tab_id, "amount": str(amount), "description": description}

    def get_bunqme_tab(self, tab_id: int, account_id: int | None = None) -> dict[str, Any]:
        from bunq.sdk.model.generated.endpoint import BunqMeTabApiObject
        t = BunqMeTabApiObject.get(tab_id, monetary_account_id=self._aid(account_id)).value
        entry = getattr(t, "bunqme_tab_entry", None)
        return {
            "id": t.id_,
            "status": t.status,
            "amount": str(entry.amount_inquired.value) if entry and entry.amount_inquired else None,
            "description": getattr(entry, "description", None) if entry else None,
            "share_url": getattr(entry, "bunqme_url", None) if entry else None,
        }

    def list_bunqme_tabs(self, account_id: int | None = None) -> list[dict[str, Any]]:
        from bunq.sdk.model.generated.endpoint import BunqMeTabApiObject
        tabs = BunqMeTabApiObject.list(monetary_account_id=self._aid(account_id)).value
        return [
            {"id": t.id_, "status": t.status,
             "amount": str(t.bunqme_tab_entry.amount_inquired.value)
                       if t.bunqme_tab_entry and t.bunqme_tab_entry.amount_inquired else None}
            for t in tabs
        ]

    def cancel_bunqme_tab(self, tab_id: int, account_id: int | None = None) -> dict[str, Any]:
        from bunq.sdk.model.generated.endpoint import BunqMeTabApiObject
        BunqMeTabApiObject.update(tab_id, monetary_account_id=self._aid(account_id), status="CANCELLED")
        return {"cancelled": True, "tab_id": tab_id}

    # ── notifications ─────────────────────────────────────────────────────

    def list_webhooks(self) -> list[dict[str, Any]]:
        from bunq.sdk.model.generated.endpoint import NotificationFilterUrlUserApiObject
        items = NotificationFilterUrlUserApiObject.list().value
        return [
            {"category": getattr(f, "category", None),
             "url": getattr(f, "notification_target", None)}
            for f in (items or [])
        ]

    def set_webhooks(self, webhook_url: str, categories: list[str]) -> dict[str, Any]:
        from bunq.sdk.model.generated.endpoint import NotificationFilterUrlUserApiObject
        from bunq.sdk.model.generated.object_ import NotificationFilterObject
        filters = [
            NotificationFilterObject(category=c, notification_target=webhook_url)
            for c in categories
        ]
        NotificationFilterUrlUserApiObject.create(notification_filters=filters)
        return {"registered": True, "url": webhook_url, "categories": categories}

    def clear_webhooks(self) -> dict[str, Any]:
        from bunq.sdk.model.generated.endpoint import NotificationFilterUrlUserApiObject
        NotificationFilterUrlUserApiObject.create(notification_filters=[])
        return {"cleared": True}

    # ── events ────────────────────────────────────────────────────────────

    def list_events(self, limit: int = 25) -> list[dict[str, Any]]:
        from bunq.sdk.model.generated.endpoint import EventApiObject
        events = EventApiObject.list(params={"count": str(limit)}).value
        return [
            {"id": e.id_, "type": e.object_.type_ if e.object_ else None,
             "action": e.action, "created": e.created}
            for e in events
        ]

    # ── user ──────────────────────────────────────────────────────────────

    def get_user_profile(self) -> dict[str, Any]:
        from bunq.sdk.model.generated.endpoint import UserApiObject
        users = UserApiObject.list().value
        u = users[0] if users else None
        if not u:
            return {}
        person = getattr(u, "user_person", None) or getattr(u, "user_company", None)
        if not person:
            return {}
        aliases = self._fmt_alias(getattr(person, "alias", None))
        return {
            "id": person.id_,
            "name": getattr(person, "display_name", None),
            "email": aliases.get("EMAIL"),
            "phone": aliases.get("PHONE_NUMBER"),
            "status": getattr(person, "status", None),
        }
