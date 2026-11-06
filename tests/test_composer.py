from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt, qInstallMessageHandler
from PyQt6.QtGui import QTextCursor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QWidget

from app.ui import theme
from app.ui.composer import Composer


@pytest.fixture()
def composer(qt_app):
    widget = Composer(theme.tokens_for("dark"))
    widget.profile_combo.addItems(["Connection A", "Connection B"])
    widget.model_combo.addItems(["Model A", "Model B"])
    widget.resize(640, 300)
    widget.show()
    widget.activateWindow()
    widget.focus_input()
    qt_app.processEvents()
    yield widget
    widget.close()


@pytest.mark.parametrize("embedded", [False, True])
def test_construction_does_not_warn_about_tab_order(qt_app, embedded):
    messages = []
    parent = QWidget() if embedded else None
    previous = qInstallMessageHandler(lambda kind, context, message: messages.append(message))
    widget = None
    try:
        widget = Composer(theme.tokens_for("dark"), parent)
    finally:
        qInstallMessageHandler(previous)
        if widget is not None:
            widget.deleteLater()
        if parent is not None:
            parent.deleteLater()
    assert not [message for message in messages if "QWidget::setTabOrder" in message]


@pytest.mark.parametrize("busy", [False, True])
def test_tab_traverses_input_connection_model_and_action(composer, qt_app, busy):
    composer.set_busy(busy)
    composer.focus_input()
    qt_app.processEvents()
    action = composer._stop if busy else composer._send
    widgets = [composer._input, composer.profile_combo, composer.model_combo, action]
    assert composer._input.tabChangesFocus()
    for previous, following in zip(widgets[:-1], widgets[1:], strict=True):
        QTest.keyClick(previous, Qt.Key.Key_Tab)
        assert following.hasFocus()
    for current, previous in zip(reversed(widgets[1:]), reversed(widgets[:-1]), strict=True):
        QTest.keyClick(current, Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier)
        assert previous.hasFocus()
    assert composer.text() == ""


