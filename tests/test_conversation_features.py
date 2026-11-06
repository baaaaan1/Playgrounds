from __future__ import annotations

import pytest
from PyQt6.QtCore import QSettings, QSize, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QInputDialog, QMessageBox

from app.core.config import Config
from app.core.models import Conversation, Message
from app.core.profiles import ConnectionProfile
from app.core.store import ConversationStore
from app.ui import icons, theme
from app.ui.main_window import MainWindow


@pytest.fixture()
def window(qt_app, workdir, credentials, monkeypatch):
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    config.set("updates/automatic", False)
    profile = ConnectionProfile(name="Test", base_url="https://example.test/v1", model="test")
    config.save_profiles([profile], profile.id)
    window = MainWindow(config, ConversationStore(workdir / "chats"), credentials)
    monkeypatch.setattr(window._controller._client, "start", lambda *args: None)
    yield window
    window._chat.cancel_edit()
    window.close()


def answer(window, text="Answer"):
    window._controller._on_delta(text)
    window._controller._on_completed()


def test_draft_isolated_on_switch_and_restored_after_restart(window, credentials):
    window._composer.set_text("Draft A\nwith spaces  ")
    first_id = window._controller.conversation.id
    first_activity = window._controller.conversation.updated_at
    window._new_chat()
    assert window._composer.text() == ""
    assert window._store.load(first_id).draft_text == "Draft A\nwith spaces  "
    assert window._store.load(first_id).updated_at == first_activity
    window._composer.set_text("Draft B")
    second_id = window._controller.conversation.id
    window._open_conversation(first_id)
    assert window._composer.text() == "Draft A\nwith spaces  "
    assert window._store.load(second_id).draft_text == "Draft B"
    assert window._pending_draft is None
    window.close()
    reopened = MainWindow(window._config, window._store, credentials)
    try:
        assert reopened._controller.conversation.id == first_id
        assert reopened._composer.text() == "Draft A\nwith spaces  "
        reopened._open_conversation(second_id)
        assert reopened._composer.text() == "Draft B"
    finally:
        reopened.close()


def test_draft_debounce_and_restore_do_not_cross_save(window):
    window._composer.set_text("First")
    first_id = window._controller.conversation.id
    window._draft_timer.timeout.emit()
    assert window._store.load(first_id).draft_text == "First"
    window._new_chat()
    window._composer.set_text("Second")
    second_id = window._controller.conversation.id
    window._open_conversation(first_id)
    window._draft_timer.timeout.emit()
    assert window._store.load(first_id).draft_text == "First"
    assert window._store.load(second_id).draft_text == "Second"


def test_validation_keeps_draft_but_accepted_send_clears_it_atomically(window):
    profile = window._config.active_profile()
    profile.model = ""
    window._config.save_profile(profile)
    window._refresh_connection_ui()
    window._composer.set_text("Question")
    conversation_id = window._controller.conversation.id
    window._send()
    assert window._composer.text() == "Question"
    assert window._controller.conversation.messages == []
    assert window._flush_draft()
    assert window._store.load(conversation_id).draft_text == "Question"
    profile.model = "test"
    window._config.save_profile(profile)
    window._refresh_connection_ui()
    window._send()
    saved = window._store.load(conversation_id)
    assert saved.draft_text == ""
    assert saved.messages[0].content == "Question"
    assert window._composer.text() == ""
    assert window._pending_draft is None
    window._controller._on_failed("Network failure")
    assert window._composer.text() == ""
    window._retry(saved.messages[0].id)
    answer(window)
    assert len(window._controller.conversation.messages) == 2


def test_save_failure_blocks_navigation_and_close_without_losing_input(window, monkeypatch):
    window._composer.set_text("Keep draft")
    conversation_id = window._controller.conversation.id
    save = window._store.save

    def fail(conversation):
        raise OSError("Disk full")

    monkeypatch.setattr(window._store, "save", fail)
    window._new_chat()
    assert window._controller.conversation.id == conversation_id
    assert window._composer.text() == "Keep draft"
    assert not window.close()
    assert window._pending_draft == (conversation_id, "Keep draft")
    monkeypatch.setattr(window._store, "save", save)
    assert window._flush_draft()
    assert window._store.load(conversation_id).draft_text == "Keep draft"


