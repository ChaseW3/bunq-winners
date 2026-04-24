# bunq Voice Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the FastAPI backend that powers bunq Voice's three demo flows (balance, send money, scan bill) end-to-end against the bunq sandbox, testable without a browser.

**Architecture:** FastAPI app with five modules — `transport` (WS + REST), `orchestrator` (STT → LLM-with-tools → TTS), `tools` (bunq-backed functions), `bunq_client` (official SDK wrapper), `media` (STT/TTS adapters), plus an in-memory `session` store. Session state is injected into the LLM system prompt every turn so multi-turn confirmation ("send €20... yes") is robust.

**Tech Stack:** Python 3.11, FastAPI, Uvicorn, official `bunq_sdk` (Python), Anthropic SDK (Claude) for LLM + vision, OpenAI SDK for Whisper STT + TTS, `python-dotenv`, `pytest`, `httpx` (tests).

---

## File Structure

```
backend/
  app.py                       # FastAPI entrypoint, CORS, mount routers
  config.py                    # env validation (fail-fast)
  transport/
    __init__.py
    voice_ws.py                # /voice WebSocket
    scan.py                    # POST /scan
    session.py                 # POST /session, DELETE /session/{id}
  orchestrator/
    __init__.py
    turn.py                    # run_turn(session, audio_bytes) -> audio_bytes
    scan.py                    # run_scan(session, image_bytes) -> (reply_text, audio_bytes)
    prompts.py                 # build_system_prompt(session)
    llm.py                     # thin Anthropic wrapper with tool loop
  tools/
    __init__.py
    registry.py                # tool schemas + dispatch table
    balance.py                 # get_balance
    payments.py                # list_recent_payments, create_draft_payment,
                               # confirm_draft_payment, cancel_pending
    contacts.py                # find_contact
  bunq_client/
    __init__.py
    client.py                  # singleton wrapper
    bootstrap.py               # installation/session at startup
  media/
    __init__.py
    stt.py                     # Whisper adapter
    tts.py                     # OpenAI TTS adapter
  session/
    __init__.py
    store.py                   # in-memory dict + helpers
  tests/
    __init__.py
    conftest.py                # shared fixtures: fake LLM, fake bunq, temp session
    test_session_store.py
    test_tools_contacts.py
    test_tools_payments.py
    test_orchestrator_turn.py
    test_orchestrator_scan.py
    test_flows_end_to_end.py   # against sandbox, skipped without env var
fixtures/
  audio/
    balance_query.wav
    send_20_michelle.wav
    yes.wav
  bills/
    kpn_invoice.jpg
pyproject.toml
.env.example
```

---

## Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `backend/__init__.py`
- Create: `backend/config.py`
- Create: `.env.example`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "bunq-voice-backend"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "python-dotenv>=1.0",
  "bunq_sdk>=1.21",
  "anthropic>=0.40",
  "openai>=1.55",
  "httpx>=0.27",
  "pydantic>=2.9",
]

