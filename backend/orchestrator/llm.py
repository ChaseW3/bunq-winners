import json
from typing import Any, Protocol
from backend.bunq_client import BunqClient
from backend.session.store import SessionStore
from backend.tools.registry import tool_schemas, dispatch
from backend.orchestrator.prompts import build_system_prompt

MAX_ITERATIONS = 6

class LLMClient(Protocol):
    def messages_create(self, **kwargs: Any) -> dict[str, Any]: ...

def _jsonable(v: Any) -> str:
    try:
        return json.dumps(v, default=str)
    except Exception:
        return str(v)

def run_llm_turn(
    llm: LLMClient,
    bunq: BunqClient,
    store: SessionStore,
    sid: str,
    *,
    user_text: str,
    model: str = "claude-sonnet-4-5",
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
                except Exception as e:
                    content = f"Error: {type(e).__name__}: {e}"
                    is_error = True
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
        return " ".join(t.strip() for t in texts if t.strip())

    raise RuntimeError("LLM loop exceeded max iterations")
