# Local Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist conversation history to `memory.json` so Claude remembers past interactions across server restarts.

**Architecture:** On each voice/text turn, append `{role: user}` + `{role: assistant}` to the session history and write it to disk. On startup, load `memory.json` and seed the session — Claude receives the prior conversation as context in every subsequent call.

**Tech Stack:** Python stdlib `json` + `pathlib`, no new dependencies.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/memory.py` | Already created | `load()` / `save()` for `memory.json` |
| `backend/orchestrator/llm.py` | Modify | Prepend session history to messages; append turns after reply |
| `scripts/serve_test.py` | Modify | Load memory on startup; save after each `/voice` and `/text` call |
| `tests/test_memory.py` | Create | Unit tests for memory module and llm history wiring |

---

## Task 1: Commit the existing `backend/memory.py`

**Files:**
- Already exists: `backend/memory.py`

- [ ] **Step 1: Verify the file is correct**

`backend/memory.py` should contain exactly:

```python
import json
from pathlib import Path

_FILE = Path("memory.json")

def load() -> list[dict]:
    if not _FILE.exists():
        return []
    try:
        return json.loads(_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

def save(history: list[dict]) -> None:
    _FILE.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
```

- [ ] **Step 2: Write tests**

Create `tests/test_memory.py`:

```python
import json, tempfile, os
from pathlib import Path
import pytest

def test_load_returns_empty_when_no_file(tmp_path, monkeypatch):
    import backend.memory as mem
    monkeypatch.setattr(mem, "_FILE", tmp_path / "memory.json")
    assert mem.load() == []

def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    import backend.memory as mem
    monkeypatch.setattr(mem, "_FILE", tmp_path / "memory.json")
    history = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]
    mem.save(history)
    assert mem.load() == history

def test_load_returns_empty_on_corrupt_file(tmp_path, monkeypatch):
    import backend.memory as mem
    f = tmp_path / "memory.json"
    f.write_text("not valid json", encoding="utf-8")
    monkeypatch.setattr(mem, "_FILE", f)
    assert mem.load() == []
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/test_memory.py -v
```

Expected: 3 PASSED

- [ ] **Step 4: Commit**

```bash
git add backend/memory.py tests/test_memory.py
git commit -m "feat: add memory.py for persistent conversation history"
```

---

## Task 2: Wire history into `run_llm_turn`

**Files:**
- Modify: `backend/orchestrator/llm.py`

Currently `run_llm_turn` builds messages as:
```python
messages: list[dict[str, Any]] = [{"role": "user", "content": user_text}]
```

It needs to prepend the session history so Claude has prior context. After getting a reply, it should save the new turn to the session.

- [ ] **Step 1: Update `run_llm_turn` in `backend/orchestrator/llm.py`**

Change lines 30–31 (the `messages` initialization) and the `return` statement at line 77:

```python
def run_llm_turn(
    llm: LLMClient,
    bunq: BunqClient,
    store: SessionStore,
    sid: str,
    *,
    user_text: str,
    model: str = "claude-sonnet-4-5",
) -> dict[str, Any]:
    """Returns {'reply': str, 'tool_calls': [{name, input, result, is_error}]}."""
    session = store.get(sid)
    system = build_system_prompt(session)
    messages: list[dict[str, Any]] = list(session["history"]) + [
        {"role": "user", "content": user_text}
    ]
    tool_calls: list[dict[str, Any]] = []

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
                args = b.get("input", {})
                try:
                    result = dispatch(bunq, store, sid, b["name"], args)
                    content = _jsonable(result)
                    is_error = False
                except Exception as e:
                    result = f"Error: {type(e).__name__}: {e}"
                    content = result
                    is_error = True
                tool_calls.append({
                    "name": b["name"],
                    "input": args,
                    "result": result,
                    "is_error": is_error,
                })
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": b["id"],
                    "content": content if isinstance(content, str) else str(content),
                    "is_error": is_error,
                })
            messages.append({"role": "user", "content": tool_results})
            system = build_system_prompt(store.get(sid))
            continue

        texts = [b["text"] for b in blocks if b.get("type") == "text"]
        reply = " ".join(t.strip() for t in texts if t.strip())

        # Save this turn to session history
        store.append_history(sid, {"role": "user", "content": user_text})
        store.append_history(sid, {"role": "assistant", "content": reply})

        return {"reply": reply, "tool_calls": tool_calls}

    raise RuntimeError("LLM loop exceeded max iterations")
```

- [ ] **Step 2: Commit**

```bash
git add backend/orchestrator/llm.py
git commit -m "feat: prepend session history to LLM context and save turns"
```

---

## Task 3: Load memory on startup, save after each turn in `serve_test.py`

**Files:**
- Modify: `scripts/serve_test.py`

- [ ] **Step 1: Add import at the top of `scripts/serve_test.py`**

After the existing imports, add:

```python
from backend import memory
```

- [ ] **Step 2: Load memory after session creation**

Find the line:
```python
SHARED_SID = store.create(bunq_user_id=0, primary_account_id=bunq.primary_account_id())
```

Add immediately after it:
```python
for msg in memory.load():
    store.append_history(SHARED_SID, msg)
```

- [ ] **Step 3: Save memory after each `/voice` turn**

Find the `return` in the `/voice` endpoint:
```python
        return {
            "user_text": user_text,
            "reply_text": result["reply"],
            "tool_calls": result["tool_calls"],
            "pending": pending,
        }
```

Add `memory.save(store.get(SHARED_SID)["history"])` immediately before that return:
```python
        memory.save(store.get(SHARED_SID)["history"])
        return {
            "user_text": user_text,
            "reply_text": result["reply"],
            "tool_calls": result["tool_calls"],
            "pending": pending,
        }
```

- [ ] **Step 4: Save memory after each `/text` turn**

Same change in the `/text` endpoint — add before its return:
```python
        memory.save(store.get(SHARED_SID)["history"])
        return {
            "user_text": message,
            "reply_text": result["reply"],
            "tool_calls": result["tool_calls"],
            "pending": pending,
        }
```

- [ ] **Step 5: Commit**

```bash
git add scripts/serve_test.py
git commit -m "feat: load memory on startup and persist history after each turn"
```

---

## How It Works (Summary)

1. Server starts → reads `memory.json` → loads past messages into the session `history` list
2. User speaks → `run_llm_turn` sends `[...history, new user message]` to Claude → Claude has full context
3. Claude replies → the new user+assistant pair is appended to `session["history"]`
4. Server writes updated `history` to `memory.json`
5. Next restart → repeat from step 1

The session history is capped at 20 entries (`store.append_history` enforces this), so the context window never overflows. `memory.json` on disk always reflects the last 20 messages.