def test_rename_pin_archive_and_restore(window, monkeypatch):
    window._composer.set_text("Question")
    window._send()
    answer(window)
    conversation_id = window._controller.conversation.id
    activity = window._controller.conversation.updated_at
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("New chat", True))
    window._rename_conversation(conversation_id)
    window._pin_conversation(conversation_id, True)
    saved = window._store.load(conversation_id)
    assert saved.title_is_custom and saved.title == "New chat"
    assert saved.pinned
    assert saved.updated_at == activity
    window._composer.set_text("Unsent")
    window._archive_conversation(conversation_id, True)
    saved = window._store.load(conversation_id)
    assert saved.archived and saved.draft_text == "Unsent"
    assert window._controller.conversation.id != conversation_id
    assert window._sidebar._list.count() == 0
    window._sidebar._archived_button.click()
    assert window._sidebar._list.count() == 1
    window._archive_conversation(conversation_id, False)
    assert not window._store.load(conversation_id).archived
    assert window._sidebar._list.count() == 0


def test_archived_chat_opens_inline_and_new_chat_returns_to_history(window, qt_app):
    archived = Conversation(
        title="Archived topic", archived=True,
        profile_id=window._config.active_profile().id, model="test",
        messages=[Message("user", "Archived question"), Message("assistant", "Archived answer")],
    )
    window._store.save(archived)
    window._refresh_conversations()
    windows = set(qt_app.topLevelWidgets())
    window._sidebar._archived_button.click()
    window._sidebar._on_item_clicked(window._sidebar._list.item(0))
    assert window._controller.conversation.id == archived.id
    assert window._stack.currentWidget() is window._chat
    assert "Archived answer" in window._chat.toPlainText()
    assert set(qt_app.topLevelWidgets()) == windows
    window._new_chat()
    assert not window._sidebar._showing_archived
    assert window._sidebar._section.text() == "HISTORY"
    assert window._sidebar._archived_button.text() == "Open archive"


def test_metadata_mutations_during_stream_cannot_overwrite_answer(window):
    window._composer.set_text("Question")
    window._send()
    conversation_id = window._controller.conversation.id
    window._pin_conversation(conversation_id, True)
    assert not window._controller.conversation.pinned
    window._controller._on_delta("Partial")
    window._archive_conversation(conversation_id, True)
    saved = window._store.load(conversation_id)
    assert saved.archived
    assert saved.messages[-1].content == "Partial"
    assert saved.messages[-1].status == "stopped"


def test_edit_action_preserves_source_draft_and_prefix(window):
    window._composer.set_text("Question")
    window._send()
    answer(window, "Original")
    source_id = window._controller.conversation.id
    user_id = window._controller.conversation.messages[0].id
    window._composer.set_text("Source draft")
    window._edit_message(user_id)
    panel = window._chat._editor
    assert panel.text() == "Question"
    assert panel.window() is window
    assert QApplication.activeModalWidget() is None
    assert window._controller.conversation.id == source_id
    panel._editor.setPlainText("Edited question")
    panel._send.click()
    assert not window._chat.editing
    assert window._controller.conversation.id != source_id
    assert window._composer.text() == ""
    assert [m.content for m in window._controller.conversation.messages] == ["Edited question"]
    saved_source = window._store.load(source_id)
    assert saved_source.draft_text == "Source draft"
    assert [m.content for m in saved_source.messages] == ["Question", "Original"]
    answer(window, "Edited answer")


@pytest.mark.parametrize("action", ["cancel", "escape"])
def test_cancel_edit_leaves_source_and_draft_unchanged(window, qt_app, action):
    window.show()
    window.activateWindow()
    window._composer.set_text("Question")
    window._send()
    answer(window, "Original")
    source = window._controller.conversation
    window._composer.set_text("Source draft")

    window._edit_message(source.messages[0].id)
    panel = window._chat._editor
    panel._editor.setPlainText("Canceled edit")
    qt_app.processEvents()
    if action == "cancel":
        panel._cancel.click()
    else:
        QTest.keyClick(panel._editor, Qt.Key.Key_Escape)
    assert not window._chat.editing
    assert window._controller.conversation is source
    assert window._composer.text() == "Source draft"
    assert [m.content for m in window._store.load(source.id).messages] == ["Question", "Original"]


