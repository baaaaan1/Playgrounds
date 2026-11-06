from __future__ import annotations

import pytest
from PyQt6.QtCore import QSettings, QSize, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QFrame, QMessageBox

from app.core.config import Config
from app.core.models import Conversation, Message
from app.core.profiles import ConnectionProfile
from app.core.store import ConversationStore
from app.ui.chat_controller import ChatController
from app.ui.main_window import MainWindow
from app.ui.settings_dialog import SettingsDialog
from app.ui.widgets import ChevronComboBox


def test_chat_uses_active_profile_and_optional_key(qt_app, workdir, credentials, monkeypatch) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    first = ConnectionProfile(name="First", base_url="https://first.example/v1", model="a")
    second = ConnectionProfile(name="Second", base_url="https://second.example/v1", model="b", temperature=1.3, system_prompt="Second instructions")
    config.save_profiles([first, second], second.id)
    credentials.set_secret(first.credential_name, "first-secret")
    credentials.set_secret(second.credential_name, "second-secret")
    store = ConversationStore(workdir / "chats")
    controller = ChatController(config, store, credentials)
    calls = []
    monkeypatch.setattr(controller._client, "start", lambda *args: calls.append(args))
    controller.send("Hello")
    url, headers, payload, _ = calls[0]
    assert url == "https://second.example/v1/chat/completions"
    assert headers["Authorization"] == "Bearer second-secret"
    assert payload["model"] == "b"
    assert payload["temperature"] == 1.3
    assert payload["messages"][0]["content"] == "Second instructions"
    assert controller.conversation.profile_id == second.id
    controller._on_delta("Answer")
    controller._on_completed()
    saved = store.load(controller.conversation.id)
    assert saved.profile_id == second.id


def test_chat_reopens_exact_connection_and_model(qt_app, workdir, credentials) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    first = ConnectionProfile(name="First", base_url="http://localhost:8080/v1", model="old")
    second = ConnectionProfile(name="Second", base_url="http://localhost:8081/v1", model="second")
    config.save_profiles([first, second], second.id)
    store = ConversationStore(workdir / "chats")
    chat = Conversation(profile_id=first.id, provider="custom", model="chat-model")
    chat.add(Message("user", "History"))
    store.save(chat)
    config.set("last_conversation", chat.id)
    window = MainWindow(config, store, credentials)
    assert window._profile_combo.currentData() == first.id
    assert window._model_combo.currentText() == "chat-model"
    assert config.active_profile().model == "chat-model"
    window._model_combo.setCurrentText("")
    assert config.active_profile().model == "chat-model"
    window.close()


@pytest.mark.parametrize("selected", ["current-model", "old-provider/model", ""])
def test_old_chat_cannot_restore_foreign_model_into_current_endpoint(
    qt_app, workdir, credentials, monkeypatch, selected,
) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    config.set("updates/automatic", False)
    profile = ConnectionProfile(
        name="Current provider", base_url="https://current.example/v1",
        model=selected, models=["current-model", "other-current-model"],
    )
    config.save_profiles([profile], profile.id)
    store = ConversationStore(workdir / "chats")
    chat = Conversation(profile_id=profile.id, model="old-provider/model")
    chat.add(Message("user", "Old question"))
    store.save(chat)
    config.set("last_conversation", chat.id)
    window = MainWindow(config, store, credentials)
    calls = []
    monkeypatch.setattr(window._controller._client, "start", lambda *args: calls.append(args))
    try:
        expected = "current-model" if selected == "current-model" else ""
        assert config.active_profile().model == expected
        assert window._model_combo.currentText() == expected
        assert window._model_combo.findText("old-provider/model") == -1
        assert "previous model" in window._banner.text()
        assert not window._banner_wrap.isHidden()
        window._composer.set_text("Follow up")
        if not expected:
            window._send()
            assert calls == []
            assert window._composer.text() == "Follow up"
        window._model_combo.setCurrentIndex(window._model_combo.findText("current-model"))
        window._send()
        assert calls[0][0] == "https://current.example/v1/chat/completions"
        assert calls[0][2]["model"] == "current-model"
    finally:
        window.close()


def test_reopening_chat_still_restores_model_in_current_catalog(qt_app, workdir, credentials):
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    config.set("updates/automatic", False)
    profile = ConnectionProfile(model="a", models=["a", "b"])
    config.save_profiles([profile], profile.id)
    store = ConversationStore(workdir / "chats")
    chat = Conversation(profile_id=profile.id, model="b", messages=[Message("user", "Question")])
    store.save(chat)
    config.set("last_conversation", chat.id)
    window = MainWindow(config, store, credentials)
    try:
        assert config.active_profile().model == "b"
        assert window._model_combo.currentText() == "b"
    finally:
        window.close()


