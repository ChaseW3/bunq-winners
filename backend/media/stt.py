import io
from typing import Protocol

class STT(Protocol):
    def transcribe(self, audio: bytes, *, language: str = "en") -> str: ...

class WhisperSTT:
    def __init__(self, openai_client) -> None:
        self._client = openai_client

    def transcribe(self, audio: bytes, *, language: str = "en") -> str:
        f = io.BytesIO(audio)
        f.name = "input.webm"
        resp = self._client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            language=language,
        )
        return resp.text
