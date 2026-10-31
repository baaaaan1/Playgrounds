from __future__ import annotations

import json

from .base import ProviderInfo


class OpenAICompatProvider:
    """Provider for any OpenAI-compatible chat completions endpoint."""

    def __init__(self, info: ProviderInfo) -> None:
        self.info = info

    def endpoint(self, base_url: str | None = None) -> str:
        root = (base_url or self.info.base_url).rstrip("/")
        if root.endswith("/chat/completions"):
            return root
        return f"{root}/chat/completions"

    def headers(self, api_key: str | None) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def payload(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        system_prompt: str = "",
    ) -> dict[str, object]:
        payload_messages: list[dict[str, str]] = []
        if system_prompt.strip():
            payload_messages.append({"role": "system", "content": system_prompt.strip()})
        payload_messages.extend(messages)
        payload: dict[str, object] = {
            "model": model,
            "messages": payload_messages,
            "stream": True,
            "temperature": temperature,
        }
        if max_tokens > 0:
            payload["max_tokens"] = max_tokens
        return payload

    def parse_delta(self, data: str) -> str | None:
        try:
            event = json.loads(data)
        except ValueError:
            return None
        choices = event.get("choices")
        if not isinstance(choices, list) or not choices:
            return None
        first = choices[0]
        if not isinstance(first, dict):
            return None
        delta = first.get("delta")
        if not isinstance(delta, dict):
            return None
        content = delta.get("content")
        if isinstance(content, str):
            return content or None
        if isinstance(content, list):
            parts = [
                part.get("text", "")
                for part in content
                if isinstance(part, dict)
            ]
            joined = "".join(parts)
            return joined or None
        return None
