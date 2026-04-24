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