[project.optional-dependencies]
dev = ["pytest>=8.3", "pytest-asyncio>=0.24", "pytest-mock>=3.14"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["backend/tests"]
```

- [ ] **Step 2: Create `.env.example`**

```
BUNQ_API_KEY=
BUNQ_ENVIRONMENT=SANDBOX
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
LLM_MODEL=claude-sonnet-4-6
TTS_VOICE=alloy
```

- [ ] **Step 3: Write failing test for `config.load()`**

Create `backend/tests/test_config.py`:

```python
import pytest
from backend.config import load, Config

def test_load_reads_required_env(monkeypatch):
    monkeypatch.setenv("BUNQ_API_KEY", "k1")
    monkeypatch.setenv("BUNQ_ENVIRONMENT", "SANDBOX")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k2")
    monkeypatch.setenv("OPENAI_API_KEY", "k3")
    cfg = load()
    assert isinstance(cfg, Config)
    assert cfg.bunq_api_key == "k1"
    assert cfg.llm_model == "claude-sonnet-4-6"  # default

def test_load_raises_when_missing(monkeypatch):
    monkeypatch.delenv("BUNQ_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="BUNQ_API_KEY"):
        load()
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest backend/tests/test_config.py -v`
Expected: FAIL — `backend.config` module not found.

- [ ] **Step 5: Implement `backend/config.py`**

```python
import os
from dataclasses import dataclass
from dotenv import load_dotenv

@dataclass(frozen=True)
class Config:
    bunq_api_key: str
    bunq_environment: str
    anthropic_api_key: str
    openai_api_key: str
    llm_model: str
    tts_voice: str

REQUIRED = ["BUNQ_API_KEY", "BUNQ_ENVIRONMENT", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"]

def load() -> Config:
    load_dotenv()
    missing = [k for k in REQUIRED if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")
    return Config(
        bunq_api_key=os.environ["BUNQ_API_KEY"],
        bunq_environment=os.environ["BUNQ_ENVIRONMENT"],
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ["OPENAI_API_KEY"],
        llm_model=os.environ.get("LLM_MODEL", "claude-sonnet-4-6"),
        tts_voice=os.environ.get("TTS_VOICE", "alloy"),
    )
```

Also create empty `backend/__init__.py` and `backend/tests/__init__.py`, and an empty `backend/tests/conftest.py`.

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest backend/tests/test_config.py -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .env.example backend/
git commit -m "feat: scaffold backend package with config loader"
```

---

## Task 2: Session store

**Files:**
- Create: `backend/session/__init__.py`
- Create: `backend/session/store.py`
- Create: `backend/tests/test_session_store.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_session_store.py`:

```python
from backend.session.store import SessionStore

def test_create_returns_unique_id():
    s = SessionStore()
    a = s.create(bunq_user_id=1, primary_account_id=2)
    b = s.create(bunq_user_id=1, primary_account_id=2)
    assert a != b

def test_get_returns_session():
    s = SessionStore()
    sid = s.create(bunq_user_id=1, primary_account_id=2)
    sess = s.get(sid)
    assert sess["bunq_user_id"] == 1
    assert sess["primary_account_id"] == 2
    assert sess["pending_draft"] is None
    assert sess["contacts_cache"] == []
    assert sess["history"] == []

def test_set_pending_draft_and_clear():
    s = SessionStore()
    sid = s.create(bunq_user_id=1, primary_account_id=2)
    s.set_pending_draft(sid, {"draft_id": "d1", "amount": "20", "counterparty": "M", "source": "voice"})
    assert s.get(sid)["pending_draft"]["draft_id"] == "d1"
    s.clear_pending_draft(sid)
    assert s.get(sid)["pending_draft"] is None

def test_get_missing_raises():
    s = SessionStore()
    try:
        s.get("nope")
    except KeyError:
        return
    raise AssertionError("expected KeyError")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/test_session_store.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `backend/session/store.py`**

```python
import uuid
from typing import Any

class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}

    def create(self, *, bunq_user_id: int, primary_account_id: int) -> str:
        sid = uuid.uuid4().hex
        self._sessions[sid] = {
            "bunq_user_id": bunq_user_id,
            "primary_account_id": primary_account_id,
            "contacts_cache": [],
            "pending_draft": None,
            "history": [],
        }
        return sid

    def get(self, sid: str) -> dict[str, Any]:
        if sid not in self._sessions:
            raise KeyError(sid)
        return self._sessions[sid]

    def set_pending_draft(self, sid: str, draft: dict[str, Any]) -> None:
        self.get(sid)["pending_draft"] = draft

    def clear_pending_draft(self, sid: str) -> None:
        self.get(sid)["pending_draft"] = None

    def set_contacts(self, sid: str, contacts: list[dict[str, Any]]) -> None:
        self.get(sid)["contacts_cache"] = contacts

    def append_history(self, sid: str, entry: dict[str, Any]) -> None:
        hist = self.get(sid)["history"]
        hist.append(entry)
        if len(hist) > 20:
            del hist[: len(hist) - 20]

    def delete(self, sid: str) -> None:
        self._sessions.pop(sid, None)
```

Also create `backend/session/__init__.py` that re-exports: `from .store import SessionStore`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest backend/tests/test_session_store.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/session/ backend/tests/test_session_store.py
git commit -m "feat: in-memory session store with pending-draft helpers"
```

---

## Task 3: bunq client wrapper (fakeable interface)

**Files:**
- Create: `backend/bunq_client/__init__.py`
- Create: `backend/bunq_client/client.py`
- Create: `backend/bunq_client/bootstrap.py`
- Create: `backend/tests/fakes.py`

This task defines the **interface** we depend on and provides a fake. The real SDK wiring is in Task 4 — doing it in two steps keeps downstream tasks testable without sandbox credentials.

- [ ] **Step 1: Write the interface (protocol) and fake**

Create `backend/bunq_client/client.py`:

```python
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
```

Create `backend/bunq_client/__init__.py`:

```python
from .client import BunqClient, Contact, PaymentSummary, DraftResult, ConfirmResult
```

Create `backend/tests/fakes.py`:

```python
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
```

Also create an empty `backend/bunq_client/bootstrap.py` (implemented in Task 4).

- [ ] **Step 2: Smoke test**

Run: `python -c "from backend.tests.fakes import FakeBunqClient; c = FakeBunqClient(); print(c.balance())"`
Expected: `1247.00`.

- [ ] **Step 3: Commit**

```bash
git add backend/bunq_client/ backend/tests/fakes.py
git commit -m "feat: define BunqClient protocol and test fake"
```

---

## Task 4: Real bunq SDK wrapper + bootstrap

**Files:**
- Modify: `backend/bunq_client/client.py` — add `RealBunqClient`
- Modify: `backend/bunq_client/bootstrap.py`

The official SDK needs an installation + device registration + session setup once at startup. This task wires that and implements each protocol method.

- [ ] **Step 1: Implement `bootstrap.py`**

```python
from pathlib import Path
from bunq.sdk.context.api_context import ApiContext
from bunq.sdk.context.api_environment_type import ApiEnvironmentType
from bunq.sdk.context.bunq_context import BunqContext

CONTEXT_FILE = Path(".bunq_context.cfg")

def ensure_context(api_key: str, environment: str, description: str = "bunq-voice") -> None:
    env = ApiEnvironmentType.SANDBOX if environment.upper() == "SANDBOX" else ApiEnvironmentType.PRODUCTION
    if CONTEXT_FILE.exists():
        ctx = ApiContext.restore(str(CONTEXT_FILE))
        try:
            ctx.ensure_session_active()
        except Exception:
            ctx = ApiContext.create(env, api_key, description)
    else:
        ctx = ApiContext.create(env, api_key, description)
    ctx.save(str(CONTEXT_FILE))
    BunqContext.load_api_context(ctx)
```

Add `.bunq_context.cfg` to `.gitignore`:

```bash
echo ".bunq_context.cfg" >> .gitignore
```

- [ ] **Step 2: Append `RealBunqClient` to `backend/bunq_client/client.py`**

```python
from decimal import Decimal
from bunq.sdk.context.bunq_context import BunqContext
from bunq.sdk.model.generated.endpoint import (
    MonetaryAccount, Payment, DraftPayment, UserContact,
)
from bunq.sdk.model.generated.object_ import Amount, Pointer

class RealBunqClient:
    def __init__(self) -> None:
        self._primary_account_id: int | None = None

    def primary_account_id(self) -> int:
        if self._primary_account_id is None:
            accounts = MonetaryAccount.list().value
            active = [a for a in accounts if a.MonetaryAccountBank and a.MonetaryAccountBank.status == "ACTIVE"]
            if not active:
                raise RuntimeError("No active monetary account")
            self._primary_account_id = active[0].MonetaryAccountBank.id_
        return self._primary_account_id

    def balance(self, account_id: int | None = None) -> Decimal:
        aid = account_id or self.primary_account_id()
        acc = MonetaryAccount.get(aid).value.MonetaryAccountBank
        return Decimal(acc.balance.value)

    def recent_payments(self, account_id: int | None = None, limit: int = 5) -> list[PaymentSummary]:
        aid = account_id or self.primary_account_id()
        page = Payment.list(aid, params={"count": str(limit)}).value
        return [
            PaymentSummary(
                date=p.created,
                counterparty=p.counterparty_alias.display_name or p.counterparty_alias.label_monetary_account.iban,
                amount=Decimal(p.amount.value),
                description=p.description or "",
            )
            for p in page
        ]

    def list_contacts(self) -> list[Contact]:
        try:
            page = UserContact.list().value
        except Exception:
            return []
        out: list[Contact] = []
        for c in page:
            iban = getattr(c, "iban", None) or ""
            name = getattr(c, "display_name", None) or ""
            if iban and name:
                out.append(Contact(id=str(c.id_), name=name, iban=iban))
        return out

    def create_draft_payment(self, account_id: int, iban: str, amount: Decimal, description: str) -> DraftResult:
        entry = {
            "amount": Amount(str(amount), "EUR"),
            "counterparty_alias": Pointer("IBAN", iban),
            "description": description or "bunq Voice",
        }
        draft_id = DraftPayment.create(
            entries=[entry],
            monetary_account_id=account_id,
            number_of_required_accepts=1,
        ).value
        return DraftResult(draft_id=str(draft_id))

    def confirm_draft_payment(self, draft_id: str) -> ConfirmResult:
        DraftPayment.update(
            draft_payment_id=int(draft_id),
            status="ACCEPTED",
            monetary_account_id=self.primary_account_id(),
        )
        return ConfirmResult(status="OK", new_balance=self.balance())
```

> **Note:** The exact bunq SDK method names and parameters have evolved across versions. If `DraftPayment.create` / `.update` signatures differ, match the signatures in the installed `bunq_sdk` package (check `bunq/sdk/model/generated/endpoint.py`). The protocol in `BunqClient` is the stable interface everything downstream depends on — keep it unchanged.

- [ ] **Step 3: Manual smoke test (requires sandbox key)**

Create `scripts/smoke_bunq.py` (gitignored or committed to `scripts/`):

```python
from backend.config import load
from backend.bunq_client.bootstrap import ensure_context
from backend.bunq_client.client import RealBunqClient

cfg = load()
ensure_context(cfg.bunq_api_key, cfg.bunq_environment)
c = RealBunqClient()
print("primary:", c.primary_account_id())
print("balance:", c.balance())
print("payments:", c.recent_payments(limit=3))
```

Run: `python scripts/smoke_bunq.py`
Expected: prints a primary account id, a Decimal balance, and a small list of payments.

- [ ] **Step 4: Commit**

```bash
git add backend/bunq_client/ scripts/smoke_bunq.py .gitignore
git commit -m "feat: real bunq SDK wrapper with bootstrap"
```

---

## Task 5: Contact fuzzy match tool

**Files:**
- Create: `backend/tools/__init__.py`
- Create: `backend/tools/contacts.py`
- Create: `backend/tests/test_tools_contacts.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_tools_contacts.py`:

```python
from backend.tools.contacts import find_contact
from backend.tests.fakes import FakeBunqClient

def test_exact_match_returns_one():
    c = FakeBunqClient()
    result = find_contact(c, "Michelle")
    assert len(result) == 1
    assert result[0]["name"] == "Michelle Weng"

def test_case_insensitive():
    c = FakeBunqClient()
    result = find_contact(c, "michelle")
    assert len(result) == 1

def test_partial_match():
    c = FakeBunqClient()
    result = find_contact(c, "Jan")
    assert len(result) == 1
    assert result[0]["name"] == "Jan Bakker"

def test_no_match_returns_empty():
    c = FakeBunqClient()
    result = find_contact(c, "Xyzzy")
    assert result == []

def test_result_shape():
    c = FakeBunqClient()
    r = find_contact(c, "Finn")[0]
    assert set(r.keys()) == {"id", "name", "iban"}
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest backend/tests/test_tools_contacts.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `backend/tools/contacts.py`**

```python
from backend.bunq_client import BunqClient

def find_contact(client: BunqClient, query: str) -> list[dict]:
    q = query.strip().lower()
    if not q:
        return []
    matches = [c for c in client.list_contacts() if q in c.name.lower()]
    return [{"id": c.id, "name": c.name, "iban": c.iban} for c in matches]
```

Create `backend/tools/__init__.py` (empty for now).

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest backend/tests/test_tools_contacts.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/tools/ backend/tests/test_tools_contacts.py
git commit -m "feat: find_contact tool with fuzzy name match"
```

---

## Task 6: Balance & payments tools

**Files:**
- Create: `backend/tools/balance.py`
- Create: `backend/tools/payments.py`
- Create: `backend/tests/test_tools_payments.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_tools_payments.py`:

```python
from decimal import Decimal
from backend.session.store import SessionStore
from backend.tools.balance import get_balance
from backend.tools.payments import (
    list_recent_payments,
    create_draft_payment,
    confirm_draft_payment,
    cancel_pending,
)
from backend.tests.fakes import FakeBunqClient

def _fresh():
    c = FakeBunqClient()
    s = SessionStore()
    sid = s.create(bunq_user_id=1, primary_account_id=c.primary_account_id())
    return c, s, sid

def test_get_balance_returns_primary():
    c, s, sid = _fresh()
    r = get_balance(c, s, sid)
    assert r["balance"] == "1247.00"
    assert r["currency"] == "EUR"

def test_list_recent_payments_limit():
    c, s, sid = _fresh()
    r = list_recent_payments(c, s, sid, limit=1)
    assert len(r) == 1
    assert "counterparty" in r[0]

def test_create_draft_writes_session_state():
    c, s, sid = _fresh()
    r = create_draft_payment(c, s, sid, iban="NL00BUNQ0000000001", amount="20.00", description="dinner", counterparty_name="Michelle Weng")
    assert r["draft_id"].startswith("draft-")
    pending = s.get(sid)["pending_draft"]
    assert pending["draft_id"] == r["draft_id"]
    assert pending["amount"] == "20.00"
    assert pending["counterparty"] == "Michelle Weng"
    assert pending["source"] == "voice"

def test_confirm_matches_pending_and_clears():
    c, s, sid = _fresh()
    create = create_draft_payment(c, s, sid, iban="NL00BUNQ0000000001", amount="20.00", description="", counterparty_name="Michelle Weng")
    r = confirm_draft_payment(c, s, sid, draft_id=create["draft_id"])
    assert r["status"] == "OK"
    assert Decimal(r["new_balance"]) == Decimal("1227.00")
    assert s.get(sid)["pending_draft"] is None

def test_confirm_rejects_mismatched_draft():
    c, s, sid = _fresh()
    create_draft_payment(c, s, sid, iban="NL00BUNQ0000000001", amount="20.00", description="", counterparty_name="Michelle Weng")
    try:
        confirm_draft_payment(c, s, sid, draft_id="nope")
    except ValueError:
        return
    raise AssertionError("expected ValueError")

def test_cancel_pending_clears():
    c, s, sid = _fresh()
    create_draft_payment(c, s, sid, iban="NL00BUNQ0000000001", amount="20.00", description="", counterparty_name="Michelle Weng")
    cancel_pending(c, s, sid)
    assert s.get(sid)["pending_draft"] is None
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest backend/tests/test_tools_payments.py -v`
Expected: FAIL — modules missing.

- [ ] **Step 3: Implement `backend/tools/balance.py`**

```python
from backend.bunq_client import BunqClient
from backend.session.store import SessionStore

def get_balance(client: BunqClient, store: SessionStore, sid: str) -> dict:
    sess = store.get(sid)
    aid = sess["primary_account_id"]
    bal = client.balance(aid)
    return {"account": "primary", "balance": f"{bal:.2f}", "currency": "EUR"}
```

- [ ] **Step 4: Implement `backend/tools/payments.py`**

```python
from decimal import Decimal
from backend.bunq_client import BunqClient
from backend.session.store import SessionStore

def list_recent_payments(client: BunqClient, store: SessionStore, sid: str, limit: int = 5) -> list[dict]:
    sess = store.get(sid)
    ps = client.recent_payments(sess["primary_account_id"], limit=limit)
    return [
        {"date": p.date, "counterparty": p.counterparty, "amount": f"{p.amount:.2f}", "description": p.description}
        for p in ps
    ]

def create_draft_payment(
    client: BunqClient,
    store: SessionStore,
    sid: str,
    *,
    iban: str,
    amount: str,
    description: str,
    counterparty_name: str,
) -> dict:
    sess = store.get(sid)
    amt = Decimal(amount)
    draft = client.create_draft_payment(sess["primary_account_id"], iban, amt, description)
    store.set_pending_draft(sid, {
        "draft_id": draft.draft_id,
        "amount": f"{amt:.2f}",
        "counterparty": counterparty_name,
        "source": "voice",
    })
    return {"draft_id": draft.draft_id}

def confirm_draft_payment(client: BunqClient, store: SessionStore, sid: str, *, draft_id: str) -> dict:
    sess = store.get(sid)
    pending = sess["pending_draft"]
    if not pending or pending["draft_id"] != draft_id:
        raise ValueError(f"No pending draft matches {draft_id}")
    result = client.confirm_draft_payment(draft_id)
    store.clear_pending_draft(sid)
    return {"status": result.status, "new_balance": f"{result.new_balance:.2f}"}

def cancel_pending(client: BunqClient, store: SessionStore, sid: str) -> dict:
    store.clear_pending_draft(sid)
    return {"status": "cancelled"}
```

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest backend/tests/test_tools_payments.py -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/tools/ backend/tests/test_tools_payments.py
git commit -m "feat: balance + payments tools with session-bound drafts"
```

---

## Task 7: Tool registry (schemas + dispatch)

**Files:**
- Create: `backend/tools/registry.py`
- Create: `backend/tests/test_registry.py`

The LLM needs JSON schemas. The orchestrator needs one dispatch call. Build both here.

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_registry.py`:

```python
from backend.session.store import SessionStore
from backend.tools.registry import tool_schemas, dispatch
from backend.tests.fakes import FakeBunqClient

def test_tool_schemas_cover_all_tools():
    names = {t["name"] for t in tool_schemas()}
    assert names == {
        "get_balance",
        "list_recent_payments",
        "find_contact",
        "create_draft_payment",
        "confirm_draft_payment",
        "cancel_pending",
    }

def test_dispatch_get_balance():
    c = FakeBunqClient()
    s = SessionStore()
    sid = s.create(bunq_user_id=1, primary_account_id=c.primary_account_id())
    result = dispatch(c, s, sid, "get_balance", {})
    assert result["balance"] == "1247.00"

def test_dispatch_unknown_tool_raises():
    c = FakeBunqClient()
    s = SessionStore()
    sid = s.create(bunq_user_id=1, primary_account_id=42)
    try:
        dispatch(c, s, sid, "bogus", {})
    except KeyError:
        return
    raise AssertionError("expected KeyError")
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest backend/tests/test_registry.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `backend/tools/registry.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest backend/tests/test_registry.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/tools/registry.py backend/tests/test_registry.py
git commit -m "feat: tool registry with JSON schemas and dispatch"
```

---

## Task 8: Prompt builder

**Files:**
- Create: `backend/orchestrator/__init__.py`
- Create: `backend/orchestrator/prompts.py`
- Create: `backend/tests/test_prompts.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_prompts.py`:

```python
from backend.session.store import SessionStore
from backend.orchestrator.prompts import build_system_prompt

def test_static_parts_present():
    s = SessionStore()
    sid = s.create(bunq_user_id=1, primary_account_id=42)
    p = build_system_prompt(s.get(sid))
    assert "bunq Voice" in p
    assert "tools" in p.lower()
    assert "two sentences" in p.lower() or "short" in p.lower()

def test_pending_draft_injected():
    s = SessionStore()
    sid = s.create(bunq_user_id=1, primary_account_id=42)
    s.set_pending_draft(sid, {
        "draft_id": "d-1", "amount": "20.00",
        "counterparty": "Michelle Weng", "source": "voice",
    })
    p = build_system_prompt(s.get(sid))
    assert "Michelle Weng" in p
    assert "20.00" in p
    assert "d-1" in p
    assert "confirm_draft_payment" in p
    assert "cancel_pending" in p

def test_no_pending_draft_no_confirm_language():
    s = SessionStore()
    sid = s.create(bunq_user_id=1, primary_account_id=42)
    p = build_system_prompt(s.get(sid))
    assert "pending payment" not in p.lower()
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest backend/tests/test_prompts.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `backend/orchestrator/prompts.py`**

```python
from typing import Any

STATIC = (
    "You are bunq Voice, a voice banking assistant. "
    "Use the provided tools to answer questions and act on the user's behalf. "
    "Keep every spoken reply to one or two short sentences. "
    "Speak amounts clearly, e.g. 'twenty euros', not '20 EUR'. "
    "Never invent data — if a tool is needed, call it. "
    "Before moving money you MUST create a draft payment; never call confirm_draft_payment until the user has explicitly said yes."
)

def build_system_prompt(session: dict[str, Any]) -> str:
    parts = [STATIC]
    pending = session.get("pending_draft")
    if pending:
        parts.append(
            f"Current pending payment: {pending['amount']} EUR to {pending['counterparty']} "
            f"(draft_id={pending['draft_id']}). "
            "If the user confirms ('yes', 'confirm', 'do it', 'go ahead'), call confirm_draft_payment with this draft_id. "
            "If the user declines ('no', 'cancel', 'never mind'), call cancel_pending."
        )
    return "\n\n".join(parts)
```

Create `backend/orchestrator/__init__.py` (empty).

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest backend/tests/test_prompts.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/orchestrator/ backend/tests/test_prompts.py
git commit -m "feat: system prompt builder with pending-draft injection"
```

---

## Task 9: LLM tool loop (Anthropic adapter, mockable)

**Files:**
- Create: `backend/orchestrator/llm.py`
- Create: `backend/tests/test_llm_loop.py`

The LLM loop has one responsibility: take a user message + session + tools, run the tool-use loop until the model produces a final text reply. We isolate this so tests can drive it with a fake client.

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_llm_loop.py`:

```python
from backend.session.store import SessionStore
from backend.orchestrator.llm import run_llm_turn
from backend.tests.fakes import FakeBunqClient

class FakeAnthropic:
    """Scripted responses. Each call pops one from the queue."""
    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.calls: list[dict] = []

    def messages_create(self, **kwargs):
        self.calls.append(kwargs)
        return self.scripted.pop(0)

def _make_text(text):
    return {"stop_reason": "end_turn", "content": [{"type": "text", "text": text}]}

def _make_tool_use(tool_name, input_, tool_use_id="t1"):
    return {
        "stop_reason": "tool_use",
        "content": [{"type": "tool_use", "id": tool_use_id, "name": tool_name, "input": input_}],
    }

def test_single_turn_no_tool_call():
    bunq = FakeBunqClient()
    store = SessionStore()
    sid = store.create(bunq_user_id=1, primary_account_id=bunq.primary_account_id())
    llm = FakeAnthropic([_make_text("You have 1247 euros.")])
    reply = run_llm_turn(llm, bunq, store, sid, user_text="what is my balance")
    assert reply == "You have 1247 euros."

def test_tool_call_then_text():
    bunq = FakeBunqClient()
    store = SessionStore()
    sid = store.create(bunq_user_id=1, primary_account_id=bunq.primary_account_id())
    llm = FakeAnthropic([
        _make_tool_use("get_balance", {}),
        _make_text("You have 1247 euros."),
    ])
    reply = run_llm_turn(llm, bunq, store, sid, user_text="balance?")
    assert reply == "You have 1247 euros."
    assert len(llm.calls) == 2  # initial + after tool result

def test_two_turn_confirmation_flow():
    bunq = FakeBunqClient()
    store = SessionStore()
    sid = store.create(bunq_user_id=1, primary_account_id=bunq.primary_account_id())

    # Turn 1: find_contact then create_draft_payment then text
    llm1 = FakeAnthropic([
        _make_tool_use("find_contact", {"query": "Michelle"}),
        _make_tool_use("create_draft_payment", {
            "iban": "NL00BUNQ0000000001", "amount": "20.00",
            "description": "", "counterparty_name": "Michelle Weng",
        }),
        _make_text("Sending 20 euros to Michelle Weng. Say yes to confirm."),
    ])
    reply1 = run_llm_turn(llm1, bunq, store, sid, user_text="send 20 to Michelle")
    assert "Michelle Weng" in reply1
    assert store.get(sid)["pending_draft"] is not None

    # Turn 2: confirm
    pending_id = store.get(sid)["pending_draft"]["draft_id"]
    llm2 = FakeAnthropic([
        _make_tool_use("confirm_draft_payment", {"draft_id": pending_id}),
        _make_text("Done. New balance: 1227 euros."),
    ])
    reply2 = run_llm_turn(llm2, bunq, store, sid, user_text="yes")
    assert "Done" in reply2
    assert store.get(sid)["pending_draft"] is None
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest backend/tests/test_llm_loop.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `backend/orchestrator/llm.py`**

```python
from typing import Any, Protocol
from backend.bunq_client import BunqClient
from backend.session.store import SessionStore
from backend.tools.registry import tool_schemas, dispatch
from backend.orchestrator.prompts import build_system_prompt

MAX_ITERATIONS = 6

class LLMClient(Protocol):
    def messages_create(self, **kwargs: Any) -> dict[str, Any]: ...

def run_llm_turn(
    llm: LLMClient,
    bunq: BunqClient,
    store: SessionStore,
    sid: str,
    *,
    user_text: str,
    model: str = "claude-sonnet-4-6",
) -> str:
    system = build_system_prompt(store.get(sid))
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_text}]

    for _ in range(MAX_ITERATIONS):
        resp = llm.messages_create(
            model=model,
            system=system,
            tools=tool_schemas(),
            messages=messages,
            max_tokens=512,
        )
        blocks = resp["content"]
        stop = resp.get("stop_reason")
        messages.append({"role": "assistant", "content": blocks})

        if stop == "tool_use":
            tool_results = []
            for b in blocks:
                if b.get("type") != "tool_use":
                    continue
                try:
                    result = dispatch(bunq, store, sid, b["name"], b.get("input", {}))
                    content = _jsonable(result)
                    is_error = False
                except Exception as e:  # surface to the model, let it recover
                    content = f"Error: {type(e).__name__}: {e}"
                    is_error = True
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": b["id"],
                    "content": content if isinstance(content, str) else str(content),
                    "is_error": is_error,
                })
            messages.append({"role": "user", "content": tool_results})
            # refresh system prompt — pending_draft may have changed
            system = build_system_prompt(store.get(sid))
            continue

        # end_turn or stop — extract text blocks
        texts = [b["text"] for b in blocks if b.get("type") == "text"]
        return " ".join(t.strip() for t in texts if t.strip())

    raise RuntimeError("LLM loop exceeded max iterations")

