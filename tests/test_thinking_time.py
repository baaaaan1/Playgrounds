from __future__ import annotations

import pytest
from PyQt6.QtCore import QSettings

from app.core.config import Config
from app.core.models import Conversation, Message
from app.core.profiles import ConnectionProfile
from app.core.store import ConversationStore
from app.ui import chat_controller, chat_view, theme
from app.ui.chat_view import ChatView
from app.ui.main_window import MainWindow


def test_thinking_time_roundtrip_and_legacy_messages(workdir) -> None:
    store = ConversationStore(workdir)
    conversation = Conversation()
    conversation.add(Message("assistant", "Answer", thinking_seconds=2.75))
    store.save(conversation)
    assert store.load(conversation.id).messages[0].thinking_seconds == 2.75
    assert Message.from_dict({"role": "assistant", "content": "Old answer"}).thinking_seconds is None
    assert "thinking_seconds" not in Message("user", "Question").to_dict()
    assert Message.from_dict(Message("assistant", "Instant", thinking_seconds=0.0).to_dict()).thinking_seconds == 0.0


@pytest.mark.parametrize("finish", ["complete", "stop", "fail"])
def test_thinking_timer_freezes_on_first_text_and_survives_reopen(
    qt_app, workdir, credentials, monkeypatch, finish,
) -> None:
    now = [100.0]
    monkeypatch.setattr(chat_controller, "monotonic", lambda: now[0])
    monkeypatch.setattr(chat_view, "monotonic", lambda: now[0])
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    profile = ConnectionProfile(name="Test", base_url="https://example.test/v1", model="test-model")
    config.save_profiles([profile], profile.id)
    store = ConversationStore(workdir / "chats")
    window = MainWindow(config, store, credentials)
    controller = window._controller
    view = window._chat
    monkeypatch.setattr(controller._client, "start", lambda *args: None)
    try:
        window._composer.set_text("Question")
        window._send()
        assert "Thinking... 0.0s" in view.toPlainText()
        now[0] = 102.5
        view._thinking_timer.timeout.emit()
        assert "Thinking... 2.5s" in view.toPlainText()
        controller._on_delta("")
        assert view._thinking_timer.isActive()
        window._apply_theme("light")
        assert "Thinking... 2.5s" in view.toPlainText()
        now[0] = 103.25
        controller._on_delta("First answer")
        view._flush()
        assert "Thought for 3.2s" in view.toPlainText()
        assert "First answer" in view.toPlainText()
        assert "Thinking..." not in view.toPlainText()
        assert not view._thinking_timer.isActive()
        now[0] = 120.0
        controller._on_delta(" and pending text")
        window._apply_theme("dark")
        assert "Thought for 3.2s" in view.toPlainText()
        assert view.toPlainText().count("First answer and pending text") == 1
        if finish == "stop":
            controller.stop()
        elif finish == "fail":
            controller._on_failed("Connection lost")
        else:
            controller._on_completed()
        assert "Thought for 3.2s" in view.toPlainText()
        assert not view._thinking_timer.isActive()
        saved = store.load(controller.conversation.id)
        assert saved.messages[-1].thinking_seconds == 3.25
        assert saved.messages[-1].content == "First answer and pending text"
        view.show_conversation(saved)
        assert "Thought for 3.2s" in view.toPlainText()
        window._composer.set_text("Next question")
        window._send()
        assert "Thinking... 0.0s" in view.toPlainText()
        now[0] = 121.0
        controller._on_delta("Next answer")
        controller._on_completed()
        assert "Thought for 1.0s" in view.toPlainText()
        assert "Thinking..." not in view.toPlainText()
    finally:
        window.close()


@pytest.mark.parametrize("finish", ["complete", "stop", "fail"])
def test_empty_response_cleans_up_thinking_timer(
    qt_app, workdir, credentials, monkeypatch, finish,
) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    profile = ConnectionProfile(name="Test", base_url="https://example.test/v1", model="test-model")
    config.save_profiles([profile], profile.id)
    window = MainWindow(config, ConversationStore(workdir / "chats"), credentials)
    controller = window._controller
    monkeypatch.setattr(controller._client, "start", lambda *args: None)
    try:
        controller.send("Question")
        if finish == "stop":
            controller.stop()
        elif finish == "fail":
            controller._on_failed("Connection lost")
        else:
            controller._on_completed()
        assert "Thinking..." not in window._chat.toPlainText()
        assert "Thought for" not in window._chat.toPlainText()
        assert not window._chat._thinking_timer.isActive()
        assert len(controller.conversation.messages) == 1
    finally:
        window.close()


def test_clear_chat_stops_timer_and_legacy_messages_have_no_timing(qt_app) -> None:
    view = ChatView(theme.tokens_for("dark"))
    try:
        conversation = Conversation(messages=[Message("assistant", "Old answer")])
        view.show_conversation(conversation)
        assert "Thought for" not in view.toPlainText()
        view.begin_stream()
        assert view._thinking_timer.isActive()
        view.clear_chat()
        assert not view._thinking_timer.isActive()
        assert view.toPlainText() == ""
    finally:
        view.close()
