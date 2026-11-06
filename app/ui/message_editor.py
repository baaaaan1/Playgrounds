from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class MessageEditor(QWidget):
    submitted = pyqtSignal(str)
    canceled = pyqtSignal()

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(parent)
        self._original_text = text
        self.setObjectName("MessageEditor")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        description = QLabel(self.tr(
            "The original chat stays unchanged. Later messages will not be copied.",
        ))
        description.setObjectName("EditHelp")
        description.setWordWrap(True)
        layout.addWidget(description)

        label = QLabel(self.tr("&Message"))
        label.setObjectName("EditLabel")
        self._editor = QPlainTextEdit()
        self._editor.setObjectName("EditMessageInput")
        self._editor.setAccessibleName(self.tr("Message"))
        self._editor.setAccessibleDescription(description.text())
        self._editor.setTabChangesFocus(True)
        self._editor.setFixedHeight(120)
        self._editor.setPlainText(text)
        label.setBuddy(self._editor)
        layout.addWidget(label)
        layout.addWidget(self._editor)

        hint = QLabel(self.tr("Ctrl+Enter to send a copy. Esc to cancel."))
        hint.setObjectName("EditHelp")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        buttons.addStretch()
        self._cancel = QPushButton(self.tr("Cancel"))
        self._cancel.setObjectName("EditCancel")
        self._send = QPushButton(self.tr("Send copy"))
        self._send.setObjectName("EditSend")
        for button in (self._cancel, self._send):
            button.setAutoDefault(False)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            buttons.addWidget(button)
        self._cancel.clicked.connect(self.canceled)
        self._send.clicked.connect(self.submit)
        self._send.setEnabled(bool(text.strip()))
        self._editor.textChanged.connect(
            lambda: self._send.setEnabled(bool(self.text().strip())),
        )
        layout.addLayout(buttons)

        QWidget.setTabOrder(self._editor, self._cancel)
        QWidget.setTabOrder(self._cancel, self._send)
        self.setFocusProxy(self._editor)
        for shortcut in ("Ctrl+Return", "Ctrl+Enter"):
            QShortcut(
                QKeySequence(shortcut), self, activated=self.submit,
                context=Qt.ShortcutContext.WidgetWithChildrenShortcut,
            )

    def text(self) -> str:
        return self._editor.toPlainText()

    @property
    def dirty(self) -> bool:
        return self.text() != self._original_text

    def submit(self) -> None:
        if self.text().strip():
            self.submitted.emit(self.text())
        else:
            self._editor.setFocus()
