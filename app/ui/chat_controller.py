from __future__ import annotations

import logging
from time import monotonic

from PyQt6.QtCore import QObject, pyqtSignal

from ..core.config import Config
from ..core.credentials import CredentialStore
from ..core.models import Conversation, Message
from ..core.profiles import endpoint_url
from ..core.providers.registry import get_provider
from ..core.store import ConversationStore
from ..net.client import StreamClient

log = logging.getLogger(__name__)


class ChatController(QObject):
    message_added = pyqtSignal(object)
    stream_started = pyqtSignal()
    thinking_finished = pyqtSignal(float)
    stream_delta = pyqtSignal(str)
    stream_finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(
        self,
        config: Config,
        store: ConversationStore,
        credentials: CredentialStore,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._store = store
        self._credentials = credentials
        self._client = StreamClient(self)
        self._conversation: Conversation | None = None
        self._buffer = ""
        self._busy = False
        self._thinking_started: float | None = None
        self._thinking_seconds: float | None = None

        self._client.delta.connect(self._on_delta)
        self._client.completed.connect(self._on_completed)
        self._client.failed.connect(self._on_failed)

    @property
    def conversation(self) -> Conversation | None:
        return self._conversation

    @property
    def busy(self) -> bool:
        return self._busy

    def new_conversation(self) -> Conversation:
        profile = self._config.active_profile()
        self._conversation = Conversation(
            provider=profile.preset, model=profile.model, profile_id=profile.id
        )
        return self._conversation

    def open(self, conversation_id: str) -> bool:
        conversation = self._store.load(conversation_id)
        if conversation is None:
            return False
        self._conversation = conversation
        return True

    def use(self, conversation: Conversation) -> None:
        self._conversation = conversation

    def send(self, text: str) -> None:
        text = text.strip()
        if not text or self._busy:
            return

        profile = self._config.active_profile()
        provider = get_provider(profile.preset)
        model = profile.model
        api_key = self._credentials.get_secret(profile.credential_name)
        try:
            url = endpoint_url(profile.base_url, "chat/completions")
        except ValueError as exc:
            self.error.emit(str(exc))
            return
        if not model:
            self.error.emit("Model belum dipilih. Buka Settings untuk memilih model.")
            return

        if self._conversation is None:
            self.new_conversation()
        conversation = self._conversation
        assert conversation is not None
        conversation.provider = profile.preset
        conversation.model = model
        conversation.profile_id = profile.id

        user_message = Message(role="user", content=text)
        conversation.add(user_message)
        try:
            self._store.save(conversation)
        except OSError:
            log.exception("Failed to save conversation")
        self.message_added.emit(user_message)

        history = [
            {"role": message.role, "content": message.content}
            for message in conversation.messages
            if message.role in {"user", "assistant"} and message.content
        ]
        payload = provider.payload(
            model=model,
            messages=history,
            temperature=profile.temperature,
            max_tokens=profile.max_tokens,
            system_prompt=profile.system_prompt,
        )

        self._buffer = ""
        self._busy = True
        self._thinking_started = monotonic()
        self._thinking_seconds = None
        self.stream_started.emit()
        self._client.start(
            url,
            provider.headers(api_key),
            payload,
            provider,
        )

    def stop(self) -> None:
        if not self._busy:
            return
        self._client.abort()
        self._finish()

    def delete(self, conversation_id: str) -> None:
        if self._conversation is not None and self._conversation.id == conversation_id:
            self._conversation = None
        self._store.delete(conversation_id)

    def shutdown(self) -> None:
        if self._busy:
            self._client.abort()
            self._busy = False
            self._thinking_started = None
            self._thinking_seconds = None

    def _on_delta(self, delta: str) -> None:
        if not self._busy or not delta:
            return
        if self._thinking_seconds is None and self._thinking_started is not None:
            self._thinking_seconds = max(0.0, monotonic() - self._thinking_started)
            self.thinking_finished.emit(self._thinking_seconds)
        self._buffer += delta
        self.stream_delta.emit(delta)

    def _on_completed(self) -> None:
        self._finish()

    def _on_failed(self, message: str) -> None:
        self._finish()
        self.error.emit(message)

    def _finish(self) -> None:
        if not self._busy:
            return
        self._busy = False
        text = self._buffer.rstrip()
        self._buffer = ""
        message: Message | None = None
        conversation = self._conversation
        if text and conversation is not None:
            message = Message(
                role="assistant", content=text, thinking_seconds=self._thinking_seconds
            )
            conversation.add(message)
            try:
                self._store.save(conversation)
            except OSError:
                log.exception("Failed to save conversation")
        self._thinking_started = None
        self._thinking_seconds = None
        self.stream_finished.emit(message)
