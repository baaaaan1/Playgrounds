from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
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

    def __init__(self, tokens: dict[str, str], parent=None) -> None:
        super().__init__(parent)
        self._tokens = dict(tokens)
        self._busy = False

        self._frame = QFrame()
        self._frame.setObjectName("Composer")
        self._frame.setProperty("busy", False)

        self._input = ComposerInput()
        self._input.setObjectName("ComposerInput")
        self._input.setPlaceholderText("Tanya apa saja...")
        self._input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._input.setFixedHeight(46)
        self._input.textChanged.connect(self._adjust_height)
        self._input.submitted.connect(self.submitted.emit)

        self._hint = QLabel("Enter kirim  \u00b7  Shift+Enter baris baru")
        self._hint.setObjectName("Hint")

        self.profile_combo = ChevronComboBox(theme.icon_color(tokens))
        self.profile_combo.setMinimumWidth(120)
        self.profile_combo.setMaximumWidth(220)
        self.profile_combo.setToolTip("Active connection profile")
        self.profile_combo.setAccessibleName("Connection profile")
        self.profile_combo.setPlaceholderText("Choose connection...")

        self.model_combo = ChevronComboBox(theme.icon_color(tokens))
        self.model_combo.setEditable(False)
        self.model_combo.setMinimumWidth(160)
        self.model_combo.setMaximumWidth(320)
        self.model_combo.setToolTip("Model untuk percakapan ini")
        self.model_combo.setAccessibleName("Chat model")
        for combo in (self.profile_combo, self.model_combo):
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            combo.setSizeAdjustPolicy(combo.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(12)

        self._send = QPushButton()
        self._send.setObjectName("Send")
        self._send.setFixedSize(36, 36)
        self._send.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send.setToolTip("Kirim (Enter)")
        self._send.clicked.connect(self._on_send_clicked)

        self._stop = QPushButton()
        self._stop.setObjectName("Stop")
        self._stop.setFixedSize(36, 36)
        self._stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop.setToolTip("Hentikan respons (Esc)")
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

        self.refresh_icons(self._tokens)

    def refresh_icons(self, tokens: dict[str, str]) -> None:
        self._tokens = dict(tokens)
        self._send.setIcon(icons.icon("send", tokens["accent_text"], 18))
        self._stop.setIcon(icons.icon("stop", tokens["text"], 16))
        self.profile_combo.set_chevron_color(theme.icon_color(tokens))
        self.model_combo.set_chevron_color(theme.icon_color(tokens))

    def text(self) -> str:
        return self._input.toPlainText()

    def clear(self) -> None:
        self._input.clear()

    def set_text(self, text: str) -> None:
        self._input.setPlainText(text)
        cursor = self._input.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self._input.setTextCursor(cursor)
        self._input.setFocus()

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

    def _adjust_height(self) -> None:
        doc_height = self._input.document().size().height()
        height = int(max(46, min(150, doc_height + 24)))
        if self._input.height() != height:
            self._input.setFixedHeight(height)
