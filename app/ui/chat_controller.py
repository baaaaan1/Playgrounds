from __future__ import annotations

import logging
import re
import time
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from time import monotonic

from PyQt6.QtCore import QObject, pyqtSignal

from ..core.config import Config
from ..core.credentials import CredentialStore
from ..core.models import Conversation, Message, ResponseStatistics
from ..core.profiles import endpoint_url
from ..core.providers.registry import get_provider
from ..core.store import ConversationStore
from ..net.client import StreamClient

log = logging.getLogger(__name__)


@dataclass
class Generation:
    id: str
    conversation: Conversation
    user_message_id: str
    replaces_message_id: str = ""
    statistics: ResponseStatistics = field(default_factory=ResponseStatistics)


class ChatController(QObject):
    conversation_changed = pyqtSignal(object)
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
        self._operation: Generation | None = None
        self._callbacks: tuple | None = None
        self._usage_callback = None
        self._selected_connection: str | None = None
        self._unsaved: dict[str, Conversation] = {}

    @property
    def conversation(self) -> Conversation | None:
        return self._conversation

    @property
    def busy(self) -> bool:
        return self._busy

    def new_conversation(self) -> Conversation:
        self.stop()
        profile = self._config.active_profile()
        self._conversation = Conversation(
            provider=profile.preset, model=profile.model, profile_id=profile.id
        )
        self._selected_connection = None
        return self._conversation

    def open(self, conversation_id: str) -> bool:
        if self._conversation is not None and self._conversation.id == conversation_id:
            return True
        self.stop()
        conversation = self._unsaved.get(conversation_id) or self._store.load(conversation_id)
        if conversation is None:
            return False
        if conversation.last_attempt.get("status") == "pending":
            conversation.last_attempt["status"] = "interrupted"
            self._persist(conversation)
        self._conversation = conversation
        self._selected_connection = None
        return True

    def use(self, conversation: Conversation) -> None:
        self.stop()
        self._conversation = conversation
        self._selected_connection = None

    def select_connection(self, profile_id: str) -> None:
        if not self._busy:
            self._config.select_profile(profile_id)
            self._selected_connection = profile_id

    def _persist(self, conversation: Conversation) -> bool:
        try:
            self._store.save(conversation)
        except OSError:
            log.exception("Failed to save conversation")
            self._unsaved[conversation.id] = conversation
            self.error.emit(self.tr("Could not save this chat. Your changes are kept in memory. Try again before closing."))
            return False
        self._unsaved.pop(conversation.id, None)
        return True

    def flush(self) -> bool:
        saved = True
        for conversation in list(self._unsaved.values()):
            if not self._persist(conversation):
                saved = False
        return saved

    def set_draft(self, conversation_id: str, text: str) -> bool:
        conversation = self._conversation
        if conversation is None or conversation.id != conversation_id:
            conversation = self._unsaved.get(conversation_id) or self._store.load(conversation_id)
        if conversation is None:
            return False
        conversation.draft_text = text
        conversation.draft_updated_at = time.time()
        return self._persist(conversation)

    def send(self, text: str) -> bool:
        text = text.strip()
        if not text or self._busy:
            return False
        conversation = deepcopy(self._conversation) if self._conversation is not None else Conversation()
        user_message = Message(role="user", content=text)
        conversation.add(user_message)
        conversation.draft_text = ""
        conversation.draft_updated_at = time.time()
        return self._start(conversation, len(conversation.messages) - 1, "send")

    def retry(self, user_message_id: str) -> bool:
        conversation = self._conversation
        if self._busy or conversation is None:
            return False
        user_index = next((i for i in range(len(conversation.messages) - 1, -1, -1)
                           if conversation.messages[i].role == "user"), -1)
        if user_index < 0 or conversation.messages[user_index].id != user_message_id:
            return False
        following = conversation.messages[user_index + 1:]
        if len(following) > 1 or any(m.role != "assistant" for m in following):
            return False
        attempt = conversation.last_attempt
        failed_attempt = attempt.get("user_message_id") == user_message_id and attempt.get("status") in {
            "failed", "stopped", "interrupted",
        }
        if following and following[0].status == "complete" and not failed_attempt:
            return False
        replacement = following[0].id if following else ""
        return self._start(deepcopy(conversation), user_index, "retry", replacement)

    def regenerate(self, assistant_message_id: str) -> bool:
        conversation = self._conversation
        if self._busy or conversation is None or len(conversation.messages) < 2:
            return False
        answer = conversation.messages[-1]
        if answer.id != assistant_message_id or answer.role != "assistant":
            return False
        user_index = len(conversation.messages) - 2
        if conversation.messages[user_index].role != "user":
            return False
        return self._start(deepcopy(conversation), user_index, "regenerate", answer.id)

    def edit_and_fork(self, user_message_id: str, text: str) -> bool:
        source = self._conversation
        text = text.strip()
        if self._busy or source is None or not text:
            return False
        index = next((i for i, m in enumerate(source.messages)
                      if m.id == user_message_id and m.role == "user"), -1)
        if index < 0:
            return False
        messages = deepcopy(source.messages[:index])
        for message in messages:
            message.id = uuid.uuid4().hex
        conversation = Conversation(
            title=self.tr("{title} (edited)").format(title=source.title),
            title_is_custom=True,
            provider=source.provider, model=source.model, profile_id=source.profile_id,
            messages=messages, forked_from_conversation_id=source.id,
            forked_from_message_id=user_message_id,
        )
        conversation.add(Message("user", text))
        return self._start(conversation, len(conversation.messages) - 1, "edit")

    def _start(
        self, conversation: Conversation, user_index: int, kind: str,
        replacement_id: str = "",
    ) -> bool:
        profile = self._config.active_profile()
        current = self._conversation
        if current is not None and current.profile_id and not any(
            p.id == current.profile_id for p in self._config.profiles()
        ) and self._selected_connection != profile.id:
            self.error.emit(self.tr("This chat's connection no longer exists. Select a connection before sending."))
            return False
        provider = get_provider(profile.preset)
        model = profile.model
        api_key = self._credentials.get_secret(profile.credential_name)
        try:
            url = endpoint_url(profile.base_url, "chat/completions")
        except ValueError as exc:
            self.error.emit(str(exc))
            return False
        if not model:
            self.error.emit(self.tr("No model selected. Open Settings to choose a model."))
            return False
        conversation.provider = profile.preset
        conversation.model = model
        conversation.profile_id = profile.id

        history = [
            {"role": message.role, "content": message.content}
            for message in conversation.messages[:user_index + 1]
            if message.role in {"user", "assistant"} and message.content
        ]
        payload = provider.payload(
            model=model,
            messages=history,
            temperature=profile.temperature,
            max_tokens=profile.max_tokens,
            system_prompt=profile.system_prompt,
        )
        if profile.include_usage:
            payload["stream_options"] = {"include_usage": True}

        operation_id = uuid.uuid4().hex
        conversation.last_attempt = {
            "operation_id": operation_id, "kind": kind,
            "user_message_id": conversation.messages[user_index].id,
            "replaces_message_id": replacement_id, "status": "pending",
        }
        # Commit the user turn and cleared draft together before contacting a provider.
        try:
            self._store.save(conversation)
        except OSError:
            log.exception("Failed to save generation request")
            self.error.emit(self.tr("Could not save this chat. Nothing was sent; your draft has been kept."))
            return False
        self._unsaved.pop(conversation.id, None)
        self._conversation = conversation
        rates = profile.model_rates.get(model, {})
        self._operation = Generation(
            operation_id, conversation, conversation.messages[user_index].id, replacement_id,
            ResponseStatistics(input_rate=rates.get("input"), output_rate=rates.get("output")),
        )
        if self._usage_callback is not None:
            self._client.usage.disconnect(self._usage_callback)
        self._usage_callback = lambda usage: self._on_usage(usage, operation_id)
        self._client.usage.connect(self._usage_callback)
        if self._callbacks is not None:
            for signal, callback in zip(
                (self._client.delta, self._client.completed, self._client.failed), self._callbacks,
                strict=True,
            ):
                signal.disconnect(callback)
        self._callbacks = (
            lambda delta: self._on_delta(delta, operation_id),
            lambda: self._on_completed(operation_id),
            lambda message: self._on_failed(message, operation_id),
        )
        for signal, callback in zip(
            (self._client.delta, self._client.completed, self._client.failed), self._callbacks,
            strict=True,
        ):
            signal.connect(callback)
        self._buffer = ""
        self._busy = True
        self._thinking_seconds = None
        self.conversation_changed.emit(conversation)
        if kind in {"send", "edit"}:
            self.message_added.emit(conversation.messages[user_index])
        self.stream_started.emit()
        self._thinking_started = monotonic()
        try:
            self._client.start(url, provider.headers(api_key), payload, provider)
        except (RuntimeError, ValueError, OSError):
            log.exception("Failed to start generation")
            self._on_failed(self.tr("Could not start the request. Try again."), operation_id)
        return True

    def stop(self) -> None:
        if not self._busy:
            return
        self._client.abort()
        self._finish("stopped")

    def delete(self, conversation_id: str) -> None:
        if self._conversation is not None and self._conversation.id == conversation_id:
            self.stop()
        self._store.delete(conversation_id)
        self._unsaved.pop(conversation_id, None)
        if self._conversation is not None and self._conversation.id == conversation_id:
            self._conversation = None

    def update_metadata(self, conversation_id: str, **changes) -> bool:
        if not set(changes) <= {"title", "pinned", "archived"}:
            return False
        current = self._conversation
        is_current = current is not None and current.id == conversation_id
        if is_current and self._busy:
            return False
        conversation = current if is_current else (
            self._unsaved.get(conversation_id) or self._store.load(conversation_id)
        )
        if conversation is None:
            return False
        if "title" in changes:
            title = str(changes["title"]).strip()
            if not title or len(title) > 200:
                self.error.emit(self.tr("Use a chat title between 1 and 200 characters."))
                return False
            changes["title"] = title
            conversation.title_is_custom = True
        for key, value in changes.items():
            setattr(conversation, key, value)
        return self._persist(conversation)

    def list_conversations(self) -> list[Conversation]:
        conversations = {c.id: c for c in self._store.list()}
        conversations.update(self._unsaved)
        if self._conversation is not None and (
            self._conversation.messages or self._conversation.draft_text
        ):
            conversations[self._conversation.id] = self._conversation
        return sorted(conversations.values(), key=lambda c: c.updated_at, reverse=True)

    def shutdown(self) -> None:
        self.stop()

    def _on_delta(self, delta: str, operation_id: str | None = None) -> None:
        if not self._busy or not delta or (operation_id is not None and (
            self._operation is None or self._operation.id != operation_id
        )):
            return
        if self._thinking_seconds is None and self._thinking_started is not None:
            self._thinking_seconds = max(0.0, monotonic() - self._thinking_started)
            self.thinking_finished.emit(self._thinking_seconds)
        self._buffer += delta
        self.stream_delta.emit(delta)

    def _on_completed(self, operation_id: str | None = None) -> None:
        if operation_id is not None and (self._operation is None or self._operation.id != operation_id):
            return
        self._finish()

    def _on_usage(self, usage: dict, operation_id: str) -> None:
        operation = self._operation
        if not self._busy or operation is None or operation.id != operation_id:
            return
        for key in ("input_tokens", "output_tokens"):
            if key in usage:
                setattr(operation.statistics, key, usage[key])

    def _on_failed(self, message: str, operation_id: str | None = None) -> None:
        if not self._busy or (operation_id is not None and (
            self._operation is None or self._operation.id != operation_id
        )):
            return
        for profile in self._config.profiles():
            key = self._credentials.get_secret(profile.credential_name)
            if key:
                message = message.replace(key, "[redacted]")
        message = re.sub(
            r"(?i)(\bbearer\s+|\b(?:api[_ -]?key|access[_ -]?token)\s*[:=]\s*)[^\s,;<>]+",
            r"\1[redacted]", message,
        )
        message = " ".join(message.split())[:600] or self.tr("The request failed. Use Retry to try again.")
        self._finish("failed", message)

    def _finish(self, status: str = "complete", error_message: str = "") -> None:
        if not self._busy:
            return
        finished = monotonic()
        self._busy = False
        text = self._buffer.rstrip()
        self._buffer = ""
        message: Message | None = None
        operation, self._operation = self._operation, None
        if operation is not None and self._thinking_started is not None:
            operation.statistics.duration_seconds = max(0.0, finished - self._thinking_started)
        conversation = operation.conversation if operation is not None else self._conversation
        if status == "complete" and not text:
            status = "failed"
        if status == "failed" and not error_message:
            error_message = self.tr("No response was received. Use Retry to try again.")
        if conversation is not None:
            conversation.last_attempt["status"] = status
            if error_message:
                conversation.last_attempt["error"] = error_message
        replacement = next((m for m in conversation.messages if operation is not None
                            and m.id == operation.replaces_message_id), None) if conversation is not None else None
        # A failed replacement must never destroy an existing answer, even a partial one.
        if text and conversation is not None and (replacement is None or status == "complete"):
            message = Message(
                role="assistant", content=text, thinking_seconds=self._thinking_seconds,
                status=status,
                statistics=operation.statistics if operation is not None else None,
            )
            if replacement is not None:
                message.id = replacement.id
                conversation.messages[conversation.messages.index(replacement)] = message
                conversation.updated_at = time.time()
            else:
                conversation.add(message)
        if conversation is not None:
            self._persist(conversation)
        self._thinking_started = None
        self._thinking_seconds = None
        self.stream_finished.emit(message)
        if status == "failed" and error_message:
            self.error.emit(error_message)
