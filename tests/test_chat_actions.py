from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QSize, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QImage, QKeyEvent, QTextDocument
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QToolButton

from app.core.models import Conversation, Message
from app.ui import theme
from app.ui.chat_find import ChatFindBar
from app.ui.chat_view import ChatView
from app.ui.markdown import extract_code_blocks, render_markdown
from app.ui.theme import tokens_for


@pytest.fixture()
def view(qt_app):
    widget = ChatView(tokens_for("dark"))
    widget.resize(620, 340)
    widget.show()
    yield widget
    widget.clear_chat()
    widget.close()


def conversation(*messages, attempt=None):
    chat = Conversation(messages=list(messages))
    chat.last_attempt = attempt or {}
    for index, message in enumerate(messages):
        message.id = f"message-{index}"
    return chat


def action_url(view, kind, payload):
    return QUrl(next(url for url, action in view._actions.items() if action == (kind, payload)))


def activate(view, kind, payload):
    view.anchorClicked.emit(action_url(view, kind, payload))


def hrefs(view):
    result = []
    block = view.document().begin()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            href = iterator.fragment().charFormat().anchorHref()
            if href:
                result.append(href)
            iterator += 1
        block = block.next()
    return result


@pytest.mark.parametrize("raw, expected", [
    ("```c++\r\n  int x = 1;\r\n\treturn x;\r\n```\r\n", ["  int x = 1;\r\n\treturn x;\r\n"]),
    ("Before\n```python\n    first()\n\n  second()", ["    first()\n\n  second()"]),
    ("```\n\n```\n~~~shell\n  echo hi\n~~~", ["\n", "  echo hi\n"]),
    ("````c++\n```\n  code\n````", ["```\n  code\n"]),
    ("```\n```", [""]),
])
def test_shared_fence_parser_preserves_raw_code(raw, expected):
    assert extract_code_blocks(raw) == expected
    rendered = render_markdown(raw, tokens_for("dark"))
    assert rendered.count("<pre") == len(expected)


def test_response_and_each_code_copy_are_exact(view, qt_app):
    raw = "**Answer**\r\n```c++\r\n  int x;\r\n\treturn x;\r\n```\r\nTail\n```py\n    unclosed()"
    message = Message("assistant", raw)
    view.show_conversation(conversation(message))
    activate(view, "copy", raw)
    assert qt_app.clipboard().text() == raw
    for code in extract_code_blocks(raw):
        activate(view, "copy", code)
        assert qt_app.clipboard().text() == code
    buttons = view.findChildren(QToolButton, "CopyResponse")
    assert len(buttons) == 1
    assert buttons[0].toolTip() == "Copy response"
    assert buttons[0].accessibleName() == "Copy response"
    assert not buttons[0].icon().isNull()
    assert "Copy response" not in view.toPlainText()
    assert view.toPlainText().count("Copy code") == 2


