from __future__ import annotations

import logging

from PyQt6.QtCore import QObject, pyqtSignal

from ..core.config import Config
from ..core.credentials import CredentialStore
from ..core.models import Conversation, Message
from ..core.providers.registry import get_provider, provider_info
from ..core.store import ConversationStore
from ..net.client import StreamClient

log = logging.getLogger(__name__)


class ChatController(QObject):
    message_added = pyqtSignal(object)
    stream_started = pyqtSignal()
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
        provider_id = str(self._config.get("provider", "openai"))
        info = provider_info(provider_id)
        model = self._config.model_for(provider_id) or info.default_model
        self._conversation = Conversation(provider=provider_id, model=model)
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

        provider_id = str(self._config.get("provider", "openai"))
        info = provider_info(provider_id)
        provider = get_provider(provider_id)
        model = self._config.model_for(provider_id) or info.default_model
        base_url = self._config.base_url_for(provider_id) or info.base_url
        api_key = self._credentials.get_secret(provider_id)

        if not base_url and provider_id == "custom":
            self.error.emit("Base URL belum diatur. Buka Settings untuk mengisinya.")
            return
        if info.requires_key and not api_key:
            self.error.emit(
                f"API key {info.label} belum diatur. Buka Settings untuk mengisinya."
            )
            return
        if not model:
            self.error.emit("Model belum dipilih. Buka Settings untuk memilih model.")
            return

        if self._conversation is None:
            self.new_conversation()
        conversation = self._conversation
        assert conversation is not None
        conversation.provider = provider_id
        conversation.model = model

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
            temperature=float(self._config.get("temperature", 0.7)),
            max_tokens=int(self._config.get("max_tokens", 2048)),
            system_prompt=str(self._config.get("system_prompt", "")),
        )

        self._buffer = ""
        self._busy = True
        self._client.start(
            provider.endpoint(base_url),
            provider.headers(api_key),
            payload,
            provider,
        )
        self.stream_started.emit()

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

    def _on_delta(self, delta: str) -> None:
        if not self._busy:
            return
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
            message = Message(role="assistant", content=text)
            conversation.add(message)
            try:
                self._store.save(conversation)
            except OSError:
                log.exception("Failed to save conversation")
        self.stream_finished.emit(message)