def _jsonable(v: Any) -> str:
    import json
    try:
        return json.dumps(v, default=str)
    except Exception:
        return str(v)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest backend/tests/test_llm_loop.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/orchestrator/llm.py backend/tests/test_llm_loop.py
git commit -m "feat: LLM tool-use loop with fake-client tests"
```

---

## Task 10: Media adapters (STT + TTS)

**Files:**
- Create: `backend/media/__init__.py`
- Create: `backend/media/stt.py`
- Create: `backend/media/tts.py`
- Create: `backend/tests/test_media.py`

Interfaces small enough to be useful, concrete providers swappable.

- [ ] **Step 1: Write failing tests (interface-level)**

Create `backend/tests/test_media.py`:

```python
from backend.media.stt import STT
from backend.media.tts import TTS

class FakeSTT:
    def transcribe(self, audio: bytes, *, language: str = "en") -> str:
        return "transcribed text"

class FakeTTS:
    def speak(self, text: str) -> bytes:
        return b"AUDIO:" + text.encode()

def test_stt_protocol_shape():
    s: STT = FakeSTT()
    assert s.transcribe(b"\x00") == "transcribed text"

def test_tts_protocol_shape():
    t: TTS = FakeTTS()
    assert t.speak("hi") == b"AUDIO:hi"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest backend/tests/test_media.py -v`
Expected: FAIL — modules missing.

- [ ] **Step 3: Implement `backend/media/stt.py`**

```python
from typing import Protocol