def test_busy_settings_allows_appearance_without_editing_connections(qt_app, workdir, credentials, monkeypatch) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    window = MainWindow(config, ConversationStore(workdir / "chats"), credentials)
    window._controller._busy = True
    window._on_stream_started()
    original = config.profiles()

    def save_appearance(dialog):
        assert dialog._pages.currentIndex() == 1
        assert not dialog._pages.widget(0).isEnabled()
        assert dialog._theme_light.isEnabled()
        dialog._theme_light.setChecked(True)
        assert dialog._save()
        return dialog.result()

    monkeypatch.setattr(SettingsDialog, "exec", save_appearance)
    window._open_settings()
    assert config.theme == "light"
    assert config.profiles() == original
    assert window._composer._busy
    assert not window._composer._stop.isHidden()
    window._controller._busy = False
    window.close()


@pytest.mark.parametrize("save", [False, True])
def test_settings_refreshes_fetched_models_only_after_save(qt_app, workdir, credentials, monkeypatch, save) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    window = MainWindow(config, ConversationStore(workdir / "chats"), credentials)
    original = config.active_profile()
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Discard)

    def fetch_and_cancel(dialog):
        dialog._models_received(["alpha", "beta"])
        if save:
            assert dialog._save()
        else:
            dialog.reject()
        return dialog.result()

    monkeypatch.setattr(SettingsDialog, "exec", fetch_and_cancel)
    try:
        window._open_settings()
        expected = ["alpha", "beta"] if save else original.models
        assert window._model_combo.currentText() == ("alpha" if save else original.model)
        assert [window._model_combo.itemText(index) for index in range(window._model_combo.count())] == expected
        assert config.active_profile().models == expected
    finally:
        window.close()


@pytest.mark.parametrize("models", [["alpha", "beta"], ["alpha"]])
def test_settings_preserves_removed_model_after_cancel(qt_app, workdir, credentials, monkeypatch, models) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    profile = ConnectionProfile(name="Test", model="alpha", models=models)
    config.save_profiles([profile], profile.id)
    window = MainWindow(config, ConversationStore(workdir / "chats"), credentials)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Discard)

    def delete_and_cancel(dialog):
        dialog._delete_model_button.click()
        dialog.reject()
        return dialog.result()

    monkeypatch.setattr(SettingsDialog, "exec", delete_and_cancel)
    try:
        window._open_settings()
        assert config.active_profile().models == models
        assert window._model_combo.findText("alpha") >= 0
        assert window._model_combo.currentText() == "alpha"
    finally:
        window.close()


def test_missing_chat_profile_requires_explicit_connection_choice(qt_app, workdir, credentials, monkeypatch) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    profile = config.active_profile()
    store = ConversationStore(workdir / "chats")
    chat = Conversation(profile_id="deleted-connection", model="private-model")
    chat.add(Message("user", "Private conversation"))
    store.save(chat)
    config.set("last_conversation", chat.id)
    window = MainWindow(config, store, credentials)
    assert window._profile_combo.currentIndex() == -1
    calls = []
    monkeypatch.setattr(window._controller._client, "start", lambda *args: calls.append(args))
    window._composer.set_text("Follow up")
    window._send()
    assert not calls
    assert len(window._controller.conversation.messages) == 1
    window._profile_combo.setCurrentIndex(window._profile_combo.findData(profile.id))
    assert window._model_combo.isEnabled()
    window._new_chat()
    assert window._profile_combo.currentIndex() >= 0
    window.close()


@pytest.mark.parametrize("edit_connection", [False, True])
def test_saving_settings_never_reconnects_missing_chat_implicitly(qt_app, workdir, credentials, monkeypatch, edit_connection) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    store = ConversationStore(workdir / "chats")
    conversation = Conversation(profile_id="deleted-connection", model="private-model")
    conversation.add(Message("user", "Private history"))
    store.save(conversation)
    config.set("last_conversation", conversation.id)
    window = MainWindow(config, store, credentials)
    calls = []
    monkeypatch.setattr(window._controller._client, "start", lambda *args: calls.append(args))

    def save_settings(dialog):
        if edit_connection:
            dialog._name.setText("Renamed connection")
        dialog._theme_light.setChecked(True)
        assert dialog._save()
        return dialog.result()

    monkeypatch.setattr(SettingsDialog, "exec", save_settings)
    try:
        window._open_settings()
        assert window._profile_combo.currentIndex() == -1
        assert not window._model_combo.isEnabled()
        assert window._meta.text() == "Connection unavailable"
        window._composer.set_text("Private follow-up")
        window._send()
        assert not calls
        assert len(window._controller.conversation.messages) == 1
    finally:
        window.close()


