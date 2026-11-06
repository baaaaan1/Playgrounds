from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from math import isfinite
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
class ResponseStatistics:
    duration_seconds: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    input_rate: float | None = None
    output_rate: float | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ResponseStatistics:
        values = {}
        for key in cls.__dataclass_fields__:
            value = raw.get(key)
            if type(value) not in {int, float} or not isfinite(value) or value < 0:
                continue
            if key.endswith("_tokens") and type(value) is not int:
                continue
            values[key] = value
        return cls(**values)

    def tokens_per_second(self, ttft: float | None) -> float | None:
        if self.output_tokens is None or self.duration_seconds is None or ttft is None:
            return None
        generation_seconds = self.duration_seconds - ttft
        return self.output_tokens / generation_seconds if generation_seconds > 0 else None

    @property
    def estimated_cost(self) -> float | None:
        # Rates are USD per million tokens; missing data must not look like free usage.
        if any(value is None for value in (
            self.input_tokens, self.output_tokens, self.input_rate, self.output_rate,
        )):
            return None
        return (self.input_tokens * self.input_rate + self.output_tokens * self.output_rate) / 1_000_000


@dataclass
class Message:
    role: str
    content: str
    ts: float = field(default_factory=time.time)
    thinking_seconds: float | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: str = "complete"
    statistics: ResponseStatistics | None = None

    def to_dict(self) -> dict[str, Any]:
        raw = {
            "id": self.id, "role": self.role, "content": self.content,
            "ts": self.ts, "status": self.status,
        }
        if self.thinking_seconds is not None:
            raw["thinking_seconds"] = self.thinking_seconds
        if self.statistics is not None:
            raw["statistics"] = asdict(self.statistics)
        return raw

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Message:
        return cls(
            id=str(raw.get("id") or uuid.uuid4().hex),
            role=str(raw.get("role", "user")),
            content=str(raw.get("content", "")),
            ts=float(raw.get("ts", time.time())),
            thinking_seconds=(
                float(raw["thinking_seconds"]) if raw.get("thinking_seconds") is not None else None
            ),
            status=str(raw.get("status", "complete")),
            statistics=(
                ResponseStatistics.from_dict(raw["statistics"])
                if isinstance(raw.get("statistics"), dict) else None
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
    pinned: bool = False
    archived: bool = False
    title_is_custom: bool = False
    draft_text: str = ""
    draft_updated_at: float = 0.0
    last_attempt: dict[str, Any] = field(default_factory=dict)
    forked_from_conversation_id: str = ""
    forked_from_message_id: str = ""

    @property
    def is_empty(self) -> bool:
        return not self.messages

    def add(self, message: Message) -> None:
        self.messages.append(message)
        self.updated_at = time.time()
        if not self.title_is_custom and message.role == "user" and (not self.title or self.title == "New chat"):
            self.title = _derive_title(message.content)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "id": self.id,
            "title": self.title,
            "provider": self.provider,
            "model": self.model,
            "profile_id": self.profile_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "messages": [m.to_dict() for m in self.messages],
            "pinned": self.pinned,
            "archived": self.archived,
            "title_is_custom": self.title_is_custom,
            "draft_text": self.draft_text,
            "draft_updated_at": self.draft_updated_at,
            "last_attempt": dict(self.last_attempt),
            "forked_from_conversation_id": self.forked_from_conversation_id,
            "forked_from_message_id": self.forked_from_message_id,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Conversation:
        conversation_id = str(raw.get("id") or uuid.uuid4().hex[:12])
        # Legacy files need stable identities even before their first upgraded save.
        messages = [
            Message.from_dict({
                **item,
                "id": item.get("id") or uuid.uuid5(
                    uuid.NAMESPACE_URL, f"playgrounds:{conversation_id}:{index}"
                ).hex,
            })
            for index, item in enumerate(raw.get("messages", []))
        ]
        return cls(
            id=conversation_id,
            title=str(raw.get("title", "New chat")),
            provider=str(raw.get("provider", "openai")),
            model=str(raw.get("model", "")),
            profile_id=str(raw.get("profile_id", "")),
            messages=messages,
            created_at=float(raw.get("created_at", time.time())),
            updated_at=float(raw.get("updated_at", time.time())),
            pinned=bool(raw.get("pinned", False)),
            archived=bool(raw.get("archived", False)),
            title_is_custom=bool(raw.get("title_is_custom", False)),
            draft_text=str(raw.get("draft_text", "")),
            draft_updated_at=float(raw.get("draft_updated_at", 0.0)),
            last_attempt=dict(raw.get("last_attempt") or {}),
            forked_from_conversation_id=str(raw.get("forked_from_conversation_id", "")),
            forked_from_message_id=str(raw.get("forked_from_message_id", "")),
        )