class STT(Protocol):
    def transcribe(self, audio: bytes, *, language: str = "en") -> str: ...

class WhisperSTT:
    def __init__(self, openai_client) -> None:
        self._client = openai_client

    def transcribe(self, audio: bytes, *, language: str = "en") -> str:
        import io
        f = io.BytesIO(audio)
        f.name = "input.webm"
        resp = self._client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            language=language,
        )
        return resp.text
```

- [ ] **Step 4: Implement `backend/media/tts.py`**

```python
from typing import Protocol

class TTS(Protocol):
    def speak(self, text: str) -> bytes: ...

class OpenAITTS:
    def __init__(self, openai_client, voice: str = "alloy") -> None:
        self._client = openai_client
        self._voice = voice

    def speak(self, text: str) -> bytes:
        resp = self._client.audio.speech.create(
            model="tts-1",
            voice=self._voice,
            input=text,
            response_format="mp3",
        )
        return resp.read()
```

Create `backend/media/__init__.py`:

```python
from .stt import STT, WhisperSTT
from .tts import TTS, OpenAITTS
```

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest backend/tests/test_media.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/media/ backend/tests/test_media.py
git commit -m "feat: STT + TTS adapters behind narrow protocols"
```

---

## Task 11: Orchestrator — voice turn

**Files:**
- Create: `backend/orchestrator/turn.py`
- Create: `backend/tests/test_orchestrator_turn.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_orchestrator_turn.py`:

