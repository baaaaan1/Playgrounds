from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

_TITLE_LIMIT = 48


def _derive_title(text: str) -> str:
    clean = " ".join(text.split())
    if not clean:
        return "New chat"
    if len(clean) <= _TITLE_LIMIT:
        return clean
    return clean[: _TITLE_LIMIT - 1].rstrip() + "\u2026"


@dataclass
class Message:
    role: str
    content: str
    ts: float = field(default_factory=time.time)
    thinking_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        raw = {"role": self.role, "content": self.content, "ts": self.ts}
        if self.thinking_seconds is not None:
            raw["thinking_seconds"] = self.thinking_seconds
        return raw

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Message:
        return cls(
            role=str(raw.get("role", "user")),
            content=str(raw.get("content", "")),
            ts=float(raw.get("ts", time.time())),
            thinking_seconds=(
                float(raw["thinking_seconds"]) if raw.get("thinking_seconds") is not None else None
            ),
        )


@dataclass
class Conversation:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = "New chat"
    provider: str = "openai"
    model: str = ""
    messages: list[Message] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    profile_id: str = ""

    @property
    def is_empty(self) -> bool:
        return not self.messages

    def add(self, message: Message) -> None:
        self.messages.append(message)
        self.updated_at = time.time()
        if message.role == "user" and (not self.title or self.title == "New chat"):
            self.title = _derive_title(message.content)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "provider": self.provider,
            "model": self.model,
            "profile_id": self.profile_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "messages": [m.to_dict() for m in self.messages],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Conversation:
        messages = [Message.from_dict(item) for item in raw.get("messages", [])]
        return cls(
            id=str(raw.get("id") or uuid.uuid4().hex[:12]),
            title=str(raw.get("title", "New chat")),
            provider=str(raw.get("provider", "openai")),
            model=str(raw.get("model", "")),
            profile_id=str(raw.get("profile_id", "")),
            messages=messages,
            created_at=float(raw.get("created_at", time.time())),
            updated_at=float(raw.get("updated_at", time.time())),
        )
