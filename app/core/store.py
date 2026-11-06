from __future__ import annotations

import json
import os
import shutil
import tempfile
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
        tmp: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.root, suffix=".tmp", delete=False,
            ) as stream:
                tmp = Path(stream.name)
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, path)
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)

    def load(self, conversation_id: str) -> Conversation | None:
        path = self._path(conversation_id)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return Conversation.from_dict(raw)
        except (OSError, ValueError, TypeError, AttributeError, OverflowError):
            return None

    def delete(self, conversation_id: str) -> None:
        try:
            self._path(conversation_id).unlink()
        except FileNotFoundError:
            return

    def list(self) -> list[Conversation]:
        conversations: list[Conversation] = []
        for path in self.root.glob("*.json"):
            conversation = self.load(path.stem)
            if conversation is not None:
                conversations.append(conversation)
        conversations.sort(key=lambda c: c.updated_at, reverse=True)
        return conversations