```python
from backend.session.store import SessionStore
from backend.orchestrator.turn import run_turn
from backend.tests.fakes import FakeBunqClient
from backend.tests.test_llm_loop import FakeAnthropic, _make_text, _make_tool_use

class StubSTT:
    def __init__(self, text): self.text = text
    def transcribe(self, audio, *, language="en"): return self.text

class StubTTS:
    def speak(self, text): return b"AUDIO:" + text.encode()

def test_run_turn_wires_stt_llm_tts():
    bunq = FakeBunqClient()
    store = SessionStore()
    sid = store.create(bunq_user_id=1, primary_account_id=bunq.primary_account_id())
    llm = FakeAnthropic([
        _make_tool_use("get_balance", {}),
        _make_text("You have 1247 euros."),
    ])
    stt = StubSTT("what is my balance")
    tts = StubTTS()

    result = run_turn(
        audio=b"\x00\x00",
        session_id=sid,
        store=store, bunq=bunq, llm=llm, stt=stt, tts=tts,
    )
    assert result.reply_text == "You have 1247 euros."
    assert result.reply_audio == b"AUDIO:You have 1247 euros."
    assert result.requires_confirm is False

def test_run_turn_flags_requires_confirm_when_draft_pending():
    bunq = FakeBunqClient()
    store = SessionStore()
    sid = store.create(bunq_user_id=1, primary_account_id=bunq.primary_account_id())
    llm = FakeAnthropic([
        _make_tool_use("find_contact", {"query": "Michelle"}),
        _make_tool_use("create_draft_payment", {
            "iban": "NL00BUNQ0000000001", "amount": "20.00",
            "description": "", "counterparty_name": "Michelle Weng",
        }),
        _make_text("Sending 20 euros to Michelle Weng. Say yes to confirm."),
    ])
    result = run_turn(
        audio=b"\x00", session_id=sid,
        store=store, bunq=bunq, llm=llm,
        stt=StubSTT("send 20 to michelle"), tts=StubTTS(),
    )
    assert result.requires_confirm is True
    assert result.pending["counterparty"] == "Michelle Weng"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest backend/tests/test_orchestrator_turn.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `backend/orchestrator/turn.py`**

```python
from dataclasses import dataclass
from backend.bunq_client import BunqClient
from backend.media import STT, TTS
from backend.orchestrator.llm import LLMClient, run_llm_turn
from backend.session.store import SessionStore

