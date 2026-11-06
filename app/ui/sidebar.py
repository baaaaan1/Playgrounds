from __future__ import annotations

from html import escape

from PyQt6.QtCore import QEvent, QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QStyledItemDelegate,
    QVBoxLayout,
)

from ..core.models import Conversation
from . import icons


class _SearchResultDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index) -> None:
        super().initStyleOption(option, index)
        snippet = index.data(Qt.ItemDataRole.UserRole + 4)
        if snippet:
            title = index.data(Qt.ItemDataRole.UserRole + 3)
            # Let Qt size, elide and paint both lines with the native selection style.
            option.text = self.displayText(f"{title}\n{snippet}", option.locale)


class Sidebar(QFrame):
    new_chat_requested = pyqtSignal()
    conversation_selected = pyqtSignal(str)
    delete_requested = pyqtSignal(str)
    settings_requested = pyqtSignal()
    rename_requested = pyqtSignal(str)
    pin_requested = pyqtSignal(str, bool)
    archive_requested = pyqtSignal(str, bool)
    search_result_selected = pyqtSignal(str, str, str)

    def __init__(self, tokens: dict[str, str], parent=None) -> None:
        super().__init__(parent)
        self._tokens = dict(tokens)
        self._conversations: dict[str, Conversation] = {}
        self._selection: tuple[str, str] | None = None
        self._showing_archived = False
        self.setObjectName("Sidebar")
        self.setMinimumWidth(210)
        self.setMaximumWidth(340)

        self._new_button = QPushButton("  " + self.tr("New chat"))
        self._new_button.setObjectName("NavButton")
        self._new_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new_button.setToolTip(self.tr("New chat (Ctrl+N)"))
        self._new_button.clicked.connect(self.new_chat_requested.emit)

        self._section = QLabel(self.tr("HISTORY"))
        self._section.setObjectName("SectionLabel")

        self._archived_button = QPushButton(self.tr("Archived"))
        self._archived_button.setObjectName("ArchiveNavigation")
        self._archived_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._archived_button.setAccessibleName(self.tr("Archived chats"))
        self._archived_button.clicked.connect(lambda: self.show_archived(not self._showing_archived))

        self._search = QLineEdit()
        self._search.setPlaceholderText(self.tr("Search chats..."))
        self._search.setAccessibleName(self.tr("Search chat titles and messages"))
        self._search.setClearButtonEnabled(True)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self._render_conversations)
        self._search.textChanged.connect(self._on_search_changed)

        self._status = QLabel()
        self._status.setObjectName("HistoryStatus")
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        self._status.setWordWrap(True)
        self._clear_search_button = QPushButton(self.tr("Clear search"))
        self._clear_search_button.setObjectName("ClearSearch")
        self._clear_search_button.setAccessibleName(self.tr("Clear chat search"))
        self._clear_search_button.clicked.connect(self._clear_search)
        self._clear_search_button.hide()

        self._list = QListWidget()
        self._list.setObjectName("Navigation")
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._list.setWordWrap(False)
        self._list.setItemDelegate(_SearchResultDelegate(self._list))
        self._list.setAccessibleName(self.tr("Chat history"))
        self._list.installEventFilter(self)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.itemClicked.connect(self._on_item_clicked)
        self._list.currentItemChanged.connect(self._on_current_item_changed)
        self._list.customContextMenuRequested.connect(self._on_context_menu)

        self._settings_button = QPushButton("  " + self.tr("Settings"))
        self._settings_button.setObjectName("NavButton")
        self._settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_button.setToolTip(self.tr("Settings (Ctrl+,)"))
        self._settings_button.clicked.connect(self.settings_requested.emit)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(10)
        layout.addWidget(self._new_button)
        layout.addSpacing(6)
        history_header = QVBoxLayout()
        history_header.setSpacing(6)
        history_header.addWidget(self._section)
        history_header.addWidget(self._archived_button)
        layout.addLayout(history_header)
        layout.addWidget(self._search)
        search_status = QHBoxLayout()
        search_status.addWidget(self._status, 1)
        search_status.addWidget(self._clear_search_button)
        layout.addLayout(search_status)
        layout.addWidget(self._list, 1)
        layout.addWidget(self._settings_button)

        self.show_archived(False)
        self.refresh_icons(self._tokens)

    def eventFilter(self, watched, event) -> bool:
        if watched is self._list and event.type() == QEvent.Type.KeyPress:
            item = self._list.currentItem()
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if item is not None:
                    self._on_item_clicked(item)
                return True
            if event.key() == Qt.Key.Key_Menu or (
                event.key() == Qt.Key.Key_F10
                and event.modifiers() & Qt.KeyboardModifier.ShiftModifier
            ):
                if item is not None:
                    self._on_context_menu(self._list.visualItemRect(item).center())
                return True
        return super().eventFilter(watched, event)

    def _on_search_changed(self, text: str) -> None:
        self._clear_search_button.setVisible(bool(text.strip()))
        self._search_timer.start()

    def _clear_search(self) -> None:
        self._search.clear()
        self._render_conversations()
        self._search.setFocus()

    def refresh_icons(self, tokens: dict[str, str]) -> None:
        self._tokens = dict(tokens)
        self._new_button.setIcon(icons.icon("plus", tokens["text_muted"], 16))
        self._settings_button.setIcon(icons.icon("sliders", tokens["text_muted"], 16))

    def set_conversations(self, conversations: list[Conversation]) -> None:
        self._conversations = {conversation.id: conversation for conversation in conversations}
        self._render_conversations()

    def _render_conversations(self) -> None:
        self._search_timer.stop()
        query = self._search.text().strip()
        folded_query = query.casefold()
        scroll = self._list.verticalScrollBar().value()
        blocked = self._list.blockSignals(True)
        self._list.clear()
        selected_item = fallback_item = None
        conversations = sorted(
            self._conversations.values(),
            key=lambda conversation: (not conversation.pinned, -conversation.updated_at),
        )
        for conversation in conversations:
            if conversation.archived != self._showing_archived:
                continue
            title = (
                self.tr("New chat")
                if not conversation.title or (
                    conversation.title == "New chat" and not conversation.title_is_custom
                ) else conversation.title
            )
            rows = []
            if not query or folded_query in title.casefold():
                rows.append(("", ""))
            if query:
                for message in conversation.messages:
                    if folded_query not in message.content.casefold():
                        continue
                    content = " ".join(message.content.split())
                    start = max(0, content.casefold().find(folded_query) - 45)
                    end = start + max(120, len(query) + 45)
                    snippet = (
                        ("..." if start else "") + content[start:end]
                        + ("..." if end < len(content) else "")
                    )
                    rows.append((message.id, snippet))
            for message_id, snippet in rows:
                text = self.tr("{title}: {snippet}").format(title=title, snippet=snippet) if message_id else title
                if conversation.pinned:
                    text = self.tr("Pinned: {title}").format(title=text)
                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, conversation.id)
                item.setData(Qt.ItemDataRole.UserRole + 1, message_id)
                item.setData(Qt.ItemDataRole.UserRole + 2, query)
                item.setData(
                    Qt.ItemDataRole.UserRole + 3,
                    self.tr("Pinned: {title}").format(title=title) if conversation.pinned else title,
                )
                item.setData(Qt.ItemDataRole.UserRole + 4, snippet)
                item.setData(Qt.ItemDataRole.AccessibleTextRole, text)
                tooltip = [title, conversation.model or conversation.provider]
                if conversation.pinned:
                    tooltip.append(self.tr("Pinned"))
                if snippet:
                    tooltip.append(snippet)
                tooltip_html = "<qt>" + "<br>".join(escape(part) for part in tooltip) + "</qt>"
                item.setToolTip(tooltip_html)
                self._list.addItem(item)
                if self._selection and conversation.id == self._selection[0]:
                    if fallback_item is None:
                        fallback_item = item
                    if message_id == self._selection[1]:
                        selected_item = item
        selected_item = selected_item if selected_item is not None else fallback_item
        if selected_item is not None:
            self._list.setCurrentItem(selected_item)
            self._on_current_item_changed(selected_item)
        self._list.doItemsLayout()
        self._list.verticalScrollBar().setValue(scroll)
        self._list.blockSignals(blocked)
        count = self._list.count()
        if query:
            count_text = (
                self.tr("1 search result") if count == 1
                else self.tr("{count} search results").format(count=count)
            )
            status = count_text if count else self.tr("No search results.")
        else:
            count_text = (
                self.tr("1 chat") if count == 1
                else self.tr("{count} chats").format(count=count)
            )
            status = count_text if count else (
                self.tr("No archived chats.") if self._showing_archived
                else self.tr("No chats yet.")
            )
        self._status.setText(status)
        self._status.setAccessibleName(status)
        self._status.setAccessibleDescription(count_text)
        self._list.setAccessibleDescription(count_text)

    def show_archived(self, archived: bool) -> None:
        self._showing_archived = archived
        self._section.setText(self.tr("ARCHIVED") if archived else self.tr("HISTORY"))
        self._archived_button.setText(
            self.tr("Back") if archived else self.tr("Open archive")
        )
        description = (
            self.tr("Return to chat history in this sidebar.") if archived
            else self.tr("Open archived chats in this sidebar.")
        )
        self._archived_button.setAccessibleName(
            self.tr("Back to history") if archived else self.tr("Open archived chats")
        )
        self._archived_button.setToolTip(description)
        self._archived_button.setAccessibleDescription(description)
        self._list.setAccessibleName(self.tr("Archived chats") if archived else self.tr("Chat history"))
        self._render_conversations()

    def _on_current_item_changed(self, item: QListWidgetItem | None, previous=None) -> None:
        if item is not None:
            self._selection = (
                str(item.data(Qt.ItemDataRole.UserRole)),
                str(item.data(Qt.ItemDataRole.UserRole + 1) or ""),
            )

    def select(self, conversation_id: str) -> None:
        if self.current_id() == conversation_id:
            return
        self._selection = (conversation_id, "")
        self._list.blockSignals(True)
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == conversation_id:
                self._list.setCurrentItem(item)
                break
        else:
            self._list.clearSelection()
            self._list.setCurrentItem(None)
        self._list.blockSignals(False)

    def clear_selection(self) -> None:
        self._selection = None
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
            self._on_current_item_changed(item)
            message_id = item.data(Qt.ItemDataRole.UserRole + 1)
            if message_id:
                self.search_result_selected.emit(
                    str(conversation_id), str(message_id),
                    str(item.data(Qt.ItemDataRole.UserRole + 2)),
                )
            else:
                self.conversation_selected.emit(str(conversation_id))

    def _on_context_menu(self, position: QPoint) -> None:
        item = self._list.itemAt(position)
        if item is None:
            return
        conversation_id = str(item.data(Qt.ItemDataRole.UserRole))
        conversation = self._conversations.get(conversation_id)
        if conversation is None:
            return
        pinned, archived = conversation.pinned, conversation.archived
        menu = QMenu(self)
        rename_action = menu.addAction(self.tr("Rename"))
        pin_action = menu.addAction(self.tr("Unpin") if pinned else self.tr("Pin"))
        archive_action = menu.addAction(self.tr("Unarchive") if archived else self.tr("Archive"))
        menu.addSeparator()
        delete_action = menu.addAction(icons.icon("trash", self._tokens["danger"], 16), self.tr("Delete"))
        chosen = menu.exec(self._list.viewport().mapToGlobal(position))
        if chosen == rename_action:
            self.rename_requested.emit(conversation_id)
        elif chosen == pin_action:
            self.pin_requested.emit(conversation_id, not pinned)
        elif chosen == archive_action:
            self.archive_requested.emit(conversation_id, not archived)
        elif chosen == delete_action:
            self.delete_requested.emit(conversation_id)
        menu.deleteLater()
