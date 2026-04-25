from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from statistics import mean, stdev
from typing import Any

from backend.bunq_client import BunqClient, PaymentSummary
from backend.session.store import SessionStore

FOCUS_OPTIONS = {
    "affordability", "spending_breakdown", "cashflow_forecast",
    "anomalies", "savings_health", "general",
}


def financial_context(
    client: BunqClient,
    store: SessionStore,
    sid: str,
    *,
    focus: str = "general",
    horizon_days: int = 30,
) -> dict[str, Any]:
    if focus not in FOCUS_OPTIONS:
        focus = "general"

    sess = store.get(sid)
    aid = sess["primary_account_id"]

    balance = client.balance(aid)
    payments = client.recent_payments(aid, limit=200)
    scheduled = client.list_scheduled_payments(aid)
    savings = client.list_savings_accounts()

    builders = {
        "affordability": _affordability,
        "spending_breakdown": _spending_breakdown,
        "cashflow_forecast": _cashflow_forecast,
        "anomalies": _anomalies,
        "savings_health": _savings_health,
        "general": _general,
    }
    return builders[focus](
        balance=balance,
        payments=payments,
        scheduled=scheduled,
        savings=savings,
        horizon_days=horizon_days,
    )


def _parse_amount(p: PaymentSummary) -> Decimal:
    return p.amount


def _spending_only(payments: list[PaymentSummary]) -> list[PaymentSummary]:
    return [p for p in payments if _parse_amount(p) < 0]


def _income_only(payments: list[PaymentSummary]) -> list[PaymentSummary]:
    return [p for p in payments if _parse_amount(p) > 0]


def _days_ago(payments: list[PaymentSummary], days: int) -> list[PaymentSummary]:
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    return [p for p in payments if p.date >= cutoff]


def _scheduled_total(scheduled: list[dict], horizon_days: int) -> Decimal:
    total = Decimal("0")
    for s in scheduled:
        amt = s.get("amount")
        if amt:
            a = Decimal(str(amt))
            if a < 0:
                total += abs(a)
    return total


def _detect_income_cycle(payments: list[PaymentSummary]) -> dict[str, Any]:
    incomes = sorted(_income_only(payments), key=lambda p: _parse_amount(p), reverse=True)
    if not incomes:
        return {"detected": False}
    largest = incomes[0]
    try:
        last_date = date.fromisoformat(largest.date[:10])
        if last_date.day <= 15:
            next_date = last_date.replace(month=last_date.month + 1 if last_date.month < 12 else 1)
        else:
            next_date = last_date.replace(month=last_date.month + 1 if last_date.month < 12 else 1)
        days_until = (next_date - date.today()).days
        if days_until < 0:
            days_until += 30
    except (ValueError, OverflowError):
        days_until = 30
    return {
        "detected": True,
        "source": largest.counterparty,
        "amount": f"{_parse_amount(largest):.2f}",
        "days_until_next": max(days_until, 0),
    }


def _affordability(
    balance: Decimal,
    payments: list[PaymentSummary],
    scheduled: list[dict],
    savings: list[dict],
    horizon_days: int,
) -> dict[str, Any]:
    spend_30d = _spending_only(_days_ago(payments, 30))
    spend_7d = _spending_only(_days_ago(payments, 7))
    total_30d = sum(abs(_parse_amount(p)) for p in spend_30d)
    total_7d = sum(abs(_parse_amount(p)) for p in spend_7d)
    avg_daily = total_30d / 30 if total_30d else Decimal("0")
    upcoming_bills = _scheduled_total(scheduled, horizon_days)
    income = _detect_income_cycle(payments)
    days_to_income = income.get("days_until_next", 30)
    buffer = balance - upcoming_bills - (avg_daily * days_to_income)

    return {
        "focus": "affordability",
        "balance_eur": f"{balance:.2f}",
        "savings_total_eur": f"{sum(Decimal(s.get('balance', '0')) for s in savings):.2f}",
        "upcoming_bills_eur": f"{upcoming_bills:.2f}",
        "spent_last_30d_eur": f"{total_30d:.2f}",
        "spent_last_7d_eur": f"{total_7d:.2f}",
        "avg_daily_spend_eur": f"{avg_daily:.2f}",
        "income_cycle": income,
        "discretionary_buffer_eur": f"{buffer:.2f}",
        "days_until_income": days_to_income,
    }


def _spending_breakdown(
    balance: Decimal,
    payments: list[PaymentSummary],
    scheduled: list[dict],
    savings: list[dict],
    horizon_days: int,
) -> dict[str, Any]:
    spend_30d = _spending_only(_days_ago(payments, 30))
    spend_7d = _spending_only(_days_ago(payments, 7))
    spend_prev_7d = _spending_only([
        p for p in payments
        if (date.today() - timedelta(days=14)).isoformat() <= p.date < (date.today() - timedelta(days=7)).isoformat()
    ])

    by_counterparty: dict[str, Decimal] = defaultdict(Decimal)
    by_category: dict[str, Decimal] = defaultdict(Decimal)
    for p in spend_30d:
        by_counterparty[p.counterparty] += abs(_parse_amount(p))
        cat = (p.description or "other").lower().strip()
        by_category[cat] += abs(_parse_amount(p))
    top_5 = sorted(by_counterparty.items(), key=lambda x: x[1], reverse=True)[:5]
    top_categories = sorted(by_category.items(), key=lambda x: x[1], reverse=True)[:5]

    total_30d = sum(abs(_parse_amount(p)) for p in spend_30d)
    total_7d = sum(abs(_parse_amount(p)) for p in spend_7d)
    total_prev_7d = sum(abs(_parse_amount(p)) for p in spend_prev_7d)

    return {
        "focus": "spending_breakdown",
        "balance_eur": f"{balance:.2f}",
        "total_30d_eur": f"{total_30d:.2f}",
        "total_7d_eur": f"{total_7d:.2f}",
        "total_prev_7d_eur": f"{total_prev_7d:.2f}",
        "week_over_week_delta_eur": f"{total_7d - total_prev_7d:.2f}",
        "top_counterparties": [
            {"name": name, "total_eur": f"{amt:.2f}"} for name, amt in top_5
        ],
        "top_categories": [
            {"category": cat, "total_eur": f"{amt:.2f}"} for cat, amt in top_categories
        ],
        "transaction_count_30d": len(spend_30d),
    }


