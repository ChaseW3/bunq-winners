"""
REPL: real Claude + FakeBunqClient.

Drives the orchestrator loop against the in-memory fake so you can iterate on
prompt quality and tool selection without hitting the bunq sandbox.

Usage:
    uv run python scripts/repl_fake.py
    > what did I spend this week?
    > how's my savings?
    > send 20 euros to Finn for pizza
    > yes
    > :quit
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from anthropic import Anthropic

from backend.orchestrator.anthropic_adapter import AnthropicAdapter
from backend.orchestrator.llm import run_llm_turn
from backend.session.store import SessionStore
from backend.tests.fakes import FakeBunqClient


def _short(v, n=120):
    s = json.dumps(v, default=str)
    return s if len(s) <= n else s[:n] + "…"


def main() -> None:
    if "ANTHROPIC_API_KEY" not in os.environ:
        sys.exit("ANTHROPIC_API_KEY not set")

    llm = AnthropicAdapter(Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"]))
    model = os.environ.get("LLM_MODEL", "claude-sonnet-4-5")
    client = FakeBunqClient()
    store = SessionStore()
    sid = store.create(bunq_user_id=0, primary_account_id=client.primary_account_id())

    print(f"bunq Voice REPL (fake data, model={model}). Type :quit to exit.\n")
    while True:
        try:
            user_text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not user_text:
            continue
        if user_text in {":q", ":quit", ":exit"}:
            return
        if user_text == ":state":
            print(json.dumps(store.get(sid), default=str, indent=2))
            continue

        try:
            out = run_llm_turn(llm, client, store, sid, user_text=user_text, model=model)
        except Exception as e:
            print(f"  ! {type(e).__name__}: {e}")
            continue

        for tc in out["tool_calls"]:
            marker = "✗" if tc["is_error"] else "→"
            print(f"  {marker} {tc['name']}({_short(tc['input'])}) = {_short(tc['result'])}")
        print(f"bot> {out['reply']}\n")


if __name__ == "__main__":
    main()