@dataclass
class TurnResult:
    user_text: str
    reply_text: str
    reply_audio: bytes
    requires_confirm: bool
    pending: dict | None

def run_turn(
    *,
    audio: bytes,
    session_id: str,
    store: SessionStore,
    bunq: BunqClient,
    llm: LLMClient,
    stt: STT,
    tts: TTS,
    model: str = "claude-sonnet-4-6",
) -> TurnResult:
    user_text = stt.transcribe(audio)
    reply_text = run_llm_turn(llm, bunq, store, session_id, user_text=user_text, model=model)
    reply_audio = tts.speak(reply_text)
    pending = store.get(session_id)["pending_draft"]
    return TurnResult(
        user_text=user_text,
        reply_text=reply_text,
        reply_audio=reply_audio,
        requires_confirm=pending is not None,
        pending=pending,
    )
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest backend/tests/test_orchestrator_turn.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/orchestrator/turn.py backend/tests/test_orchestrator_turn.py
git commit -m "feat: orchestrator run_turn wiring STT → LLM → TTS"
```

---

## Task 12: Orchestrator — scan flow

**Files:**
- Create: `backend/orchestrator/scan.py`
- Create: `backend/tests/test_orchestrator_scan.py`

Scan does NOT go through the voice LLM loop. It calls a vision model with a structured extraction prompt, then writes `pending_draft` directly and returns a spoken prompt.

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_orchestrator_scan.py`:

```python
from backend.session.store import SessionStore
from backend.orchestrator.scan import run_scan
from backend.tests.fakes import FakeBunqClient

class StubVision:
    def __init__(self, extracted): self.extracted = extracted
    def extract_bill(self, image_bytes): return self.extracted

class StubTTS:
    def speak(self, text): return b"A:" + text.encode()

def test_scan_writes_pending_draft_and_returns_audio():
    bunq = FakeBunqClient()
    store = SessionStore()
    sid = store.create(bunq_user_id=1, primary_account_id=bunq.primary_account_id())

    vision = StubVision({
        "creditor": "KPN",
        "iban": "NL00KPNL0000000099",
        "amount": "47.82",
        "due_date": "2026-11-15",
        "reference": "12345",
    })
    r = run_scan(image=b"\xFF\xD8", session_id=sid, store=store, bunq=bunq, vision=vision, tts=StubTTS())

    assert r.pending["counterparty"] == "KPN"
    assert r.pending["amount"] == "47.82"
    assert r.pending["source"] == "scan"
    assert "KPN" in r.reply_text
    assert "47" in r.reply_text
    assert r.reply_audio.startswith(b"A:")

def test_scan_reports_unreadable():
    bunq = FakeBunqClient()
    store = SessionStore()
    sid = store.create(bunq_user_id=1, primary_account_id=bunq.primary_account_id())
    vision = StubVision({"error": "unreadable"})
    r = run_scan(image=b"\xFF", session_id=sid, store=store, bunq=bunq, vision=vision, tts=StubTTS())
    assert r.pending is None
    assert "couldn't" in r.reply_text.lower() or "could not" in r.reply_text.lower()
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest backend/tests/test_orchestrator_scan.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `backend/orchestrator/scan.py`**

```python
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from backend.bunq_client import BunqClient
from backend.media import TTS
from backend.session.store import SessionStore

class Vision(Protocol):
    def extract_bill(self, image_bytes: bytes) -> dict: ...

@dataclass
class ScanResult:
    reply_text: str
    reply_audio: bytes
    pending: dict | None

def run_scan(*, image: bytes, session_id: str, store: SessionStore, bunq: BunqClient, vision: Vision, tts: TTS) -> ScanResult:
    extracted = vision.extract_bill(image)
    if "error" in extracted or not extracted.get("iban") or not extracted.get("amount"):
        msg = "I couldn't read that clearly. Try holding the phone about 20 centimetres above the paper."
        return ScanResult(reply_text=msg, reply_audio=tts.speak(msg), pending=None)

    creditor = extracted.get("creditor", "the creditor")
    amount = extracted["amount"]
    iban = extracted["iban"]
    description = extracted.get("reference", "")
    sess = store.get(session_id)
    draft = bunq.create_draft_payment(sess["primary_account_id"], iban, Decimal(amount), description)
    pending = {
        "draft_id": draft.draft_id,
        "amount": f"{Decimal(amount):.2f}",
        "counterparty": creditor,
        "source": "scan",
    }
    store.set_pending_draft(session_id, pending)

    euros, cents = f"{Decimal(amount):.2f}".split(".")
    msg = f"This is an invoice from {creditor} for {euros} euros {cents}. Say yes to pay it."
    return ScanResult(reply_text=msg, reply_audio=tts.speak(msg), pending=pending)
```

- [ ] **Step 4: Add real vision adapter**

Append to `backend/orchestrator/scan.py`:

```python
import base64, json

BILL_EXTRACTION_PROMPT = (
    "Extract payment details from this invoice image. "
    "Respond with ONLY a JSON object with keys: creditor, iban, amount, due_date, reference. "
    'Use "" for missing fields. Amount must be a decimal string without currency. '
    "If the image is unreadable or not an invoice, return {\"error\": \"unreadable\"}."
)

class AnthropicVision:
    def __init__(self, anthropic_client, model: str = "claude-sonnet-4-6") -> None:
        self._client = anthropic_client
        self._model = model

    def extract_bill(self, image_bytes: bytes) -> dict:
        b64 = base64.standard_b64encode(image_bytes).decode()
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                    {"type": "text", "text": BILL_EXTRACTION_PROMPT},
                ],
            }],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        if text.startswith("```"):
            text = text.strip("`").split("\n", 1)[-1].rsplit("```", 1)[0]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"error": "unreadable"}
```

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest backend/tests/test_orchestrator_scan.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/orchestrator/scan.py backend/tests/test_orchestrator_scan.py
git commit -m "feat: scan flow with vision extraction and pending_draft"
```

---

## Task 13: Transport — FastAPI app, session + scan endpoints

**Files:**
- Create: `backend/transport/__init__.py`
- Create: `backend/transport/session.py`
- Create: `backend/transport/scan.py`
- Create: `backend/app.py`
- Create: `backend/tests/test_transport_http.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_transport_http.py`:

