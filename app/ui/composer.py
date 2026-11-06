from __future__ import annotations

from math import ceil

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QResizeEvent, QTextCursor
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import icons, theme
from .widgets import ChevronComboBox


class ComposerInput(QPlainTextEdit):
    submitted = pyqtSignal()
    resized = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setTabChangesFocus(True)

    def insert_suggestion(self, text: str) -> None:
        if not text:
            return
        document = self.document()
        cursor = self.textCursor()
        cursor.beginEditBlock()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(("\n\n" if not document.isEmpty() else "") + text)
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.resized.emit()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        is_enter = event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        if is_enter and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.submitted.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class Composer(QWidget):
    submitted = pyqtSignal()
    stop_requested = pyqtSignal()
    text_changed = pyqtSignal(str)

    def __init__(self, tokens: dict[str, str], parent=None) -> None:
        super().__init__(parent)
        self._tokens = dict(tokens)
        self._busy = False
        self._adjusting_height = False

        self._frame = QFrame()
        self._frame.setObjectName("Composer")
        self._frame.setProperty("busy", False)
        self._frame.setProperty("inputFocused", False)

        self._input = ComposerInput()
        self._input.setObjectName("ComposerInput")
        self._input.setPlaceholderText(self.tr("Ask anything..."))
        self._input.setAccessibleName(self.tr("Message"))
        self._input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._input.setFixedHeight(46)
        self._input.installEventFilter(self)
        self._input.textChanged.connect(self._adjust_height)
        self._input.resized.connect(self._adjust_height)
        self._input.document().documentLayout().documentSizeChanged.connect(self._adjust_height)
        self._input.textChanged.connect(lambda: self.text_changed.emit(self.text()))
        self._input.submitted.connect(self.submitted.emit)

        self._hint = QLabel(self.tr("Enter to send  \u00b7  Shift+Enter for a new line"))
        self._hint.setObjectName("Hint")
        self._hint.setWordWrap(True)

        self.profile_combo = ChevronComboBox(theme.icon_color(tokens))
        self.profile_combo.setMinimumWidth(120)
        self.profile_combo.setMaximumWidth(220)
        self.profile_combo.setToolTip(self.tr("Active connection profile"))
        self.profile_combo.setAccessibleName(self.tr("Connection profile"))
        self.profile_combo.setPlaceholderText(self.tr("Choose connection..."))

        self.model_combo = ChevronComboBox(theme.icon_color(tokens))
        self.model_combo.setEditable(False)
        self.model_combo.setMinimumWidth(160)
        self.model_combo.setMaximumWidth(320)
        self.model_combo.setToolTip(self.tr("Model for this chat"))
        self.model_combo.setAccessibleName(self.tr("Chat model"))
        for combo in (self.profile_combo, self.model_combo):
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            combo.setSizeAdjustPolicy(combo.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(8)
            combo.currentTextChanged.connect(
                self.refresh_selector_tooltips
            )

        self._send = QPushButton()
        self._send.setObjectName("Send")
        self._send.setFixedSize(36, 36)
        self._send.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send.setToolTip(self.tr("Send (Enter)"))
        self._send.setAccessibleName(self.tr("Send message"))
        self._send.clicked.connect(self._on_send_clicked)

        self._stop = QPushButton()
        self._stop.setObjectName("Stop")
        self._stop.setFixedSize(36, 36)
        self._stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop.setToolTip(self.tr("Stop response (Esc)"))
        self._stop.setAccessibleName(self.tr("Stop response"))
        self._stop.clicked.connect(self.stop_requested.emit)
        self._stop.hide()

        footer = QHBoxLayout()
        footer.setContentsMargins(12, 4, 8, 8)
        footer.setSpacing(8)
        footer.addWidget(self.profile_combo, 1)
        footer.addWidget(self.model_combo, 2)
        footer.addStretch(1)
        footer.addWidget(self._send)
        footer.addWidget(self._stop)

        inner = QVBoxLayout(self._frame)
        inner.setContentsMargins(0, 2, 0, 0)
        inner.setSpacing(0)
        inner.addWidget(self._input)
        inner.addLayout(footer)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        outer.addWidget(self._frame)
        outer.addWidget(self._hint)

        QWidget.setTabOrder(self._input, self.profile_combo)
        QWidget.setTabOrder(self.profile_combo, self.model_combo)
        QWidget.setTabOrder(self.model_combo, self._send)
        QWidget.setTabOrder(self._send, self._stop)

        self.refresh_icons(self._tokens)

    def refresh_icons(self, tokens: dict[str, str]) -> None:
        self._tokens = dict(tokens)
        self._send.setIcon(icons.icon("send", tokens["accent_text"], 18))
        self._stop.setIcon(icons.icon("stop", tokens["text"], 16))
        self.profile_combo.set_chevron_color(theme.icon_color(tokens))
        self.model_combo.set_chevron_color(theme.icon_color(tokens))
        self.refresh_selector_tooltips()

    def refresh_selector_tooltips(self) -> None:
        for combo, label in (
            (self.profile_combo, self.tr("Active connection profile")),
            (self.model_combo, self.tr("Model for this chat")),
        ):
            value = combo.currentText()
            combo.setToolTip(self.tr("{label}\n{value}").format(label=label, value=value) if value else label)

    def text(self) -> str:
        return self._input.toPlainText()

    def clear(self) -> None:
        self._input.clear()

    def insert_suggestion(self, text: str) -> None:
        self._input.insert_suggestion(text)
        self.focus_input()

    def set_text(self, text: str) -> None:
        self._input.setPlainText(text)
        cursor = self._input.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self._input.setTextCursor(cursor)
        self._input.setFocus()

    def restore_text(self, text: str) -> None:
        self._input.blockSignals(True)
        self.set_text(text)
        self._input.blockSignals(False)
        self._adjust_height()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._send.setVisible(not busy)
        self._stop.setVisible(busy)
        self._input.setReadOnly(busy)
        self._frame.setProperty("busy", busy)
        style = self._frame.style()
        style.unpolish(self._frame)
        style.polish(self._frame)

    def focus_input(self) -> None:
        self._input.setFocus()

    def _on_send_clicked(self) -> None:
        if not self._busy:
            self.submitted.emit()

    def eventFilter(self, watched, event: QEvent) -> bool:
        if watched is self._input and event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            self._frame.setProperty("inputFocused", event.type() == QEvent.Type.FocusIn)
            style = self._frame.style()
            style.unpolish(self._frame)
            style.polish(self._frame)
            self._frame.update()
        return super().eventFilter(watched, event)

    def _adjust_height(self) -> None:
        if self._adjusting_height:
            return
        self._adjusting_height = True
        try:
            document = self._input.document()
            layout = document.documentLayout()
            # Plain-text document size is in paragraphs; block bounds are pixels.
            height = document.documentMargin() + self._input.height() - self._input.viewport().height()
            block = document.begin()
            while block.isValid() and height < 150:
                height += layout.blockBoundingRect(block).height()
                block = block.next()
            # Qt needs a cursor-clearance pixel to avoid a spurious scroll step.
            height = max(46, min(150, ceil(height) + 1))
            if self._input.height() != height:
                self._input.setFixedHeight(height)
        finally:
            self._adjusting_height = False