def test_enter_submits_and_shift_enter_inserts_newline(composer):
    submitted = []
    composer.submitted.connect(lambda: submitted.append(True))
    QTest.keyClicks(composer._input, "Draft")
    QTest.keyClick(composer._input, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    assert composer.text() == "Draft\n"
    QTest.keyClick(composer._input, Qt.Key.Key_Return)
    assert submitted == [True]
    assert composer.text() == "Draft\n"


def test_short_multiline_expands_in_pixels_and_shrinks(composer, qt_app):
    composer.set_text("Short")
    qt_app.processEvents()
    assert composer._input.height() == 46
    composer.set_text("First\nSecond\nThird\nFourth")
    qt_app.processEvents()
    assert 46 < composer._input.height() < 150
    assert composer._input.verticalScrollBar().maximum() == 0
    composer.clear()
    qt_app.processEvents()
    assert composer._input.height() == 46


def test_wrapped_paragraph_reflows_after_resize(composer, qt_app):
    composer.resize(900, 300)
    composer.set_text("word " * 65)
    qt_app.processEvents()
    wide_height = composer._input.height()
    assert composer._input.document().blockCount() == 1
    composer.resize(390, 300)
    qt_app.processEvents()
    narrow_height = composer._input.height()
    assert wide_height < narrow_height <= 150
    composer.resize(900, 300)
    qt_app.processEvents()
    assert composer._input.height() == wide_height


@pytest.mark.parametrize("draft", ["line\n" * 100, "word " * 1000])
def test_height_caps_and_shrinks_after_edit(composer, qt_app, draft):
    composer.set_text(draft)
    qt_app.processEvents()
    assert composer._input.height() == 150
    assert composer._input.verticalScrollBar().maximum() > 0
    composer._input.selectAll()
    QTest.keyClicks(composer._input, "Short")
    qt_app.processEvents()
    assert composer._input.height() == 46
    assert composer._input.verticalScrollBar().maximum() == 0


def test_sizing_accounts_for_stylesheet_padding(composer, qt_app):
    composer._input.setStyleSheet("QPlainTextEdit { padding: 10px 12px; border: none; }")
    composer.set_text("First\nSecond\nThird\nFourth")
    qt_app.processEvents()
    assert 46 < composer._input.height() <= 150
    assert composer._input.verticalScrollBar().maximum() == 0


def test_empty_suggestion_is_one_undoable_edit(composer):
    suggestion = "Explain this\nwith examples"
    composer.insert_suggestion(suggestion)
    assert composer.text() == suggestion
    composer._input.undo()
    assert composer.text() == ""
    assert not composer._input.document().isUndoAvailable()
    composer._input.redo()
    assert composer.text() == suggestion


@pytest.mark.parametrize("anchor,position", [(3, 11), (11, 3), (5, 5), (0, 20)])
@pytest.mark.parametrize("keyboard", [False, True])
def test_suggestion_preserves_selected_draft_text_and_undo_history(
    composer, anchor, position, keyboard,
):
    draft = "Original draft\n  end"
    composer._input.insertPlainText(draft)
    cursor = composer._input.textCursor()
    cursor.setPosition(anchor)
    cursor.setPosition(position, QTextCursor.MoveMode.KeepAnchor)
    composer._input.setTextCursor(cursor)
    changes = []
    composer.text_changed.connect(changes.append)

    composer.insert_suggestion("Suggestion\nwith details")
    assert composer.text() == draft + "\n\nSuggestion\nwith details"
    assert changes == [composer.text()]
    assert composer._input.hasFocus()

    if keyboard:
        QTest.keyClick(composer._input, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    else:
        composer._input.undo()
    assert composer.text() == draft
    composer._input.undo()
    assert composer.text() == ""


def test_suggestion_undo_redo_and_new_history_branch(composer):
    composer.set_text("draft")
    composer.insert_suggestion("first")
    composer.insert_suggestion("second")
    composer._input.undo()
    assert composer.text() == "draft\n\nfirst"
    composer._input.redo()
    assert composer.text() == "draft\n\nfirst\n\nsecond"
    composer._input.undo()
    composer._input.undo()
    assert composer.text() == "draft"
    composer._input.insertPlainText("!")
    composer.insert_suggestion("replacement")
    composer._input.undo()
    assert composer.text() == "draft!"
    composer._input.undo()
    assert composer.text() == "draft"


def test_suggestion_undo_after_later_edits_and_redo(composer):
    composer._input.insertPlainText("original draft")
    composer._input.selectAll()
    composer.insert_suggestion("suggestion")
    composer._input.insertPlainText("!")
    composer._input.undo()
    assert composer.text() == "original draft\n\nsuggestion"
    composer._input.undo()
    assert composer.text() == "original draft"
    composer._input.redo()
    composer._input.undo()
    assert composer.text() == "original draft"


def test_native_context_menu_undo_restores_draft(composer):
    composer.set_text("original draft")
    composer._input.selectAll()
    composer.insert_suggestion("suggestion")
    menu = composer._input.createStandardContextMenu()
    undo = next(action for action in menu.actions() if action.objectName() == "edit-undo")
    undo.trigger()
    assert composer.text() == "original draft"
    menu.deleteLater()


def test_empty_suggestion_is_noop(composer):
    composer.set_text("draft")
    composer._input.selectAll()
    composer.insert_suggestion("")
    assert composer.text() == "draft"
    assert composer._input.textCursor().selectedText() == "draft"
    assert not composer._input.document().isUndoAvailable()


def test_focus_property_tracks_only_input(composer, qt_app):
    assert composer._frame.property("inputFocused") is True
    composer.profile_combo.setFocus()
    qt_app.processEvents()
    assert composer._frame.property("inputFocused") is False
    composer.focus_input()
    qt_app.processEvents()
    assert composer._frame.property("inputFocused") is True


def test_combo_tooltips_include_full_current_values_with_stable_names(composer):
    for combo, name, label in (
        (composer.profile_combo, "Connection profile", "Active connection profile"),
        (composer.model_combo, "Chat model", "Model for this chat"),
    ):
        value = "full-current-value/" + "very-long-name-" * 20
        combo.addItem(value)
        combo.setCurrentIndex(combo.count() - 1)
        assert value in combo.toolTip()
        assert label in combo.toolTip()
        assert combo.accessibleName() == name
        combo.setItemText(combo.currentIndex(), "Renamed value")
        assert "Renamed value" in combo.toolTip()
        assert value not in combo.toolTip()
        combo.clear()
        assert combo.toolTip() == label
