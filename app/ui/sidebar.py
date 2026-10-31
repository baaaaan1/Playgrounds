from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
)

from ..core.models import Conversation
from . import icons


class Sidebar(QFrame):
    new_chat_requested = pyqtSignal()
    conversation_selected = pyqtSignal(str)
    delete_requested = pyqtSignal(str)
    settings_requested = pyqtSignal()

    def __init__(self, tokens: dict[str, str], parent=None) -> None:
        super().__init__(parent)
        self._tokens = dict(tokens)
        self.setObjectName("Sidebar")
        self.setMinimumWidth(210)
        self.setMaximumWidth(340)

        header = QHBoxLayout()
        header.setContentsMargins(10, 0, 6, 0)
        wordmark = QLabel("playgrounds")
        wordmark.setObjectName("Wordmark")
        header.addWidget(wordmark)
        header.addStretch(1)

        self._new_button = QPushButton("  New chat")
        self._new_button.setObjectName("NavButton")
        self._new_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new_button.setToolTip("Percakapan baru (Ctrl+N)")
        self._new_button.clicked.connect(self.new_chat_requested.emit)

        section = QLabel("RIWAYAT")
        section.setObjectName("SectionLabel")

        self._list = QListWidget()
        self._list.setObjectName("Navigation")
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._list.setWordWrap(False)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.itemClicked.connect(self._on_item_clicked)
        self._list.customContextMenuRequested.connect(self._on_context_menu)

        self._settings_button = QPushButton("  Settings")
        self._settings_button.setObjectName("NavButton")
        self._settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_button.setToolTip("Pengaturan (Ctrl+,)")
        self._settings_button.clicked.connect(self.settings_requested.emit)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(10)
        layout.addLayout(header)
        layout.addWidget(self._new_button)
        layout.addSpacing(6)
        layout.addWidget(section)
        layout.addWidget(self._list, 1)
        layout.addWidget(self._settings_button)

        self.refresh_icons(self._tokens)

    def refresh_icons(self, tokens: dict[str, str]) -> None:
        self._tokens = dict(tokens)
        self._new_button.setIcon(icons.icon("plus", tokens["text_muted"], 16))
        self._settings_button.setIcon(icons.icon("sliders", tokens["text_muted"], 16))

    def set_conversations(self, conversations: list[Conversation]) -> None:
        selected = self.current_id()
        self._list.blockSignals(True)
        self._list.clear()
        for conversation in conversations:
            item = QListWidgetItem(conversation.title or "New chat")
            item.setData(Qt.ItemDataRole.UserRole, conversation.id)
            item.setToolTip(conversation.model or conversation.provider)
            self._list.addItem(item)
            if conversation.id == selected:
                self._list.setCurrentItem(item)
        self._list.blockSignals(False)

    def select(self, conversation_id: str) -> None:
        self._list.blockSignals(True)
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == conversation_id:
                self._list.setCurrentItem(item)
                break
        else:
            self._list.clearSelection()
        self._list.blockSignals(False)

    def clear_selection(self) -> None:
        self._list.blockSignals(True)
        self._list.clearSelection()
        self._list.setCurrentItem(None)
        self._list.blockSignals(False)

    def current_id(self) -> str | None:
        item = self._list.currentItem()
        if item is None or not item.isSelected():
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return str(value) if value else None

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        conversation_id = item.data(Qt.ItemDataRole.UserRole)
        if conversation_id:
            self.conversation_selected.emit(str(conversation_id))

    def _on_context_menu(self, position: QPoint) -> None:
        item = self._list.itemAt(position)
        if item is None:
            return
        menu = QMenu(self)
        delete_action = menu.addAction(icons.icon("trash", self._tokens["danger"], 16), "Hapus")
        chosen = menu.exec(self._list.mapToGlobal(position))
        if chosen == delete_action:
            conversation_id = item.data(Qt.ItemDataRole.UserRole)
            if conversation_id:
                self.delete_requested.emit(str(conversation_id))
