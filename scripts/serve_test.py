"""
Dev server for bunq Voice: STT + LLM + bunq tool calling.

Usage:
    uv run python scripts/serve_test.py
Then open http://localhost:8000 in Chrome.
"""
import io, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import uvicorn
from openai import OpenAI
from anthropic import Anthropic

from backend import memory
from backend.session.store import SessionStore
from backend.orchestrator.anthropic_adapter import AnthropicAdapter
from backend.orchestrator.llm import run_llm_turn

# --- bootstrap ---
# Set BUNQ_FAKE=1 in the environment to run against FakeBunqClient (no bunq key needed).
USE_FAKE = os.environ.get("BUNQ_FAKE", "").lower() in {"1", "true", "yes"}
if USE_FAKE:
    from backend.tests.fakes import FakeBunqClient
    bunq = FakeBunqClient()
    print("[serve_test] Using FakeBunqClient (BUNQ_FAKE=1).")
else:
    from backend.bunq_client.bootstrap import ensure_context
    from backend.bunq_client.client import RealBunqClient
    ensure_context(os.environ["BUNQ_API_KEY"], os.environ.get("BUNQ_ENVIRONMENT", "SANDBOX"))
    bunq = RealBunqClient()
store = SessionStore()
openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
anthropic_client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
llm = AnthropicAdapter(anthropic_client)
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-4-5")

# Single shared session for the dev server
SHARED_SID = store.create(bunq_user_id=0, primary_account_id=bunq.primary_account_id())
for msg in memory.load():
    store.append_history(SHARED_SID, msg)

# --- app ---
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/config")
async def config():
    return {"elevenlabs_api_key": os.environ.get("ELEVENLABS_API_KEY", "")}

@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    try:
        data = await audio.read()
        buf = io.BytesIO(data)
        buf.name = audio.filename or "recording.webm"
        resp = openai_client.audio.transcriptions.create(model="whisper-1", file=buf)
        return {"text": resp.text}
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})

@app.post("/voice")
async def voice(audio: UploadFile = File(...)):
    """Full pipeline: audio → STT → LLM (with bunq tools) → text reply."""
    try:
        data = await audio.read()
        buf = io.BytesIO(data)
        buf.name = audio.filename or "recording.webm"

        # 1. Transcribe
        stt_resp = openai_client.audio.transcriptions.create(model="whisper-1", file=buf)
        user_text = stt_resp.text

        if not user_text.strip():
            return {"user_text": "", "reply_text": "I didn't catch that. Try again.", "pending": None, "tool_calls": []}

        # 2. LLM with tools
        result = run_llm_turn(llm, bunq, store, SHARED_SID, user_text=user_text, model=LLM_MODEL)

        pending = store.get(SHARED_SID)["pending_draft"]
        memory.save(store.get(SHARED_SID)["history"])
        return {
            "user_text": user_text,
            "reply_text": result["reply"],
            "tool_calls": result["tool_calls"],
            "accessibility_events": result.get("accessibility_events", []),
            "pending": pending,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": f"{type(e).__name__}: {e}"})

@app.post("/text")
async def text(message: str = Form(...)):
    """Text-only entry point for fast iteration without recording."""
    try:
        result = run_llm_turn(llm, bunq, store, SHARED_SID, user_text=message, model=LLM_MODEL)
        pending = store.get(SHARED_SID)["pending_draft"]
        memory.save(store.get(SHARED_SID)["history"])
        return {
            "user_text": message,
            "reply_text": result["reply"],
            "tool_calls": result["tool_calls"],
            "accessibility_events": result.get("accessibility_events", []),
            "pending": pending,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": f"{type(e).__name__}: {e}"})

app.mount("/", StaticFiles(directory="frontend", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
