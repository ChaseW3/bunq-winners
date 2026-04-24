import pytest
from backend.config import load, Config

def test_load_reads_required_env(monkeypatch):
    monkeypatch.setenv("BUNQ_API_KEY", "k1")
    monkeypatch.setenv("BUNQ_ENVIRONMENT", "SANDBOX")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k2")
    monkeypatch.setenv("OPENAI_API_KEY", "k3")
    cfg = load()
    assert isinstance(cfg, Config)
    assert cfg.bunq_api_key == "k1"
    assert cfg.llm_model == "claude-sonnet-4-6"  # default

def test_load_raises_when_missing(monkeypatch):
    monkeypatch.delenv("BUNQ_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="BUNQ_API_KEY"):
        load()