@pytest.mark.parametrize("failure", ["save", "validation"])
def test_inline_edit_retained_when_submission_fails(window, monkeypatch, failure):
    window._composer.set_text("Question")
    window._send()
    answer(window)
    source = window._controller.conversation
    window._edit_message(source.messages[0].id)
    panel = window._chat._editor
    panel._editor.setPlainText("Keep this edit")
    if failure == "save":
        def fail(conversation):
            raise OSError("Disk full")
        monkeypatch.setattr(window._store, "save", fail)
    else:
        profile = window._config.active_profile()
        profile.model = ""
        window._config.save_profile(profile)
    panel._send.click()
    assert window._chat._editor is panel
    assert panel.text() == "Keep this edit"
    assert window._controller.conversation is source
    assert not window._controller.busy
    assert not window._banner_wrap.isHidden()


def test_inline_edit_blocks_competing_sends_and_clears_on_navigation(window):
    window._composer.set_text("Question")
    window._send()
    answer(window)
    source = window._controller.conversation
    window._composer.set_text("Separate draft")
    window._edit_message(source.messages[0].id)
    window._send()
    window._regenerate(source.messages[-1].id)
    window._retry(source.messages[0].id)
    assert not window._controller.busy
    assert window._composer.text() == "Separate draft"
    assert window._chat.editing
    window._new_chat()
    assert not window._chat.editing
    assert window._store.load(source.id).draft_text == "Separate draft"


def test_delete_cancels_pending_draft_and_does_not_resurrect_chat(window, monkeypatch):
    window._composer.set_text("Unsent")
    conversation_id = window._controller.conversation.id
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    window._delete_conversation(conversation_id)
    window._draft_timer.timeout.emit()
    assert window._store.load(conversation_id) is None
    assert window._pending_draft is None
    assert window._composer.text() == ""


def test_ctrl_f_and_escape_close_find_before_stop(window, qt_app):
    window.show()
    window.activateWindow()
    window._composer.set_text("Question")
    window._send()
    window._controller._on_delta("Searchable text")
    window._chat._flush()
    window._composer.focus_input()
    qt_app.processEvents()
    QTest.keyClick(window._composer._input, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    assert not window._find_bar.isHidden()
    window._find_bar._query.setText("Searchable")
    QTest.keyClick(window._find_bar._query, Qt.Key.Key_Escape)
    assert window._find_bar.isHidden()
    assert window._controller.busy
    QTest.keyClick(window._composer._input, Qt.Key.Key_Escape)
    assert not window._controller.busy


def test_sidebar_message_search_opens_correct_message_and_find(window):
    conversation = Conversation(
        title="Topic", profile_id=window._config.active_profile().id,
        messages=[Message("user", "Needle first"), Message("assistant", "Needle second")],
    )
    window._store.save(conversation)
    window._refresh_conversations()
    window._sidebar._search.setText("Needle")
    window._sidebar._search_timer.timeout.emit()
    item = window._sidebar._list.item(1)
    window._sidebar._on_item_clicked(item)
    assert window._controller.conversation.id == conversation.id
    assert not window._find_bar.isHidden()
    assert window._find_bar._query.text() == "Needle"
    assert window._chat._find_matches[window._chat._find_index].selectedText() == "Needle"
    assert window._find_bar._count.text() == "2 of 2"


def test_synchronous_start_failure_keeps_retry_error_visible(window, monkeypatch):
    def fail(*args):
        raise OSError("Start failed")

    monkeypatch.setattr(window._controller._client, "start", fail)
    window._composer.set_text("Question")
    window._send()
    assert not window._controller.busy
    assert not window._banner_wrap.isHidden()
    assert window._controller.conversation.last_attempt["status"] == "failed"
    assert window._composer.text() == ""


def test_metadata_save_error_remains_visible_and_keeps_composer(window, monkeypatch):
    window._composer.set_text("Question")
    window._send()
    answer(window)
    window._composer.set_text("Do not clear this draft")
    save = window._store.save

    def fail(conversation):
        raise OSError("Disk full")

    monkeypatch.setattr(window._store, "save", fail)
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("Renamed", True))
    window._rename_conversation(window._controller.conversation.id)
    assert window._composer.text() == "Do not clear this draft"
    assert window._title.text() == "Renamed"
    assert not window._banner_wrap.isHidden()
    assert "Could not save" in window._banner.text()
    monkeypatch.setattr(window._store, "save", save)
    assert window._flush_draft()


