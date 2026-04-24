"""
Test WhisperSTT with a local audio file.

Usage:
    uv run python scripts/test_stt.py fixtures/audio/balance_query.wav
    uv run python scripts/test_stt.py path/to/any_audio.mp3
"""
import sys
from dotenv import load_dotenv
import os

load_dotenv()

from openai import OpenAI
from backend.media.stt import WhisperSTT

path = sys.argv[1] if len(sys.argv) > 1 else None
if not path:
    print("Usage: uv run python scripts/test_stt.py <audio_file>")
    sys.exit(1)

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
stt = WhisperSTT(client)

with open(path, "rb") as f:
    audio = f.read()

# Whisper needs the filename to detect format — patch the BytesIO name
import io
buf = io.BytesIO(audio)
buf.name = path.split("/")[-1]

resp = client.audio.transcriptions.create(model="whisper-1", file=buf)
print("Transcription:", resp.text)
