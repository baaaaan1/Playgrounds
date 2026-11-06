from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette, QTextCursor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QLabel

from app.core.models import Conversation, Message
from app.ui import theme
from app.ui.chat_view import ChatView


@pytest.fixture()
def view(qt_app):
    widget = ChatView(theme.tokens_for("dark"))
    widget.resize(640, 480)
    widget.show()
    widget.activateWindow()
    yield widget
    widget.clear_chat()
    widget.close()


def start_edit(view, text="Original"):
    chat = Conversation(messages=[Message("user", text), Message("assistant", "Answer")])
    view.show_conversation(chat)
    view.begin_edit(chat.messages[0].id)
    return view._editor


@pytest.mark.parametrize("name", ["dark", "light"])
@pytest.mark.parametrize("size", [(400, 420), (640, 480), (900, 700)])
def test_inline_editor_palette_layout_and_focus(view, qt_app, name, size):
    previous_palette, previous_qss = qt_app.palette(), qt_app.styleSheet()
    tokens = theme.apply(qt_app, name)
    view.set_tokens(tokens)
    view.resize(*size)
    text = "Original message <b>not HTML</b>\n" + "long-line-" * 100
    panel = start_edit(view, text)
    qt_app.processEvents()
    try:
        assert panel.text() == text
        assert panel.parentWidget() is view.viewport()
        assert not panel.isWindow()
        assert panel._editor.hasFocus()
        assert panel._editor.accessibleName() == "Message"
        assert panel._editor.accessibleDescription()
        for widget in (panel._editor, panel._cancel, panel._send, *panel.findChildren(QLabel)):
            assert panel.rect().contains(widget.mapTo(panel, widget.rect().topLeft()))
            assert panel.rect().contains(widget.mapTo(panel, widget.rect().bottomRight()))
        assert panel._editor.horizontalScrollBar().maximum() == 0
        assert panel._editor.viewport().height() >= 64
        for label in panel.findChildren(QLabel, "EditHelp"):
            assert label.palette().color(QPalette.ColorRole.WindowText).name() == tokens["text_muted"]
            assert label.height() >= label.heightForWidth(label.width())
        palette = panel._editor.palette()
        assert palette.color(QPalette.ColorRole.Text).name() == tokens["text"]
        assert palette.color(QPalette.ColorRole.Highlight).name().upper() == tokens["accent"]
        assert palette.color(QPalette.ColorRole.HighlightedText).name() == tokens["accent_text"]
        image = panel._editor.viewport().grab().toImage()
        assert image.pixelColor(image.width() - 3, image.height() - 3).name() == tokens["surface"]
        image = panel._editor.grab().toImage()
        assert image.pixelColor(image.width() // 2, 0).name().upper() == tokens["accent_strong"]
        panel._cancel.setFocus()
        qt_app.processEvents()
        image = panel._cancel.grab().toImage()
        assert image.pixelColor(image.width() // 2, 0).name().upper() == tokens["accent_strong"]
        panel._editor.clear()
        assert not panel._send.isEnabled()
    finally:
        view.cancel_edit()
        qt_app.setPalette(previous_palette)
        qt_app.setStyleSheet(previous_qss)


def test_inline_keyboard_multiline_validation_and_submit(view, qt_app):
    submitted = []
    view.edit_submitted.connect(lambda *args: submitted.append(args))
    panel = start_edit(view)
    qt_app.processEvents()
    panel._editor.selectAll()
    QTest.keyClick(panel._editor, Qt.Key.Key_Return)
    assert panel.text() == "\n"
    assert not panel._send.isEnabled()
    panel.submit()
    QTest.keyClick(panel._editor, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    assert not submitted
    panel._editor.setPlainText("  Edited\nmessage  ")
    QTest.keyClick(panel._editor, Qt.Key.Key_Tab)
    assert panel._cancel.hasFocus()
    QTest.keyClick(panel._cancel, Qt.Key.Key_Tab)
    assert panel._send.hasFocus()
    panel._editor.setFocus()
    QTest.keyClick(panel._editor, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    assert submitted == [(view._conversation.id, view._conversation.messages[0].id,
                          "  Edited\nmessage  ")]
    # The owner closes the editor only after accepting the submission.
    assert view.editing


def test_inline_replaces_only_selected_message_and_tracks_layout(view, qt_app):
    messages = [Message("user", "First original"), Message("assistant", "First answer\n" * 40),
                Message("user", "Selected original"), Message("assistant", "Later answer")]
    chat = Conversation(messages=messages)
    view.show_conversation(chat)
    view.begin_edit(messages[2].id)
    panel = view._editor
    panel._editor.setPlainText("Unsent\nchanges <b>still plain text</b>")
    qt_app.processEvents()
    assert "Selected original" not in view.toPlainText()
    assert "First original" in view.toPlainText()
    assert "Later answer" in view.toPlainText()
    assert panel.isVisible()
    assert view.viewport().rect().intersects(panel.geometry())
    for size in ((400, 420), (900, 700), (640, 480)):
        view.resize(*size)
        view.set_tokens(theme.tokens_for("light"))
        view.show_conversation(chat)
        qt_app.processEvents()
        assert view._editor is panel
        assert panel.text() == "Unsent\nchanges <b>still plain text</b>"
        cursor = QTextCursor(view._edit_cursor)
        cursor.setPosition(cursor.selectionStart())
        assert panel.pos() == view.cursorRect(cursor).topLeft()
        assert panel.geometry().right() < view.viewport().width()
        following = QTextCursor(view.document())
        following.setPosition(view._message_ranges[messages[3].id][0])
        assert view.cursorRect(following).top() > panel.geometry().bottom()
        previous_y = panel.y()
        bar = view.verticalScrollBar()
        previous_scroll = bar.value()
        bar.setValue(max(0, previous_scroll - 30))
        assert panel.y() == previous_y + previous_scroll - bar.value()
    assert messages[2].content == "Selected original"
    view.cancel_edit()
    assert "Selected original" in view.toPlainText()


def test_inline_actions_and_lifecycle(view, qt_app):
    panel = start_edit(view)
    panel._editor.setPlainText("Unsaved")
    assert all(kind == "copy" for kind, _payload in view._actions.values())
    view.begin_edit(view._conversation.messages[1].id)
    assert view._editor is panel
    assert panel.text() == "Unsaved"
    view.show_conversation(Conversation(messages=[Message("user", "Other")]))
    assert not view.editing
    view.begin_edit(view._conversation.messages[0].id)
    view.clear_chat()
    assert not view.editing
    assert "chat-editor-placeholder" not in view.toHtml()
    chat = Conversation(messages=[Message("user", "Busy")])
    view.show_conversation(chat)
    view.set_busy(True)
    view.begin_edit(chat.messages[0].id)
    assert not view.editing
    view.set_busy(False)
    view.begin_stream()
    view.begin_edit(chat.messages[0].id)
    assert not view.editing
    view.end_stream(chat)


def test_inline_invalid_message_and_removed_target(view):
    chat = Conversation(messages=[Message("user", "Question"), Message("assistant", "Answer")])
    view.show_conversation(chat)
    for message_id in ("missing", chat.messages[1].id):
        view.begin_edit(message_id)
        assert not view.editing
    view.begin_edit(chat.messages[0].id)
    chat.messages.pop(0)
    view.show_conversation(chat)
    assert not view.editing


def test_inline_dirty_state_tracks_actual_text_and_undo(view):
    panel = start_edit(view, "Original")
    assert not panel.dirty
    assert not view.has_unsaved_edit
    panel._editor.selectAll()
    QTest.keyClicks(panel._editor, "Changed")
    assert panel.dirty
    assert view.has_unsaved_edit
    panel._editor.undo()
    assert panel.text() == "Original"
    assert not view.has_unsaved_edit