@pytest.mark.parametrize("search", [False, True])
def test_blocked_history_navigation_restores_active_selection(window, monkeypatch, search):
    window._composer.set_text("Needle A")
    window._send()
    answer(window)
    source_id = window._controller.conversation.id
    other = Conversation(
        title="Other", profile_id=window._config.active_profile().id,
        messages=[Message("user", "Needle B")],
    )
    window._store.save(other)
    window._refresh_conversations()
    if search:
        window._sidebar._search.setText("Needle")
        window._sidebar._search_timer.timeout.emit()
    window._composer.set_text("Unsent follow-up")
    save = window._store.save

    def fail(conversation):
        raise OSError("Disk full")

    monkeypatch.setattr(window._store, "save", fail)
    window._sidebar.select(other.id)
    assert window._sidebar.current_id() == other.id
    window._sidebar._on_item_clicked(window._sidebar._list.currentItem())
    assert window._controller.conversation.id == source_id
    assert window._sidebar.current_id() == source_id
    assert window._composer.text() == "Unsent follow-up"
    assert window._find_bar.isHidden()
    monkeypatch.setattr(window._store, "save", save)
    assert window._flush_draft()


def test_missing_history_file_restores_active_selection(window):
    window._composer.set_text("Question")
    window._send()
    answer(window)
    source_id = window._controller.conversation.id
    missing = Conversation(title="Removed")
    window._sidebar.set_conversations([window._controller.conversation, missing])
    window._sidebar.select(missing.id)
    window._sidebar._on_item_clicked(window._sidebar._list.currentItem())
    assert window._controller.conversation.id == source_id
    assert window._sidebar.current_id() == source_id
    assert "Could not open" in window._banner.text()


def test_starter_suggestion_preserves_draft_and_undo(window):
    window._composer.set_text("Keep my original draft  ")
    window._empty.suggestion_chosen.emit("Suggested prompt")
    assert window._composer.text() == "Keep my original draft  \n\nSuggested prompt"
    window._composer._input.undo()
    assert window._composer.text() == "Keep my original draft  "
    assert window._flush_draft()
    assert window._store.load(window._controller.conversation.id).draft_text == window._composer.text()


@pytest.mark.parametrize("action", ["new", "open", "archive", "delete", "close"])
@pytest.mark.parametrize("discard", [False, True])
def test_dirty_inline_edit_requires_explicit_discard(window, monkeypatch, action, discard):
    window._composer.set_text("Question")
    window._send()
    answer(window)
    source = window._controller.conversation
    other = Conversation(title="Other")
    window._store.save(other)
    window._refresh_conversations()
    window._edit_message(source.messages[0].id)
    panel = window._chat._editor
    panel._editor.setPlainText("Unsaved edit")
    prompts = []

    def choose(*args):
        if args[1] == "Delete chat":
            return QMessageBox.StandardButton.Yes
        prompts.append(args)
        return QMessageBox.StandardButton.Discard if discard else QMessageBox.StandardButton.Cancel

    monkeypatch.setattr(QMessageBox, "question", choose)
    if action == "new":
        window._new_chat()
    elif action == "open":
        window._sidebar.select(other.id)
        window._open_conversation(other.id)
    elif action == "archive":
        window._archive_conversation(source.id, True)
    elif action == "delete":
        window._delete_conversation(source.id)
    else:
        assert window.close() == discard
    assert len(prompts) == 1
    assert prompts[0][-1] == QMessageBox.StandardButton.Cancel
    if discard:
        assert not window._chat.editing
    else:
        assert window._controller.conversation is source
        assert window._chat._editor is panel
        assert panel.text() == "Unsaved edit"
        assert window._sidebar.current_id() == source.id
        assert not window._store.load(source.id).archived


