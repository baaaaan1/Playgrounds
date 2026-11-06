from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from .chat_view import ChatView


class ChatFindBar(QWidget):
    """Non-modal transcript search; the transcript owns matches and highlights."""

    closed = pyqtSignal()

    def __init__(self, view: ChatView, parent=None) -> None:
        super().__init__(parent)
        self._view = view
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        self._query = QLineEdit(self)
        self._query.setPlaceholderText(self.tr("Find in chat"))
        self._query.setAccessibleName(self.tr("Find in chat"))
        self._count = QLabel(self)
        self._count.setTextFormat(Qt.TextFormat.PlainText)
        self._previous = QPushButton(self.tr("Previous"), self)
        self._next = QPushButton(self.tr("Next"), self)
        self._close = QPushButton(self.tr("Close"), self)
        self._previous.setAccessibleName(self.tr("Previous match"))
        self._next.setAccessibleName(self.tr("Next match"))
        self._close.setAccessibleName(self.tr("Close find"))
        layout.addWidget(self._query, 1)
        layout.addWidget(self._count)
        layout.addWidget(self._previous)
        layout.addWidget(self._next)
        layout.addWidget(self._close)
        self._query.textChanged.connect(view.set_find_query)
        self._query.returnPressed.connect(self._return_pressed)
        self._previous.clicked.connect(view.find_previous)
        self._next.clicked.connect(view.find_next)
        self._close.clicked.connect(self.close_find)
        view.find_changed.connect(self._update_count)
        self._update_count(0, 0)
        self.hide()

    def open(self, query: str = "") -> None:
        self.show()
        if query:
            self._query.setText(query)
        self._view.set_find_query(self._query.text())
        self._query.setFocus()
        self._query.selectAll()

    def close_find(self) -> None:
        self.hide()
        self._view.clear_find()
        self._view.setFocus()
        self.closed.emit()

    def _return_pressed(self) -> None:
        if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
            self._view.find_previous()
        else:
            self._view.find_next()

    def _update_count(self, current: int, total: int) -> None:
        self._count.setText(self.tr("{current} of {total}").format(current=current, total=total))
        self._previous.setEnabled(total > 0)
        self._next.setEnabled(total > 0)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close_find()
            event.accept()
            return
        super().keyPressEvent(event)
