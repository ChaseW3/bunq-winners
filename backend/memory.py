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