```python
from fastapi.testclient import TestClient
from backend.app import build_app
from backend.session.store import SessionStore
from backend.tests.fakes import FakeBunqClient

class StubTTS:
    def speak(self, text): return b"A:" + text.encode()

class StubVision:
    def extract_bill(self, b):
        return {"creditor": "KPN", "iban": "NL00KPNL0000000099",
                "amount": "47.82", "due_date": "2026-11-15", "reference": ""}

def _client():
    app = build_app(
        store=SessionStore(),
        bunq=FakeBunqClient(),
        llm=None,                # not used in these tests
        stt=None,
        tts=StubTTS(),
        vision=StubVision(),
        cors_origins=["*"],
    )
    return TestClient(app)

def test_create_session():
    c = _client()
    r = c.post("/session")
    assert r.status_code == 200
    data = r.json()
    assert "session_id" in data
    assert data["primary_account_id"] == 42

def test_scan_endpoint_produces_pending():
    c = _client()
    sid = c.post("/session").json()["session_id"]
    files = {"image": ("bill.jpg", b"\xFF\xD8\xFF", "image/jpeg")}
    r = c.post(f"/scan?session_id={sid}", files=files)
    assert r.status_code == 200
    body = r.json()
    assert body["pending"]["counterparty"] == "KPN"
    assert body["reply_text"].startswith("This is an invoice from KPN")
    assert body["reply_audio_base64"]
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest backend/tests/test_transport_http.py -v`
Expected: FAIL — modules missing.

- [ ] **Step 3: Implement `backend/transport/session.py`**

```python
from fastapi import APIRouter, HTTPException
from backend.bunq_client import BunqClient
from backend.session.store import SessionStore

def session_router(store: SessionStore, bunq: BunqClient) -> APIRouter:
    r = APIRouter()

    @r.post("/session")
    def create():
        pid = bunq.primary_account_id()
        contacts = [{"id": c.id, "name": c.name, "iban": c.iban} for c in bunq.list_contacts()]
        sid = store.create(bunq_user_id=0, primary_account_id=pid)
        store.set_contacts(sid, contacts)
        return {"session_id": sid, "primary_account_id": pid}

    @r.delete("/session/{sid}")
    def destroy(sid: str):
        store.delete(sid)
        return {"ok": True}

    return r
```

- [ ] **Step 4: Implement `backend/transport/scan.py`**

```python
import base64
from fastapi import APIRouter, UploadFile, File, HTTPException
from backend.bunq_client import BunqClient
from backend.session.store import SessionStore
from backend.media import TTS
from backend.orchestrator.scan import run_scan, Vision

def scan_router(store: SessionStore, bunq: BunqClient, tts: TTS, vision: Vision) -> APIRouter:
    r = APIRouter()

    @r.post("/scan")
    async def scan(session_id: str, image: UploadFile = File(...)):
        try:
            store.get(session_id)
        except KeyError:
            raise HTTPException(404, "session not found")
        data = await image.read()
        result = run_scan(image=data, session_id=session_id, store=store, bunq=bunq, vision=vision, tts=tts)
        return {
            "reply_text": result.reply_text,
            "reply_audio_base64": base64.b64encode(result.reply_audio).decode(),
            "pending": result.pending,
        }

    return r
```

- [ ] **Step 5: Implement `backend/app.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.bunq_client import BunqClient
from backend.media import STT, TTS
from backend.orchestrator.llm import LLMClient
from backend.orchestrator.scan import Vision
from backend.session.store import SessionStore
from backend.transport.session import session_router
from backend.transport.scan import scan_router

def build_app(
    *,
    store: SessionStore,
    bunq: BunqClient,
    llm: LLMClient | None,
    stt: STT | None,
    tts: TTS,
    vision: Vision,
    cors_origins: list[str],
) -> FastAPI:
    app = FastAPI(title="bunq Voice")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(session_router(store, bunq))
    app.include_router(scan_router(store, bunq, tts, vision))
    # voice WS registered in Task 14
    app.state.store = store
    app.state.bunq = bunq
    app.state.llm = llm
    app.state.stt = stt
    app.state.tts = tts
    return app
```

Create empty `backend/transport/__init__.py`.

- [ ] **Step 6: Run tests to verify pass**

Run: `pytest backend/tests/test_transport_http.py -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
git add backend/app.py backend/transport/ backend/tests/test_transport_http.py
git commit -m "feat: FastAPI app with session + scan endpoints"
```

---

## Task 14: Transport — voice WebSocket

**Files:**
- Create: `backend/transport/voice_ws.py`
- Modify: `backend/app.py` — register WS route
- Create: `backend/tests/test_transport_ws.py`

Message protocol (JSON over WS, with audio as base64):

- Client → server: `{"type": "audio", "data": "<base64>"}` (one full utterance per message)
- Server → client: `{"type": "reply", "user_text": "...", "reply_text": "...", "reply_audio_base64": "...", "requires_confirm": bool, "pending": {...}|null}`
- Server → client on error: `{"type": "error", "message": "..."}`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_transport_ws.py`:

```python
import base64
from fastapi.testclient import TestClient
from backend.app import build_app
from backend.session.store import SessionStore
from backend.tests.fakes import FakeBunqClient
from backend.tests.test_llm_loop import FakeAnthropic, _make_text, _make_tool_use

class StubSTT:
    def __init__(self, text): self.text = text
    def transcribe(self, audio, *, language="en"): return self.text

class StubTTS:
    def speak(self, text): return b"A:" + text.encode()

class StubVision:
    def extract_bill(self, b): return {"error": "unreadable"}

def test_ws_voice_balance_turn():
    store = SessionStore()
    bunq = FakeBunqClient()
    llm = FakeAnthropic([
        _make_tool_use("get_balance", {}),
        _make_text("You have 1247 euros."),
    ])
    app = build_app(
        store=store, bunq=bunq, llm=llm,
        stt=StubSTT("what is my balance"), tts=StubTTS(),
        vision=StubVision(), cors_origins=["*"],
    )
    client = TestClient(app)
    sid = client.post("/session").json()["session_id"]

    with client.websocket_connect(f"/voice?session_id={sid}") as ws:
        ws.send_json({"type": "audio", "data": base64.b64encode(b"\x00").decode()})
        msg = ws.receive_json()
        assert msg["type"] == "reply"
        assert msg["user_text"] == "what is my balance"
        assert msg["reply_text"] == "You have 1247 euros."
        assert msg["requires_confirm"] is False
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest backend/tests/test_transport_ws.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `backend/transport/voice_ws.py`**

```python
import base64
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.bunq_client import BunqClient
from backend.media import STT, TTS
from backend.orchestrator.llm import LLMClient
from backend.orchestrator.turn import run_turn
from backend.session.store import SessionStore

def voice_ws_router(store: SessionStore, bunq: BunqClient, llm: LLMClient, stt: STT, tts: TTS, model: str) -> APIRouter:
    r = APIRouter()

    @r.websocket("/voice")
    async def voice(ws: WebSocket, session_id: str):
        await ws.accept()
        try:
            store.get(session_id)
        except KeyError:
            await ws.send_json({"type": "error", "message": "session not found"})
            await ws.close()
            return

        try:
            while True:
                msg = await ws.receive_json()
                if msg.get("type") != "audio":
                    await ws.send_json({"type": "error", "message": "expected audio"})
                    continue
                audio = base64.b64decode(msg["data"])
                result = run_turn(
                    audio=audio, session_id=session_id,
                    store=store, bunq=bunq, llm=llm, stt=stt, tts=tts, model=model,
                )
                await ws.send_json({
                    "type": "reply",
                    "user_text": result.user_text,
                    "reply_text": result.reply_text,
                    "reply_audio_base64": base64.b64encode(result.reply_audio).decode(),
                    "requires_confirm": result.requires_confirm,
                    "pending": result.pending,
                })
        except WebSocketDisconnect:
            return
        except Exception as e:
            await ws.send_json({"type": "error", "message": f"{type(e).__name__}: {e}"})
            await ws.close()

    return r
```