def _cashflow_forecast(
    balance: Decimal,
    payments: list[PaymentSummary],
    scheduled: list[dict],
    savings: list[dict],
    horizon_days: int,
) -> dict[str, Any]:
    spend_30d = _spending_only(_days_ago(payments, 30))
    avg_daily = sum(abs(_parse_amount(p)) for p in spend_30d) / 30 if spend_30d else Decimal("0")
    income = _detect_income_cycle(payments)
    upcoming_bills = _scheduled_total(scheduled, horizon_days)

    projection = []
    running = balance
    danger_date = None
    for day_offset in range(1, horizon_days + 1):
        running -= avg_daily
        d = date.today() + timedelta(days=day_offset)
        if income.get("detected") and income.get("days_until_next") == day_offset:
            running += Decimal(income.get("amount", "0"))
        if running < 0 and danger_date is None:
            danger_date = d.isoformat()
        if day_offset in (7, 14, 21, 30):
            projection.append({"day": day_offset, "date": d.isoformat(), "projected_balance_eur": f"{running:.2f}"})

    return {
        "focus": "cashflow_forecast",
        "balance_eur": f"{balance:.2f}",
        "avg_daily_spend_eur": f"{avg_daily:.2f}",
        "upcoming_bills_eur": f"{upcoming_bills:.2f}",
        "income_cycle": income,
        "projection": projection,
        "danger_date": danger_date,
        "horizon_days": horizon_days,
    }


def _anomalies(
    balance: Decimal,
    payments: list[PaymentSummary],
    scheduled: list[dict],
    savings: list[dict],
    horizon_days: int,
) -> dict[str, Any]:
    spend = _spending_only(payments)
    amounts = [float(abs(_parse_amount(p))) for p in spend]

    anomalies = []
    if len(amounts) >= 3:
        avg = mean(amounts)
        sd = stdev(amounts) if len(amounts) > 1 else 0.0
        threshold = avg + 2 * sd if sd > 0 else avg * 2
        for p in spend:
            if float(abs(_parse_amount(p))) > threshold:
                anomalies.append({
                    "date": p.date,
                    "counterparty": p.counterparty,
                    "amount_eur": f"{abs(_parse_amount(p)):.2f}",
                    "reason": "unusually_large",
                })

    known = {p.counterparty for p in payments[: len(payments) // 2]}
    recent = _days_ago(payments, 14)
    for p in _spending_only(recent):
        if p.counterparty not in known and not any(
            a["counterparty"] == p.counterparty for a in anomalies
        ):
            anomalies.append({
                "date": p.date,
                "counterparty": p.counterparty,
                "amount_eur": f"{abs(_parse_amount(p)):.2f}",
                "reason": "new_counterparty",
            })

    return {
        "focus": "anomalies",
        "balance_eur": f"{balance:.2f}",
        "anomalies": anomalies,
        "total_transactions_checked": len(spend),
    }


def _savings_health(
    balance: Decimal,
    payments: list[PaymentSummary],
    scheduled: list[dict],
    savings: list[dict],
    horizon_days: int,
) -> dict[str, Any]:
    savings_total = sum(Decimal(s.get("balance", "0")) for s in savings)
    incomes = _income_only(payments)
    total_income = sum(_parse_amount(p) for p in incomes) if incomes else Decimal("0")
    savings_pct = (savings_total / total_income * 100) if total_income > 0 else Decimal("0")

    savings_transfers = [
        p for p in payments
        if _parse_amount(p) < 0 and "sav" in (p.description or "").lower()
    ]
    monthly_contrib = sum(abs(_parse_amount(p)) for p in savings_transfers)

    return {
        "focus": "savings_health",
        "savings_accounts": [
            {"name": s.get("description", ""), "balance_eur": s.get("balance", "0")}
            for s in savings
        ],
        "savings_total_eur": f"{savings_total:.2f}",
        "total_income_in_history_eur": f"{total_income:.2f}",
        "savings_as_pct_of_income": f"{savings_pct:.1f}",
        "detected_savings_contributions_eur": f"{monthly_contrib:.2f}",
    }


def _general(
    balance: Decimal,
    payments: list[PaymentSummary],
    scheduled: list[dict],
    savings: list[dict],
    horizon_days: int,
) -> dict[str, Any]:
    aff = _affordability(balance, payments, scheduled, savings, horizon_days)
    breakdown = _spending_breakdown(balance, payments, scheduled, savings, horizon_days)
    anomaly = _anomalies(balance, payments, scheduled, savings, horizon_days)
    return {
        "focus": "general",
        "balance_eur": aff["balance_eur"],
        "savings_total_eur": aff["savings_total_eur"],
        "discretionary_buffer_eur": aff["discretionary_buffer_eur"],
        "avg_daily_spend_eur": aff["avg_daily_spend_eur"],
        "top_counterparties": breakdown["top_counterparties"][:3],
        "week_over_week_delta_eur": breakdown["week_over_week_delta_eur"],
        "anomalies": anomaly["anomalies"][:3],
        "income_cycle": aff["income_cycle"],
    }
