import os
from dataclasses import dataclass
from dotenv import load_dotenv

@dataclass(frozen=True)
class Config:
    bunq_api_key: str
    bunq_environment: str
    anthropic_api_key: str
    openai_api_key: str
    llm_model: str
    tts_voice: str

REQUIRED = ["BUNQ_API_KEY", "BUNQ_ENVIRONMENT", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"]

def load() -> Config:
    load_dotenv()
    missing = [k for k in REQUIRED if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")
    return Config(
        bunq_api_key=os.environ["BUNQ_API_KEY"],
        bunq_environment=os.environ["BUNQ_ENVIRONMENT"],
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ["OPENAI_API_KEY"],
        llm_model=os.environ.get("LLM_MODEL", "claude-sonnet-4-6"),
        tts_voice=os.environ.get("TTS_VOICE", "alloy"),
    )
