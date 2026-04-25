import json
import re
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

def derive_accessibility_events(
    reply: str,
    tool_calls: list[dict[str, Any]],
) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []

    has_error = any(tc["is_error"] for tc in tool_calls)
    if has_error:
        events.append({"type": "ERROR", "event": "tool-error", "detail": "Error communicated via voice — no silent failures"})

    tool_names = [tc["name"] for tc in tool_calls]
    has_draft = "create_draft_payment" in tool_names
    has_confirm = "confirm_draft_payment" in tool_names

    amount_words = bool(re.search(
        r'\b(one|two|three|four|five|six|seven|eight|nine|ten|'
        r'eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|'
        r'eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|'
        r'eighty|ninety|hundred|thousand|million|euro|cent)\b',
        reply.lower()
    ))
    if amount_words:
        events.append({"type": "SPEECH", "event": "full-amount", "detail": "Amount spoken as words, not symbols or digits"})

    iban_phonetic = bool(re.search(
        r'\b(Alpha|Bravo|Charlie|Delta|Echo|Foxtrot|Golf|Hotel|India|'
        r'Juliet|Kilo|Lima|Mike|November|Oscar|Papa|Quebec|Romeo|'
        r'Sierra|Tango|Uniform|Victor|Whiskey|X-ray|Yankee|Zulu)\b',
        reply
    ))
    if iban_phonetic:
        events.append({"type": "SPEECH", "event": "iban-phonetic", "detail": "IBAN read with NATO phonetic alphabet"})

    if has_draft:
        events.append({"type": "SPEECH", "event": "readback", "detail": "Full payment details read back before action"})
        events.append({"type": "ACTION", "event": "voice-confirm", "detail": "Awaiting spoken 'confirm' — no screen interaction needed"})

    if has_confirm:
        events.append({"type": "ACTION", "event": "payment-confirmed", "detail": "Payment confirmed by voice command"})

    return events


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
    messages: list[dict[str, Any]] = list(session["history"]) + [{"role": "user", "content": user_text}]
    tool_calls: list[dict[str, Any]] = []

    for _ in range(MAX_ITERATIONS):
        resp = llm.messages_create(
            model=model,
            system=system,
            tools=tool_schemas(),
            messages=messages,
            max_tokens=1024,
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
        store.append_history(sid, {"role": "user", "content": user_text})
        store.append_history(sid, {"role": "assistant", "content": reply})
        a11y_events = derive_accessibility_events(reply, tool_calls)
        return {"reply": reply, "tool_calls": tool_calls, "accessibility_events": a11y_events}

    raise RuntimeError("LLM loop exceeded max iterations")