@pytest.mark.parametrize("name", ["dark", "light"])
def test_copy_icon_button_mouse_keyboard_and_theme(view, qt_app, name):
    old_palette, old_qss = qt_app.palette(), qt_app.styleSheet()
    try:
        tokens = theme.apply(qt_app, name)
        view.set_tokens(tokens)
        raw = "  **Answer**\n```python\n  print('exact')\n```\nTail  "
        view.show_conversation(conversation(Message("assistant", raw)))
        view.activateWindow()
        qt_app.processEvents()
        button = view.findChild(QToolButton, "CopyResponse")
        assert button.isVisible()
        assert button.iconSize() == QSize(16, 16)
        assert button.size() == QSize(24, 24)
        assert view.anchorAt(button.geometry().center()) == action_url(view, "copy", raw).toString()
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        assert qt_app.clipboard().text() == raw
        qt_app.clipboard().setText("Not copied yet")
        button.setFocus()
        QTest.keyClick(button, Qt.Key.Key_Space)
        assert qt_app.clipboard().text() == raw
        qt_app.processEvents()
        image = button.grab().toImage()
        assert image.pixelColor(image.width() // 2, image.height() - 1).name().upper() == tokens["accent_strong"]
        QTest.mouseMove(view.viewport(), view.viewport().rect().topLeft())
        QTest.mouseMove(button, button.rect().center())
        qt_app.processEvents()
        image = view.viewport().grab().toImage()
        assert image.pixelColor(button.x() + button.width() // 2, button.y() + 1).name() == tokens["assistant_surface"]
    finally:
        qt_app.setPalette(old_palette)
        qt_app.setStyleSheet(old_qss)


@pytest.mark.parametrize("name", ["dark", "light"])
def test_edit_and_regenerate_buttons_mouse_keyboard_and_theme(view, qt_app, name):
    old_palette, old_qss = qt_app.palette(), qt_app.styleSheet()
    try:
        tokens = theme.apply(qt_app, name)
        view.set_tokens(tokens)
        user, answer = Message("user", "Question"), Message("assistant", "Answer")
        view.show_conversation(conversation(user, answer))
        edited, regenerated = [], []
        view.edit_requested.connect(edited.append)
        view.regenerate_requested.connect(regenerated.append)
        view.activateWindow()
        qt_app.processEvents()
        assert "Edit" not in view.toPlainText()
        assert "Regenerate" not in view.toPlainText()
        for object_name, label, message, received in (
            ("EditMessage", "Edit", user, edited),
            ("RegenerateResponse", "Regenerate", answer, regenerated),
        ):
            button = view.findChild(QToolButton, object_name)
            cursor = next(cursor for item, cursor in view._action_buttons if item is button)
            bar = view.verticalScrollBar()
            bar.setValue(bar.value() + view.cursorRect(cursor).top() - 60)
            qt_app.processEvents()
            assert button.isVisible() and button.isEnabled()
            assert button.iconSize() == QSize(16, 16)
            assert button.size() == QSize(24, 24)
            assert button.toolTip() == button.accessibleName() == label
            assert not button.icon().isNull()
            assert not button.icon().pixmap(16, 16).isNull()
            assert view.anchorAt(button.geometry().center()) == action_url(
                view, "edit" if object_name == "EditMessage" else "regenerate", message.id,
            ).toString()
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)
            button.setFocus()
            QTest.keyClick(button, Qt.Key.Key_Space)
            assert received == [message.id, message.id]
            qt_app.processEvents()
            image = button.grab().toImage()
            assert image.pixelColor(image.width() // 2, image.height() - 1).name().upper() == tokens["accent_strong"]
            QTest.mouseMove(view.viewport(), view.viewport().rect().topLeft())
            QTest.mouseMove(button, button.rect().center())
            qt_app.processEvents()
            image = view.viewport().grab().toImage()
            surface = "user_surface" if object_name == "EditMessage" else "assistant_surface"
            assert image.pixelColor(button.x() + button.width() // 2, button.y() + 1).name() == tokens[surface]
    finally:
        qt_app.setPalette(old_palette)
        qt_app.setStyleSheet(old_qss)


def test_copy_buttons_follow_scroll_resize_and_streaming(view, qt_app):
    messages = [Message("assistant", f"Answer {index}\n" + "long line " * 200) for index in range(3)]
    chat = conversation(*messages)
    view.show_conversation(chat)
    qt_app.processEvents()
    assert len(view._action_buttons) == 4
    assert view.verticalScrollBar().maximum() > 0
    copy_buttons = [(button, cursor) for button, cursor in view._action_buttons
                    if button.property("actionKind") == "copy"]
    for message, (button, cursor) in zip(messages, copy_buttons, strict=True):
        bar = view.verticalScrollBar()
        bar.setValue(bar.value() + view.cursorRect(cursor).top() - 60)
        qt_app.processEvents()
        assert button.isVisible()
        assert button.pos() == view.cursorRect(cursor).topLeft()
        assert view.anchorAt(button.geometry().center()) == action_url(
            view, "copy", message.content,
        ).toString()
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        assert qt_app.clipboard().text() == message.content
    view.resize(400, 300)
    qt_app.processEvents()
    for button, cursor in view._action_buttons:
        assert button.pos() == view.cursorRect(cursor).topLeft()
        assert button.isVisible() == view.viewport().rect().intersects(button.geometry())
    view.begin_stream()
    view.feed("New response " * 50)
    view._flush()
    view.set_tokens(tokens_for("light"))
    qt_app.processEvents()
    assert len(view.findChildren(QToolButton, "CopyResponse")) == 3
    button = view.findChildren(QToolButton, "CopyResponse")[-1]
    button.click()
    assert qt_app.clipboard().text() == messages[-1].content
    view.end_stream(chat)


def test_copy_buttons_are_removed_when_switching_or_clearing(view, qt_app):
    view.show_conversation(conversation(Message("assistant", "First"), Message("assistant", "Second")))
    assert len(view.findChildren(QToolButton, "CopyResponse")) == 2
    view.show_conversation(conversation(Message("user", "Question only")))
    assert not view.findChildren(QToolButton, "CopyResponse")
    view.show_conversation(conversation(Message("assistant", "New answer")))
    assert len(view.findChildren(QToolButton, "CopyResponse")) == 1
    view.clear_chat()
    assert not view.findChildren(QToolButton, "CopyResponse")
    assert not view._action_buttons
    assert not view._icon_actions
    assert not view.findChildren(QToolButton, "EditMessage")
    assert not view.findChildren(QToolButton, "RegenerateResponse")


@pytest.mark.parametrize("mode", ["dark", "light"])
@pytest.mark.parametrize("clear_method", ["new_chat", "empty_conversation"])
def test_chat_icon_spacers_survive_clearing(view, qt_app, mode, clear_method):
    view.set_tokens(tokens_for(mode))
    chat = conversation(Message("user", "Question"), Message("assistant", "Answer"))
    view.show_conversation(chat)
    qt_app.processEvents()
    if clear_method == "new_chat":
        view.clear_chat()
    else:
        view.show_conversation(Conversation())
    view.show_conversation(chat)
    qt_app.processEvents()
    for name in ("chat-action-placeholder", "chat-editor-placeholder"):
        image = view.document().resource(QTextDocument.ResourceType.ImageResource, QUrl(name))
        assert isinstance(image, QImage)
        assert not image.isNull()
        assert all(image.pixelColor(x, y).alpha() == 0
                   for x in range(image.width()) for y in range(image.height()))
    for button, _ in view._action_buttons:
        assert not button.icon().pixmap(16, 16).isNull()


def test_icon_buttons_reappear_after_horizontal_scroll_and_resize(view, qt_app):
    view.show_conversation(conversation(Message("assistant", "```\n" + "x" * 400 + "\n```")))
    qt_app.processEvents()
    for button, _ in view._action_buttons:
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clearFocus()
    bar = view.horizontalScrollBar()
    assert bar.maximum() > 500
    bar.setValue(500)
    view.resize(610, 340)
    qt_app.processEvents()
    assert all(button.isHidden() for button, _ in view._action_buttons), (
        bar.value(), [(button.pos(), button.isHidden()) for button, _ in view._action_buttons],
    )
    bar.setValue(0)
    qt_app.processEvents()
    for button, cursor in view._action_buttons:
        assert button.pos() == view.cursorRect(cursor).topLeft()
        assert view.viewport().rect().intersects(button.geometry())
        assert not button.isHidden()


def test_normal_selection_copy_is_unchanged(view, qt_app):
    view.show_conversation(conversation(Message("assistant", "plain **bold** text")))
    cursor = view.document().find("bold")
    view.setTextCursor(cursor)
    view.copy()
    assert qt_app.clipboard().text() == "bold"


def test_only_latest_assistant_regenerates_and_every_user_can_edit(view):
    messages = [Message("user", "First"), Message("assistant", "One"),
                Message("user", "Second"), Message("assistant", "Two")]
    view.show_conversation(conversation(*messages))
    edited, regenerated = [], []
    view.edit_requested.connect(edited.append)
    view.regenerate_requested.connect(regenerated.append)
    for message in (messages[0], messages[2]):
        activate(view, "edit", message.id)
    activate(view, "regenerate", messages[-1].id)
    assert edited == [messages[0].id, messages[2].id]
    assert regenerated == [messages[-1].id]
    assert ("regenerate", messages[1].id) not in view._actions.values()
    assert len(view.findChildren(QToolButton, "EditMessage")) == 2
    assert len(view.findChildren(QToolButton, "RegenerateResponse")) == 1


@pytest.mark.parametrize("status", ["failed", "stopped"])
def test_partial_and_zero_text_failures_retry_the_user(view, status):
    user = Message("user", "Question")
    assistant = Message("assistant", "Partial")
    assistant.status = status
    chat = conversation(user, assistant)
    view.show_conversation(chat)
    retries = []
    view.retry_requested.connect(retries.append)
    activate(view, "retry", user.id)
    assert ("regenerate", assistant.id) not in view._actions.values()
    chat.messages.pop()
    chat.last_attempt = {"user_message_id": user.id, "status": status}
    view.show_conversation(chat)
    activate(view, "retry", user.id)
    assert retries == [user.id, user.id]
    chat.last_attempt["user_message_id"] = "another-user"
    view.show_conversation(chat)
    assert not any(kind == "retry" for kind, payload in view._actions.values())


@pytest.mark.parametrize("theme_name", ["dark", "light"])
@pytest.mark.parametrize("partial", [False, True])
def test_retry_uses_native_icon_button_with_mouse_keyboard_and_busy_guard(
    view, qt_app, theme_name, partial,
):
    view.set_tokens(tokens_for(theme_name))
    user = Message("user", "Question")
    messages = [user]
    if partial:
        messages.append(Message("assistant", "Partial answer", status="failed"))
    chat = conversation(*messages)
    chat.last_attempt = {"user_message_id": user.id, "status": "failed"}
    view.show_conversation(chat)
    qt_app.processEvents()
    button = view.findChild(QToolButton, "RetryResponse")
    assert button is not None
    assert button.text() == ""
    assert button.toolTip() == button.accessibleName() == "Retry"
    assert button.iconSize() == QSize(16, 16)
    assert button.size() == QSize(24, 24)
    assert not button.icon().pixmap(16, 16).isNull()
    assert "Retry" not in view.toPlainText()
    retries = []
    view.retry_requested.connect(retries.append)
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    button.setFocus()
    QTest.keyClick(button, Qt.Key.Key_Space)
    assert retries == [user.id, user.id]
    view.set_busy(True)
    disabled = view.findChild(QToolButton, "RetryResponse")
    assert not disabled.isEnabled()
    disabled.click()
    assert retries == [user.id, user.id]


def test_busy_and_streaming_block_mutation_but_allow_completed_copy(view, qt_app):
    user, answer = Message("user", "Question"), Message("assistant", "Saved answer")
    chat = conversation(user, answer)
    view.show_conversation(chat)
    edits, regenerations = [], []
    view.edit_requested.connect(edits.append)
    view.regenerate_requested.connect(regenerations.append)
    edit = action_url(view, "edit", user.id)
    regenerate = action_url(view, "regenerate", answer.id)
    view.begin_stream()
    for button, _cursor in view._action_buttons:
        assert button.isEnabled() == (button.property("actionKind") == "copy")
    view.findChild(QToolButton, "EditMessage").click()
    view.findChild(QToolButton, "RegenerateResponse").click()
    view.anchorClicked.emit(edit)
    view.anchorClicked.emit(regenerate)
    activate(view, "copy", answer.content)
    assert qt_app.clipboard().text() == answer.content
    assert not edits and not regenerations
    view.feed("live response")
    view.set_tokens(tokens_for("light"))
    assert view.toPlainText().count("live response") == 1
    assert not any(kind in {"edit", "retry", "regenerate"} for kind, payload in view._actions.values())
    view.end_stream(chat)
    view.set_busy(True)
    assert not any(kind in {"edit", "retry", "regenerate"} for kind, payload in view._actions.values())
    assert not view.findChild(QToolButton, "EditMessage").isEnabled()
    assert not view.findChild(QToolButton, "RegenerateResponse").isEnabled()
    view.set_busy(False)
    assert view.findChild(QToolButton, "EditMessage").isEnabled()
    assert view.findChild(QToolButton, "RegenerateResponse").isEnabled()
    activate(view, "edit", user.id)
    assert edits == [user.id]


def test_busy_blocks_retry_and_stale_links(view):
    user = Message("user", "Question")
    chat = conversation(user)
    chat.last_attempt = {"user_message_id": user.id, "status": "failed"}
    view.show_conversation(chat)
    retry = action_url(view, "retry", user.id)
    retries = []
    view.retry_requested.connect(retries.append)
    view.set_busy(True)
    view.anchorClicked.emit(retry)
    view.set_busy(False)
    view.anchorClicked.emit(retry)
    assert not retries
    activate(view, "retry", user.id)
    assert retries == [user.id]


@pytest.mark.parametrize("status", ["failed", "stopped", "interrupted"])
def test_failed_regeneration_retains_complete_answer_and_can_retry(view, status):
    user, assistant = Message("user", "Question"), Message("assistant", "Original answer")
    chat = conversation(user, assistant)
    chat.last_attempt = {
        "user_message_id": user.id, "replaces_message_id": assistant.id, "status": status,
    }
    view.show_conversation(chat)
    assert ("retry", user.id) in view._actions.values()
    assert ("regenerate", assistant.id) in view._actions.values()
    assert ("copy", "Original answer") in view._actions.values()
    assert assistant.status == "complete"


def test_interrupted_zero_text_attempt_can_retry(view):
    user = Message("user", "Question")
    chat = conversation(user)
    chat.last_attempt = {"user_message_id": user.id, "status": "interrupted"}
    view.show_conversation(chat)
    assert ("retry", user.id) in view._actions.values()


def test_model_supplied_links_cannot_dispatch_actions_or_open_other_schemes(view, monkeypatch):
    opened, edits = [], []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True)
    raw = ('<a href="chat-action:forged">Edit</a> '
           '[attack](chat-action:forged) [file](file:///private) '
           '[safe](https://example.test/path) '
           '[quote](https://example.test/"name="forged)')
    view.show_conversation(conversation(Message("assistant", raw)))
    view.edit_requested.connect(edits.append)
    assert not view.openExternalLinks() and not view.openLinks()
    for href in hrefs(view):
        assert href in view._actions or href.startswith("https://example.test/")
    for url in ("chat-action:forged", "file:///private", "javascript:alert(1)",
                "data:text/html,attack", "https:///missing-host"):
        view.anchorClicked.emit(QUrl(url))
    assert not opened and not edits
    view.anchorClicked.emit(QUrl("https://example.test/path"))
    view.anchorClicked.emit(QUrl("http://example.test/path"))
    assert opened == ["https://example.test/path", "http://example.test/path"]


def test_open_and_clipboard_errors_are_reported(view, monkeypatch):
    errors = []
    view.error.connect(errors.append)
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: False)
    view.anchorClicked.emit(QUrl("https://example.test"))
    assert errors == ["Could not open the link in your browser."]

    class BrokenClipboard:
        def setText(self, text):
            raise RuntimeError("Clipboard unavailable")

    monkeypatch.setattr(QApplication, "clipboard", lambda: BrokenClipboard())
    view.show_conversation(conversation(Message("assistant", "Answer")))
    activate(view, "copy", "Answer")
    assert errors[-1] == "Could not copy to the clipboard: Clipboard unavailable"


def test_find_highlights_rebuilds_without_content_or_selection_changes(view, qt_app):
    chat = conversation(Message("user", "Needle question"), Message("assistant", "needle answer needle"))
    view.show_conversation(chat)
    qt_app.processEvents()
    text = view.toPlainText()
    selection = view.document().find("answer")
    view.setTextCursor(selection)
    counts = []
    view.find_changed.connect(lambda current, total: counts.append((current, total)))
    view.set_find_query("needle")
    assert counts[-1] == (1, 3)
    assert len(view.extraSelections()) == 3
    assert view.toPlainText() == text
    assert view.textCursor().selectedText() == "answer"
    view.find_next()
    assert counts[-1] == (2, 3)
    view.find_previous()
    assert counts[-1] == (1, 3)
    view.find_next()
    view.set_tokens(tokens_for("light"))
    assert len(view.extraSelections()) == 3
    assert counts[-1] == (2, 3)
    assert view.toPlainText() == text
    assert view.find_message(chat.messages[-1].id, "needle")
    assert counts[-1] == (2, 3)
    assert not view.find_message("missing", "needle")
    view.clear_find()
    assert not view.extraSelections()
    assert counts[-1] == (0, 0)


def test_find_survives_flush_theme_and_completion_without_autoscroll(view, qt_app):
    chat = conversation(Message("user", "needle " + "line\n" * 100))
    view.show_conversation(chat)
    qt_app.processEvents()
    view.set_find_query("needle")
    view.verticalScrollBar().setValue(0)
    view.begin_stream()
    view.feed("needle streamed")
    view._flush()
    qt_app.processEvents()
    assert len(view.extraSelections()) == 2
    assert view.verticalScrollBar().value() == 0
    view.set_tokens(tokens_for("light"))
    qt_app.processEvents()
    assert len(view.extraSelections()) == 2
    assert view.verticalScrollBar().value() == 0
    assistant = Message("assistant", "needle streamed")
    assistant.id = "streamed-answer"
    assistant.status = "complete"
    chat.messages.append(assistant)
    view.end_stream(chat)
    assert len(view.extraSelections()) == 2
    assert view.verticalScrollBar().value() == 0


def test_find_bar_contract_and_escape(view):
    view.show_conversation(conversation(Message("assistant", "one one")))
    bar = ChatFindBar(view)
    try:
        assert bar.isHidden()
        bar.open("one")
        assert not bar.isHidden()
        assert bar._count.text() == "1 of 2"
        bar._next.click()
        assert bar._count.text() == "2 of 2"
        bar.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
        assert bar.isHidden()
        assert not view.extraSelections()
        bar.open()
        assert len(view.extraSelections()) == 2
        bar.close_find()
    finally:
        bar.close()
