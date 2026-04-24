from typing import Any

class AnthropicAdapter:
    def __init__(self, client) -> None:
        self._client = client

    def messages_create(self, **kwargs: Any) -> dict[str, Any]:
        resp = self._client.messages.create(**kwargs)
        return {
            "stop_reason": resp.stop_reason,
            "content": [self._block_to_dict(b) for b in resp.content],
        }

    @staticmethod
    def _block_to_dict(b: Any) -> dict[str, Any]:
        t = b.type
        if t == "text":
            return {"type": "text", "text": b.text}
        if t == "tool_use":
            return {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
        return {"type": t}