- [ ] **Step 4: Modify `backend/app.py` to register the WS route**

Replace the comment `# voice WS registered in Task 14` with:

```python
    if llm is not None and stt is not None:
        from backend.transport.voice_ws import voice_ws_router
        app.include_router(voice_ws_router(store, bunq, llm, stt, tts, model="claude-sonnet-4-6"))
```

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest backend/tests/test_transport_ws.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/transport/voice_ws.py backend/app.py backend/tests/test_transport_ws.py
git commit -m "feat: /voice WebSocket turn endpoint"
```

---

## Task 15: LLM/Anthropic real adapter

**Files:**
- Create: `backend/orchestrator/anthropic_adapter.py`
- Modify: `backend/orchestrator/__init__.py`

Bridge the `LLMClient` protocol to the real Anthropic SDK (which returns Pydantic-ish objects, not dicts).

- [ ] **Step 1: Implement the adapter**

Create `backend/orchestrator/anthropic_adapter.py`:

```python
from typing import Any

class AnthropicAdapter:
    def __init__(self, client) -> None:
        self._client = client

    def messages_create(self, **kwargs: Any) -> dict[str, Any]:
        resp = self._client.messages.create(**kwargs)
        return {
            "stop_reason": resp.stop_reason,
            "content": [self._block_to_dict(b) for b in resp.content],
        }

    @staticmethod
    def _block_to_dict(b: Any) -> dict[str, Any]:
        t = b.type
        if t == "text":
            return {"type": "text", "text": b.text}
        if t == "tool_use":
            return {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
        return {"type": t}
```

- [ ] **Step 2: Commit**

```bash
git add backend/orchestrator/anthropic_adapter.py
git commit -m "feat: Anthropic SDK adapter for LLMClient protocol"
```

---

## Task 16: Main entrypoint, wiring & manual smoke

**Files:**
- Modify: `backend/app.py` — add `create_production_app()`
- Create: `backend/__main__.py`

- [ ] **Step 1: Add production factory**

Append to `backend/app.py`:

```python
def create_production_app() -> FastAPI:
    from anthropic import Anthropic
    from openai import OpenAI
    from backend.config import load
    from backend.bunq_client.bootstrap import ensure_context
    from backend.bunq_client.client import RealBunqClient
    from backend.media import WhisperSTT, OpenAITTS
    from backend.orchestrator.anthropic_adapter import AnthropicAdapter
    from backend.orchestrator.scan import AnthropicVision

    cfg = load()
    ensure_context(cfg.bunq_api_key, cfg.bunq_environment)
    anthropic = Anthropic(api_key=cfg.anthropic_api_key)
    openai = OpenAI(api_key=cfg.openai_api_key)

    return build_app(
        store=SessionStore(),
        bunq=RealBunqClient(),
        llm=AnthropicAdapter(anthropic),
        stt=WhisperSTT(openai),
        tts=OpenAITTS(openai, voice=cfg.tts_voice),
        vision=AnthropicVision(anthropic, model=cfg.llm_model),
        cors_origins=["*"],
    )
```

- [ ] **Step 2: Create `backend/__main__.py`**

```python
import uvicorn
from backend.app import create_production_app

app = create_production_app()

if __name__ == "__main__":
    uvicorn.run("backend.__main__:app", host="0.0.0.0", port=8000, reload=False)
```

- [ ] **Step 3: Manual smoke**

With `.env` populated, run:

```bash
python -m backend
```

In another terminal:

```bash
curl -X POST http://localhost:8000/session
# Expect JSON with session_id, primary_account_id

# Voice smoke (requires a short wav at fixtures/audio/balance_query.wav):
python scripts/smoke_voice.py <session_id>
```

Create `scripts/smoke_voice.py`:

```python
import sys, base64, asyncio, json
import websockets

async def main(sid):
    uri = f"ws://localhost:8000/voice?session_id={sid}"
    with open("fixtures/audio/balance_query.wav", "rb") as f:
        audio = f.read()
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"type": "audio", "data": base64.b64encode(audio).decode()}))
        reply = json.loads(await ws.recv())
        print("user:", reply["user_text"])
        print("bot :", reply["reply_text"])

asyncio.run(main(sys.argv[1]))
```

Add `websockets` to dev deps if not present.

- [ ] **Step 4: Commit**

```bash
git add backend/__main__.py backend/app.py scripts/smoke_voice.py pyproject.toml
git commit -m "feat: production app factory and CLI entrypoint"
```

---

## Task 17: End-to-end sandbox test (optional, env-gated)

**Files:**
- Create: `backend/tests/test_flows_end_to_end.py`

- [ ] **Step 1: Write env-gated test**

```python
import os, base64
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(
    not os.environ.get("BUNQ_API_KEY") or not os.environ.get("ANTHROPIC_API_KEY") or not os.environ.get("OPENAI_API_KEY"),
    reason="sandbox credentials not set",
)

def test_balance_flow_against_sandbox():
    from backend.app import create_production_app
    app = create_production_app()
    client = TestClient(app)
    sid = client.post("/session").json()["session_id"]
    with open("fixtures/audio/balance_query.wav", "rb") as f:
        audio = f.read()
    with client.websocket_connect(f"/voice?session_id={sid}") as ws:
        ws.send_json({"type": "audio", "data": base64.b64encode(audio).decode()})
        msg = ws.receive_json()
        assert msg["type"] == "reply"
        assert "euro" in msg["reply_text"].lower() or "balance" in msg["reply_text"].lower()
```

- [ ] **Step 2: Run (only with env set)**

Run: `pytest backend/tests/test_flows_end_to_end.py -v`
Expected: either PASS (with sandbox keys) or SKIPPED (without).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_flows_end_to_end.py
git commit -m "test: end-to-end balance flow against sandbox (env-gated)"
```

---

## Task 18: Full test suite green

- [ ] **Step 1: Run full suite**

Run: `pytest backend/tests -v`
Expected: all PASS (sandbox E2E may SKIP).

- [ ] **Step 2: Fix anything red.** Do not proceed until green.

- [ ] **Step 3: Commit any fixes**

```bash
git add -A
git commit -m "chore: fix failing tests from full-suite review"
```

---

## Done criteria

- `pytest backend/tests -v` is green.
- `python -m backend` serves `POST /session`, `POST /scan`, and `WS /voice` and those three endpoints succeed end-to-end against bunq sandbox when a sandbox key is set.
- A new developer can read this plan top-to-bottom and land the backend without asking follow-up questions.
