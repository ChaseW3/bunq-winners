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