def test_saving_theme_preserves_flushed_and_pending_stream_text(qt_app, workdir, credentials, monkeypatch) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    window = MainWindow(config, ConversationStore(workdir / "chats"), credentials)
    monkeypatch.setattr(window._controller._client, "start", lambda *args: None)

    def save_appearance(dialog):
        assert not dialog._pages.widget(0).isEnabled()
        dialog._theme_light.setChecked(True)
        assert dialog._save()
        return dialog.result()

    monkeypatch.setattr(SettingsDialog, "exec", save_appearance)
    try:
        window._composer.set_text("Question")
        window._send()
        window._controller._on_delta("Visible partial answer")
        window._chat._flush()
        window._controller._on_delta(" and pending text")
        window._open_settings()
        transcript = window._chat.toPlainText()
        assert "ASSISTANT" in transcript
        assert transcript.count("Visible partial answer and pending text") == 1
        assert window._controller.busy
        window._controller._on_delta(" and next chunk")
        window._chat._flush()
        assert "Visible partial answer and pending text and next chunk" in window._chat.toPlainText()
        window._controller._on_completed()
        assert "Visible partial answer and pending text and next chunk" in window._chat.toPlainText()
    finally:
        window.close()


@pytest.mark.parametrize("width", [720, 880, 1180])
@pytest.mark.parametrize("sidebar_visible", [True, False])
@pytest.mark.parametrize("theme_name", ["dark", "light"])
def test_connection_selectors_fit_inside_composer(qt_app, workdir, credentials, width, sidebar_visible, theme_name) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    profile = ConnectionProfile(name="Long connection name " * 10, model="long-model-id-" * 20)
    config.save_profiles([profile], profile.id)
    config.set("sidebar_visible", sidebar_visible)
    window = MainWindow(config, ConversationStore(workdir / "chats"), credentials)
    window._apply_theme(theme_name)
    window.resize(width, 480)
    window.show()
    qt_app.processEvents()
    try:
        composer = window._composer
        frame = composer._frame
        assert window.width() == width
        assert window.height() == 480
        assert window._profile_combo is composer.profile_combo
        assert window._model_combo is composer.model_combo
        assert window.findChild(QFrame, "TopBar").findChildren(ChevronComboBox) == []
        for combo in (window._profile_combo, window._model_combo):
            assert frame.isAncestorOf(combo)
            assert frame.rect().contains(combo.geometry())
            assert combo.y() > composer._input.geometry().bottom()
            assert not combo.geometry().intersects(composer._send.geometry())
        assert not window._profile_combo.geometry().intersects(window._model_combo.geometry())
        assert window._profile_combo.currentData() == profile.id
        assert window._model_combo.currentText() == profile.model
        assert window._empty.horizontalScrollBar().maximum() == 0
        assert window._empty.verticalScrollBar().maximum() > 0
        window.show_demo()
        qt_app.processEvents()
        assert window.size() == QSize(width, 480)
        assert window._splitter.widget(1).rect().contains(composer.parentWidget().geometry())
    finally:
        window.close()


def test_composer_selectors_keep_profile_model_and_busy_behavior(qt_app, workdir, credentials, monkeypatch) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    first = ConnectionProfile(name="First", base_url="https://first.example/v1", model="first-model")
    second = ConnectionProfile(
        name="Second", base_url="https://second.example/v1", model="second-model",
        models=["second-model", "alternate-model"],
    )
    config.save_profiles([first, second], first.id)
    window = MainWindow(config, ConversationStore(workdir / "chats"), credentials)
    calls = []
    monkeypatch.setattr(window._controller._client, "start", lambda *args: calls.append(args))
    try:
        window._profile_combo.setCurrentIndex(window._profile_combo.findData(second.id))
        assert config.active_profile().id == second.id
        assert window._model_combo.currentText() == "second-model"
        window._model_combo.setCurrentIndex(window._model_combo.findText("alternate-model"))
        assert config.active_profile().model == "alternate-model"
        window._composer.set_text("Hello")
        window._send()
        assert calls[0][2]["model"] == "alternate-model"
        assert not window._profile_combo.isEnabled()
        assert not window._model_combo.isEnabled()
        assert not window._composer._stop.isHidden()
        window._controller._on_completed()
        assert window._profile_combo.isEnabled()
        assert window._model_combo.isEnabled()
        assert not window._composer._send.isHidden()
    finally:
        window.close()


def test_chat_model_is_list_only_and_can_be_selected_by_click(qt_app, workdir, credentials) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    profile = ConnectionProfile(name="Test", model="model-a", models=["model-a", "model-b"])
    config.save_profiles([profile], profile.id)
    window = MainWindow(config, ConversationStore(workdir / "chats"), credentials)
    window.show()
    qt_app.processEvents()
    try:
        combo = window._model_combo
        assert not combo.isEditable()
        assert combo.lineEdit() is None
        QTest.keyClicks(combo, "zzz")
        combo.setCurrentText("unlisted-model")
        assert combo.currentText() == "model-a"
        assert config.active_profile().model == "model-a"
        combo.showPopup()
        qt_app.processEvents()
        view = combo.view()
        index = combo.model().index(combo.findText("model-b"), combo.modelColumn())
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=view.visualRect(index).center())
        assert combo.currentText() == "model-b"
        assert config.active_profile().model == "model-b"
    finally:
        window.close()
