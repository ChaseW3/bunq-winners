"""
Minimal FastAPI server for testing STT via the browser test page.

Usage:
    uv run python scripts/serve_test.py
Then open frontend/test_stt.html in Chrome (via Live Server or file://).
"""
import io, os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import uvicorn
from openai import OpenAI

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    try:
        data = await audio.read()
        buf = io.BytesIO(data)
        buf.name = audio.filename or "recording.webm"
        resp = client.audio.transcriptions.create(model="whisper-1", file=buf)
        return {"text": resp.text}
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})

app.mount("/", StaticFiles(directory="frontend", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