def test_unchanged_inline_edit_does_not_prompt(window, monkeypatch):
    window._composer.set_text("Question")
    window._send()
    answer(window)
    window._edit_message(window._controller.conversation.messages[0].id)
    assert not window._chat.has_unsaved_edit

    def unexpected_prompt(*args):
        pytest.fail("Unchanged edits must not require discard confirmation")

    monkeypatch.setattr(QMessageBox, "question", unexpected_prompt)
    window._new_chat()
    assert not window._chat.editing


@pytest.mark.parametrize("focus_search", [False, True])
def test_stream_completion_preserves_intentional_focus(window, qt_app, focus_search):
    window.show()
    window.activateWindow()
    window._composer.set_text("Question")
    window._send()
    qt_app.processEvents()
    if focus_search:
        window._find_bar.open("Question")
    else:
        window._composer._stop.setFocus()
    qt_app.processEvents()
    answer(window)
    qt_app.processEvents()
    if focus_search:
        assert window._find_bar._query.hasFocus()
        QTest.keyClicks(window._find_bar._query, " extended")
        assert window._composer.text() == ""
    else:
        assert window._composer._input.hasFocus()


@pytest.mark.parametrize("confirm", [False, True])
def test_regeneration_discloses_response_replacement(window, monkeypatch, confirm):
    window._composer.set_text("Question")
    window._send()
    answer(window, "Original")
    message_id = window._controller.conversation.messages[-1].id
    prompts = []

    def choose(*args):
        prompts.append(args)
        return QMessageBox.StandardButton.Yes if confirm else QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", choose)
    window._regenerate(message_id)
    assert len(prompts) == 1
    assert "cannot be restored" in prompts[0][2]
    assert window._controller.busy == confirm
    assert window._controller.conversation.messages[-1].content == "Original"
    if confirm:
        answer(window, "Replacement")


def test_error_stays_actionable_and_is_restored_when_chat_reopens(window):
    window._composer.set_text("Question")
    window._send()
    source_id = window._controller.conversation.id
    window._controller._on_failed("Quota exhausted. Check your account.")
    assert not window._banner_wrap.isHidden()
    assert window._banner.text() == "Quota exhausted. Check your account."
    assert not window._banner_retry.isHidden()
    assert window._banner.accessibleDescription() == window._banner.text()
    assert not hasattr(window, "_banner_timer")
    window._banner_dismiss.click()
    assert window._banner_wrap.isHidden()
    window._new_chat()
    assert window._open_conversation(source_id)
    assert not window._banner_wrap.isHidden()
    assert window._banner.text() == "Quota exhausted. Check your account."
    window._banner_retry.click()
    assert window._controller.busy
    assert window._banner_wrap.isHidden()
    answer(window)


@pytest.mark.parametrize("theme_name", ["dark", "light"])
@pytest.mark.parametrize("activation", ["mouse", "keyboard"])
def test_error_banner_retry_is_themed_icon_button(window, qt_app, theme_name, activation):
    old_palette, old_qss = qt_app.palette(), qt_app.styleSheet()
    try:
        window._apply_theme(theme_name)
        window.show()
        window.activateWindow()
        window._composer.set_text("Question")
        window._send()
        window._controller._on_failed("Connection failed")
        qt_app.processEvents()
        button = window._banner_retry
        assert button.isVisible()
        assert button.text() == ""
        assert button.size() == QSize(34, 34)
        assert button.iconSize() == QSize(18, 18)
        assert button.toolTip() == button.accessibleName() == "Retry failed response"
        expected = icons.icon("regenerate", theme.icon_color(window._tokens), 18)
        assert button.icon().pixmap(18, 18).toImage() == expected.pixmap(18, 18).toImage()
        if activation == "mouse":
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        else:
            button.setFocus()
            QTest.keyClick(button, Qt.Key.Key_Space)
        assert window._controller.busy
        assert window._banner_wrap.isHidden()
        answer(window)
    finally:
        qt_app.setPalette(old_palette)
        qt_app.setStyleSheet(old_qss)


def test_settings_recovery_button_opens_connection_settings(window, monkeypatch):
    calls = []
    # Reconnect through the public button signal to avoid opening a modal dialog.
    window._banner_settings.clicked.disconnect()
    window._banner_settings.clicked.connect(lambda: calls.append("settings"))
    window._on_error("Select a connection.")
    assert window._banner_retry.isHidden()
    window._banner_settings.click()
    assert calls == ["settings"]
