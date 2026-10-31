from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from .models import Conversation


def default_data_dir() -> Path:
    """Return the per-user application data directory."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "Playgrounds"
    return Path.home() / ".playgrounds"


class ConversationStore:
    """JSON-per-conversation persistence with atomic writes."""

    def __init__(self, root: Path | None = None) -> None:
        explicit = root is not None
        self.root = Path(root) if explicit else default_data_dir() / "conversations"
        self.root.mkdir(parents=True, exist_ok=True)
        if not explicit:
            self._migrate_legacy()

    def _migrate_legacy(self) -> None:
        legacy = default_data_dir() / "Playgrounds" / "conversations"
        if not legacy.is_dir() or legacy == self.root:
            return
        for path in legacy.glob("*.json"):
            target = self.root / path.name
            if target.exists():
                continue
            try:
                shutil.copy2(path, target)
            except OSError:
                continue

    def _path(self, conversation_id: str) -> Path:
        return self.root / f"{conversation_id}.json"

    def save(self, conversation: Conversation) -> None:
        path = self._path(conversation.id)
        payload: dict[str, Any] = conversation.to_dict()
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def load(self, conversation_id: str) -> Conversation | None:
        path = self._path(conversation_id)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return Conversation.from_dict(raw)

    def delete(self, conversation_id: str) -> None:
        try:
            self._path(conversation_id).unlink()
        except FileNotFoundError:
            return

    def list(self) -> list[Conversation]:
        conversations: list[Conversation] = []
        for path in self.root.glob("*.json"):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            conversations.append(Conversation.from_dict(raw))
        conversations.sort(key=lambda c: c.updated_at, reverse=True)
        return conversations
