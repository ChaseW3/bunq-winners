from decimal import Decimal
from typing import Any
from backend.bunq_client import Contact, PaymentSummary, DraftResult, ConfirmResult

class FakeBunqClient:
    def __init__(self) -> None:
        self.draft_calls: list[tuple] = []
        self.confirmed: list[str] = []
        self.cancelled_drafts: list[str] = []
        self.sent_payments: list[tuple] = []
        self.card_updates: list[tuple] = []
        self.webhook_calls: list[tuple] = []
        self._balance = Decimal("847.35")
        self._contacts = [
            Contact(id="c1", name="Michelle Weng", iban="NL42BUNQ0123456789"),
            Contact(id="c2", name="Nikki de Vries", iban="NL91BUNQ0987654321"),
            Contact(id="c3", name="Jan Bakker", iban="NL00BUNQ0000000003"),
            Contact(id="c4", name="Finn Bunq", iban="NL00BUNQ0000000002"),
        ]
        self._payments = [
            PaymentSummary(date="2026-04-25", counterparty="Albert Heijn",  amount=Decimal("-32.40"), description="groceries"),
            PaymentSummary(date="2026-04-25", counterparty="Nikki de Vries",amount=Decimal("15.00"),  description="lunch payback"),
            PaymentSummary(date="2026-04-25", counterparty="Starbucks",     amount=Decimal("-6.20"),  description="coffee"),
            PaymentSummary(date="2026-04-24", counterparty="Uber",          amount=Decimal("-14.20"), description=""),
            PaymentSummary(date="2026-04-24", counterparty="Spotify",       amount=Decimal("-10.99"), description="subscription"),
            PaymentSummary(date="2026-04-24", counterparty="Thuisbezorgd",  amount=Decimal("-28.50"), description="takeaway"),
            PaymentSummary(date="2026-04-23", counterparty="Albert Heijn",  amount=Decimal("-22.30"), description="groceries"),
            PaymentSummary(date="2026-04-23", counterparty="KPN",           amount=Decimal("-47.82"), description="internet bill"),
            PaymentSummary(date="2026-04-22", counterparty="Uber",          amount=Decimal("-40.00"), description=""),
            PaymentSummary(date="2026-04-22", counterparty="Albert Heijn",  amount=Decimal("-18.10"), description="groceries"),
            PaymentSummary(date="2026-04-21", counterparty="Netflix",       amount=Decimal("-11.99"), description="subscription"),
            PaymentSummary(date="2026-04-21", counterparty="Bol.com",       amount=Decimal("-67.00"), description="electronics"),
            PaymentSummary(date="2026-04-20", counterparty="Albert Heijn",  amount=Decimal("-24.60"), description="groceries"),
            PaymentSummary(date="2026-04-20", counterparty="NS",            amount=Decimal("-12.40"), description="train"),
            PaymentSummary(date="2026-04-19", counterparty="Dad",           amount=Decimal("500.00"), description="birthday gift"),
            PaymentSummary(date="2026-04-18", counterparty="Jumbo",         amount=Decimal("-15.20"), description="groceries"),
            PaymentSummary(date="2026-04-17", counterparty="Starbucks",     amount=Decimal("-4.80"),  description="coffee"),
            PaymentSummary(date="2026-04-17", counterparty="Michelle Weng", amount=Decimal("-25.00"), description="dinner split"),
            PaymentSummary(date="2026-04-16", counterparty="Gym Amsterdam", amount=Decimal("-39.00"), description="monthly"),
            PaymentSummary(date="2026-04-15", counterparty="Employer BV",   amount=Decimal("2450.00"), description="salary"),
            PaymentSummary(date="2026-04-15", counterparty="Shell",         amount=Decimal("-52.10"), description="fuel"),
            PaymentSummary(date="2026-04-14", counterparty="Uber Eats",     amount=Decimal("-22.80"), description=""),
            PaymentSummary(date="2026-04-13", counterparty="Apple",         amount=Decimal("-0.99"),  description="iCloud"),
            PaymentSummary(date="2026-04-12", counterparty="Albert Heijn",  amount=Decimal("-19.30"), description="groceries"),
            PaymentSummary(date="2026-04-10", counterparty="Nikki de Vries",amount=Decimal("-50.00"), description="concert tickets"),
        ]
        self._accounts = [
            {"id": 42, "description": "Main", "balance": "847.35", "currency": "EUR", "status": "ACTIVE", "iban": "NL42BUNQ0000000042"},
            {"id": 43, "description": "Holiday", "balance": "310.00", "currency": "EUR", "status": "ACTIVE", "iban": "NL42BUNQ0000000043"},
        ]
        self._savings = [
            {"id": 99, "description": "Rainy day", "balance": "3400.00", "status": "ACTIVE"},
        ]
        self._joint: list[dict] = []
        self._cards = [
            {"id": 7, "type": "MASTERCARD", "status": "ACTIVE", "second_line": "V. TESTER", "card_limit": "2500.00"},
        ]
        self._scheduled = [
            {"id": 1, "status": "ACTIVE", "amount": "-50.00"},
        ]
        self._request_inquiries = [
            {"id": 11, "status": "PENDING", "amount": "25.00", "description": "dinner last week", "counterparty": "Nikki de Vries"},
        ]
        self._request_responses: list[dict] = []
        self._drafts: list[dict] = []
        self._events = [
            {"id": 1001, "type": "Payment", "action": "CREATED", "created": "2026-04-22 10:00:00"},
        ]
        self._card_transactions = [
            {"id": 501, "amount": "-22.30", "merchant": "Albert Heijn", "city": "Amsterdam", "status": "AUTHORISED", "created": "2026-04-22 10:00:00"},
        ]
        self._tabs: list[dict] = []
        self._webhooks: list[dict] = []

    # accounts
    def primary_account_id(self) -> int: return 42
    def balance(self, account_id: int | None = None) -> Decimal: return self._balance
    def list_accounts(self) -> list[dict[str, Any]]: return list(self._accounts)
    def get_account(self, account_id: int) -> dict[str, Any]:
        return next((a for a in self._accounts if a["id"] == account_id), {})
    def list_savings_accounts(self) -> list[dict[str, Any]]: return list(self._savings)
    def list_joint_accounts(self) -> list[dict[str, Any]]: return list(self._joint)
    def create_account(self, description: str) -> dict[str, Any]:
        new = {"id": 100 + len(self._accounts), "description": description, "balance": "0.00", "currency": "EUR", "status": "ACTIVE", "iban": ""}
        self._accounts.append(new)
        return {"created": True, "id": new["id"], "description": description}
    def update_account(self, account_id: int, description: str | None, close: bool) -> dict[str, Any]:
        return {"updated": True, "account_id": account_id}

    # payments
    def recent_payments(self, account_id: int | None = None, limit: int = 5) -> list[PaymentSummary]:
        return self._payments[:limit]
    def get_payment(self, payment_id: int, account_id: int | None = None) -> dict[str, Any]:
        return {"id": payment_id, "amount": "-10.00", "currency": "EUR", "description": "", "type": "BUNQ", "counterparty": "", "created": ""}
    def send_payment(self, account_id: int, iban: str, amount: Decimal, description: str, counterparty_name: str) -> dict[str, Any]:
        self.sent_payments.append((account_id, iban, amount, description, counterparty_name))
        return {"sent": True, "payment_id": 9000 + len(self.sent_payments)}

    # drafts
    def create_draft_payment(self, account_id: int, iban: str, amount: Decimal, description: str) -> DraftResult:
        self.draft_calls.append((account_id, iban, amount, description))
        return DraftResult(draft_id=f"draft-{len(self.draft_calls)}")
    def confirm_draft_payment(self, draft_id: str) -> ConfirmResult:
        self.confirmed.append(draft_id)
        # Deduct the amount from the matching draft call
        idx = int(draft_id.split("-")[-1]) - 1
        if 0 <= idx < len(self.draft_calls):
            self._balance -= self.draft_calls[idx][2]
        return ConfirmResult(status="OK", new_balance=self._balance)
    def cancel_draft_payment(self, draft_id: str, account_id: int | None = None) -> dict[str, Any]:
        self.cancelled_drafts.append(draft_id)
        return {"cancelled": True, "draft_id": draft_id}
    def list_draft_payments(self, account_id: int | None = None) -> list[dict[str, Any]]: return list(self._drafts)

    # scheduled
    def create_scheduled_payment(self, account_id: int, iban: str, amount: Decimal, description: str, counterparty_name: str, start_date: str, recurrence: str) -> dict[str, Any]:
        return {"created": True, "schedule_id": 200}
    def list_scheduled_payments(self, account_id: int | None = None) -> list[dict[str, Any]]: return list(self._scheduled)
    def cancel_scheduled_payment(self, schedule_id: int, account_id: int | None = None) -> dict[str, Any]:
        return {"cancelled": True, "schedule_id": schedule_id}

    # requests
    def request_money(self, account_id: int, iban: str, amount: Decimal, description: str, counterparty_name: str) -> dict[str, Any]:
        return {"request_id": 321, "amount": str(amount), "iban": iban}
    def list_request_inquiries(self, account_id: int | None = None) -> list[dict[str, Any]]:
        return list(self._request_inquiries)
    def revoke_request_inquiry(self, request_id: int, account_id: int | None = None) -> dict[str, Any]:
        return {"revoked": True, "request_id": request_id}
    def list_request_responses(self, account_id: int | None = None) -> list[dict[str, Any]]:
        return list(self._request_responses)
    def accept_request(self, request_response_id: int, amount: Decimal, account_id: int | None = None) -> dict[str, Any]:
        return {"accepted": True, "request_response_id": request_response_id}
    def reject_request(self, request_response_id: int, account_id: int | None = None) -> dict[str, Any]:
        return {"rejected": True, "request_response_id": request_response_id}

    # contacts/cards
    def list_contacts(self) -> list[Contact]: return list(self._contacts)
    def list_cards(self) -> list[dict[str, Any]]: return list(self._cards)
    def update_card(self, card_id: int, status: str | None, card_limit: Decimal | None) -> dict[str, Any]:
        self.card_updates.append((card_id, status, card_limit))
        return {"updated": True, "card_id": card_id}
    def list_card_transactions(self, account_id: int | None = None, limit: int = 25) -> list[dict[str, Any]]:
        return list(self._card_transactions)[:limit]

    # bunq.me
    def create_bunqme_tab(self, account_id: int, amount: Decimal, description: str) -> dict[str, Any]:
        return {"tab_id": 777, "amount": str(amount), "description": description}
    def get_bunqme_tab(self, tab_id: int, account_id: int | None = None) -> dict[str, Any]:
        return {"id": tab_id, "status": "OPEN", "amount": "10.00", "description": "", "share_url": ""}
    def list_bunqme_tabs(self, account_id: int | None = None) -> list[dict[str, Any]]: return list(self._tabs)
    def cancel_bunqme_tab(self, tab_id: int, account_id: int | None = None) -> dict[str, Any]:
        return {"cancelled": True, "tab_id": tab_id}

    # notifications
    def list_webhooks(self) -> list[dict[str, Any]]: return list(self._webhooks)
    def set_webhooks(self, webhook_url: str, categories: list[str]) -> dict[str, Any]:
        self.webhook_calls.append((webhook_url, tuple(categories)))
        return {"registered": True, "url": webhook_url, "categories": categories}
    def clear_webhooks(self) -> dict[str, Any]: return {"cleared": True}

    # events / user
    def list_events(self, limit: int = 25) -> list[dict[str, Any]]: return list(self._events)[:limit]
    def get_user_profile(self) -> dict[str, Any]:
        return {"id": 1, "name": "Victor Tester", "email": "victor@example.com", "phone": "+31000000000", "status": "ACTIVE"}
