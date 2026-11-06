from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.config import Config
from ..core.credentials import CredentialStore
from ..core.models import Conversation
from ..core.store import ConversationStore
from ..core.updates import can_install, launch_installer
from . import icons, theme
from .chat_controller import ChatController
from .chat_find import ChatFindBar
from .chat_view import ChatView
from .composer import Composer
from .empty_state import EmptyState
from .settings_dialog import SettingsDialog
from .sidebar import Sidebar
from .update_panel import UpdatePanel
from .window_chrome import FramelessWindowMixin, TitleBar


class MainWindow(FramelessWindowMixin, QMainWindow):
    def __init__(
        self, config: Config, store: ConversationStore | None = None,
        credentials: CredentialStore | None = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._tokens = theme.tokens_for(config.theme)
        self._sidebar_splitter_state = None
        self._store = store if store is not None else ConversationStore()
        self._credentials = credentials if credentials is not None else CredentialStore()
        self._controller = ChatController(config, self._store, self._credentials, self)
        self._pending_draft: tuple[str, str] | None = None
        self._draft_timer = QTimer(self)
        self._draft_timer.setSingleShot(True)
        self._draft_timer.setInterval(400)
        self._draft_timer.timeout.connect(self._save_draft)
        self.setup_frameless_window()

        self._build_ui()
        self._wire()
        self._restore_state()
        self._update_panel = None
        self._settings_dialog = None
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._check_updates_automatically)
        if can_install() and self._config.get("updates/automatic"):
            self._update_timer.start(3000)

    def _build_ui(self) -> None:
        self.setWindowTitle("Playgrounds")
        self.setMinimumSize(720, 480)
        self.resize(1180, 780)
        self._apply_window_icon()

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(1)

        self._sidebar = Sidebar(self._tokens)
        self._splitter.addWidget(self._sidebar)

        right = QWidget()
        right.setObjectName("Root")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        right_layout.addWidget(self._build_topbar())

        self._banner = QLabel()
        self._banner.setObjectName("Banner")
        self._banner.setWordWrap(True)
        self._banner.setTextFormat(Qt.TextFormat.PlainText)
        self._banner.setAccessibleName(self.tr("Chat error"))
        self._banner.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._banner_wrap = QWidget()
        banner_layout = QVBoxLayout(self._banner_wrap)
        banner_layout.setContentsMargins(24, 10, 24, 0)
        banner_layout.addWidget(self._banner)
        banner_actions = QHBoxLayout()
        self._banner_retry = QPushButton()
        self._banner_retry.setObjectName("IconButton")
        self._banner_retry.setFixedSize(34, 34)
        self._banner_retry.setIconSize(QSize(18, 18))
        self._banner_retry.setIcon(icons.icon("regenerate", theme.icon_color(self._tokens), 18))
        self._banner_retry.setCursor(Qt.CursorShape.PointingHandCursor)
        self._banner_retry.setToolTip(self.tr("Retry failed response"))
        self._banner_retry.setAccessibleName(self.tr("Retry failed response"))
        self._banner_retry.clicked.connect(self._retry_last_attempt)
        self._banner_settings = QPushButton(self.tr("Connection settings"))
        self._banner_settings.clicked.connect(self._open_settings)
        self._banner_dismiss = QPushButton(self.tr("Dismiss"))
        self._banner_dismiss.setAccessibleName(self.tr("Dismiss error"))
        self._banner_dismiss.clicked.connect(self._hide_banner)
        banner_actions.addWidget(self._banner_retry)
        banner_actions.addWidget(self._banner_settings)
        banner_actions.addStretch(1)
        banner_actions.addWidget(self._banner_dismiss)
        banner_layout.addLayout(banner_actions)
        self._banner_wrap.hide()
        right_layout.addWidget(self._banner_wrap)

        self._stack = QStackedWidget()
        self._empty = EmptyState(self._tokens)
        self._chat = ChatView(self._tokens)
        self._find_bar = ChatFindBar(self._chat)
        right_layout.addWidget(self._find_bar)
        self._stack.addWidget(self._empty)
        self._stack.addWidget(self._chat)
        right_layout.addWidget(self._stack, 1)

        self._composer = Composer(self._tokens)
        self._profile_combo = self._composer.profile_combo
        self._model_combo = self._composer.model_combo
        composer_wrap = QWidget()
        composer_layout = QVBoxLayout(composer_wrap)
        composer_layout.setContentsMargins(24, 10, 24, 18)
        composer_layout.addWidget(self._composer)
        right_layout.addWidget(composer_wrap)

        self._splitter.addWidget(right)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([268, 912])
        shell = QFrame()
        shell.setObjectName("WindowShell")
        layout = QVBoxLayout(shell)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        self._title_bar = TitleBar(self, self._tokens)
        self._sidebar_button = QPushButton()
        self._sidebar_button.setObjectName("IconButton")
        self._sidebar_button.setFixedSize(34, 34)
        self._sidebar_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sidebar_button.setIcon(icons.icon("sidebar", theme.icon_color(self._tokens), 18))
        self._title_bar.layout().insertWidget(0, self._sidebar_button)
        layout.addWidget(self._title_bar)
        layout.addWidget(self._splitter, 1)
        self.setCentralWidget(shell)

    def _build_topbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(58)

        self._title = QLabel(self.tr("New chat"))
        self._title.setObjectName("TopTitle")
        self._title.setTextFormat(Qt.TextFormat.PlainText)
        self._title.setMinimumWidth(100)
        self._title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._meta = QLabel("OpenAI")
        self._meta.setObjectName("TopMeta")
        self._meta.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.addWidget(self._title)
        title_box.addWidget(self._meta)

        self._theme_button = QPushButton()
        self._theme_button.setObjectName("IconButton")
        self._theme_button.setFixedSize(34, 34)
        self._theme_button.setToolTip(self.tr("Switch theme"))
        self._theme_button.setAccessibleName(self.tr("Switch theme"))
        self._theme_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_button.setIcon(icons.icon("theme", theme.icon_color(self._tokens), 18))

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 0, 18, 0)
        layout.setSpacing(12)
        layout.addLayout(title_box, 1)
        layout.addWidget(self._theme_button)
        return bar

    def _wire(self) -> None:
        self._sidebar.new_chat_requested.connect(self._new_chat)
        self._sidebar.conversation_selected.connect(self._open_conversation)
        self._sidebar.delete_requested.connect(self._delete_conversation)
        self._sidebar.settings_requested.connect(self._open_settings)
        self._sidebar.rename_requested.connect(self._rename_conversation)
        self._sidebar.pin_requested.connect(self._pin_conversation)
        self._sidebar.archive_requested.connect(self._archive_conversation)
        self._sidebar.search_result_selected.connect(self._open_search_result)

        self._composer.submitted.connect(self._send)
        self._composer.stop_requested.connect(self._controller.stop)
        self._composer.text_changed.connect(self._on_draft_changed)
        self._empty.suggestion_chosen.connect(self._composer.insert_suggestion)

        self._controller.message_added.connect(self._on_message_added)
        self._controller.conversation_changed.connect(self._show_conversation)
        self._controller.stream_started.connect(self._on_stream_started)
        self._controller.thinking_finished.connect(self._chat.set_thinking_time)
        self._controller.stream_delta.connect(self._chat.feed)
        self._controller.stream_finished.connect(self._on_stream_finished)
        self._controller.error.connect(self._on_error)
        self._chat.edit_requested.connect(self._edit_message)
        self._chat.edit_submitted.connect(self._submit_message_edit)
        self._chat.regenerate_requested.connect(self._regenerate)
        self._chat.retry_requested.connect(self._retry)
        self._chat.error.connect(self._on_error)

        self._model_combo.currentTextChanged.connect(self._on_model_changed)
        self._profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        self._theme_button.clicked.connect(self._toggle_theme)
        self._sidebar_button.clicked.connect(self._toggle_sidebar)

        QShortcut(QKeySequence.StandardKey.New, self, activated=self._new_chat)
        QShortcut(QKeySequence("Ctrl+B"), self, activated=self._toggle_sidebar)
        QShortcut(QKeySequence("Ctrl+,"), self, activated=self._open_settings)
        QShortcut(QKeySequence.StandardKey.Find, self, activated=self._find_bar.open)
        QShortcut(QKeySequence("Esc"), self, activated=self._escape)

    def _restore_state(self) -> None:
        geometry = self._config.geometry()
        if geometry is not None:
            self.restoreGeometry(geometry)
        state = self._config.splitter_state()
        if state is not None:
            self._splitter.restoreState(state)
        self._set_sidebar_visible(self._config.get("sidebar_visible"))
        if self._sidebar.isHidden() and state is not None:
            # Keep the saved sizes until the hidden sidebar is laid out on screen.
            self._sidebar_splitter_state = state

        self._refresh_connection_ui()
        self._refresh_conversations()

        last = str(self._config.get("last_conversation", "") or "")
        if last and self._controller.open(last) and self._controller.conversation is not None:
            if self._controller.conversation.archived:
                self._controller.new_conversation()
                self._show_empty()
            else:
                self._show_conversation(self._controller.conversation)
        else:
            self._show_empty()
            self._composer.focus_input()

    def _toggle_sidebar(self) -> None:
        self._set_sidebar_visible(self._sidebar.isHidden())

    def _set_sidebar_visible(self, visible: bool) -> None:
        if not visible and not self._sidebar.isHidden():
            self._sidebar_splitter_state = self._splitter.saveState()
        self._sidebar.setVisible(visible)
        if visible and self._sidebar_splitter_state is not None:
            self._splitter.restoreState(self._sidebar_splitter_state)
            self._sidebar_splitter_state = None
        action = self.tr("Hide sidebar") if visible else self.tr("Show sidebar")
        self._sidebar_button.setToolTip(
            self.tr("Hide sidebar (Ctrl+B)") if visible else self.tr("Show sidebar (Ctrl+B)")
        )
        self._sidebar_button.setAccessibleName(action)
        self._config.set("sidebar_visible", visible)

    def _refresh_connection_ui(self) -> None:
        profile = self._config.active_profile()
        self._meta.setText(profile.name)
        self._profile_combo.blockSignals(True)
        self._profile_combo.clear()
        for item in self._config.profiles():
            self._profile_combo.addItem(item.name, item.id)
        self._profile_combo.setCurrentIndex(self._profile_combo.findData(profile.id))
        self._profile_combo.blockSignals(False)

        model = profile.model
        models = list(profile.models)
        if model and model not in models:
            models.insert(0, model)
        if not models:
            models = [model or ""]

        combo = self._model_combo
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(models)
        combo.setCurrentIndex(combo.findText(model))
        combo.blockSignals(False)
        combo.setEnabled(not self._controller.busy)
        self._composer.refresh_selector_tooltips()

    def _on_profile_changed(self) -> None:
        profile_id = self._profile_combo.currentData()
        if profile_id and not self._controller.busy:
            self._controller.select_connection(str(profile_id))
            self._refresh_connection_ui()

    def _refresh_conversations(self) -> None:
        self._sidebar.set_conversations(self._controller.list_conversations())

    def _show_empty(self) -> None:
        self._stack.setCurrentWidget(self._empty)
        self._title.setText(self.tr("New chat"))

    def _show_conversation(self, conversation: Conversation) -> None:
        profiles = self._config.profiles()
        profile_id = conversation.profile_id or f"legacy-{conversation.provider}"
        restored = next((p for p in profiles if p.id == profile_id), None)
        unavailable_model = False
        if restored is not None:
            self._config.select_profile(restored.id)
            if conversation.model:
                # The same profile may now point at a different provider or model catalog.
                unavailable_model = bool(restored.models and conversation.model not in restored.models)
                if not unavailable_model:
                    restored.model = conversation.model
                elif restored.model == conversation.model:
                    restored.model = ""
                self._config.save_profile(restored)
        self._refresh_connection_ui()

        self._chat.show_conversation(conversation)
        self._stack.setCurrentWidget(self._chat)
        self._composer.restore_text(conversation.draft_text)
        self._title.setText(
            self.tr("New chat") if not conversation.title or (
                conversation.title == "New chat" and not conversation.title_is_custom
            )
            else conversation.title
        )
        self._composer.focus_input()

        self._sidebar.show_archived(conversation.archived)
        self._sidebar.select(conversation.id)
        self._config.set("last_conversation", conversation.id)
        self._hide_banner()
        if restored is None:
            self._show_connection_unavailable()
        elif unavailable_model:
            self._on_error(self.tr(
                "This chat's previous model is not in this connection's model list. "
                "Select an available model before sending, or refresh the models in Settings."
            ))
        elif conversation.last_attempt.get("status") == "failed":
            error = conversation.last_attempt.get("error")
            if isinstance(error, str) and error:
                self._on_error(error)

    def _show_connection_unavailable(self) -> None:
        self._profile_combo.blockSignals(True)
        self._profile_combo.setCurrentIndex(-1)
        self._profile_combo.blockSignals(False)
        self._model_combo.setEnabled(False)
        self._meta.setText(self.tr("Connection unavailable"))
        self._on_error(self.tr("This chat's connection no longer exists. Select a connection before sending."))

    def show_demo(self) -> None:
        from ..core.models import Message

        conversation = Conversation(title=self.tr("How transformers work"))
        profile = self._config.active_profile()
        conversation.provider = profile.preset
        conversation.profile_id = profile.id
        conversation.model = profile.model
        conversation.add(
            Message(role="user", content=self.tr("Explain how transformers work in simple terms."))
        )
        conversation.add(
            Message(
                role="assistant",
                content=self.tr(
                    "Transformers process all tokens in parallel using **self-attention**.\n\n"
                    "1. Tokens are converted into vectors (embeddings).\n"
                    "2. Attention calculates how tokens relate to each other.\n"
                    "3. A feed-forward network processes each position.\n\n"
                    "A short implementation example:\n\n"
                    "```python\n"
                    "attn = softmax(q @ k.T / sqrt(d)) @ v\n"
                    "```\n\n"
                    "This captures sentence context without recurrent processing."
                ),
            )
        )
        self._controller.use(conversation)
        self._show_conversation(conversation)
        self._refresh_conversations()

    def _new_chat(self) -> None:
        if not self._confirm_discard_edit():
            return
        if not self._flush_draft():
            return
        if self._controller.busy:
            self._controller.stop()
        self._controller.new_conversation()
        self._composer.restore_text("")
        self._find_bar.close_find()
        self._refresh_connection_ui()
        self._chat.clear_chat()
        self._sidebar.clear_selection()
        self._sidebar.show_archived(False)
        self._show_empty()
        self._hide_banner()
        self._config.set("last_conversation", "")
        self._composer.focus_input()

    def _restore_history_selection(self) -> None:
        conversation = self._controller.conversation
        if conversation is None:
            self._sidebar.clear_selection()
        else:
            self._sidebar.select(conversation.id)

    def _open_conversation(self, conversation_id: str) -> bool:
        current = self._controller.conversation
        if (current is None or current.id != conversation_id) and not self._confirm_discard_edit():
            self._restore_history_selection()
            return False
        if not self._flush_draft():
            self._restore_history_selection()
            return False
        if self._controller.busy:
            self._controller.stop()
        if not self._controller.open(conversation_id):
            self._restore_history_selection()
            self._on_error(self.tr("Could not open this chat. Its file may be missing or invalid."))
            return False
        conversation = self._controller.conversation
        if conversation is not None:
            self._show_conversation(conversation)
            return True
        return False

    def _open_search_result(self, conversation_id: str, message_id: str, query: str) -> None:
        if self._open_conversation(conversation_id):
            self._find_bar.open(query)
            self._chat.find_message(message_id, query)

    def _escape(self) -> None:
        if self._chat.editing:
            self._chat.cancel_edit()
        elif not self._find_bar.isHidden():
            self._find_bar.close_find()
        else:
            self._controller.stop()

    def _confirm_discard_edit(self) -> bool:
        if not self._chat.has_unsaved_edit:
            return True
        answer = QMessageBox.question(
            self, self.tr("Discard message edit?"),
            self.tr("This message has unsent changes. Discard them and continue?"),
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Discard:
            self._chat._editor.setFocus()
            return False
        self._chat.cancel_edit()
        return True

    def _on_draft_changed(self, text: str) -> None:
        conversation = self._controller.conversation
        if conversation is None:
            conversation = self._controller.new_conversation()
        conversation.draft_text = text
        self._pending_draft = (conversation.id, text)
        self._config.set("last_conversation", conversation.id)
        self._draft_timer.start()

    def _flush_draft(self) -> bool:
        self._draft_timer.stop()
        if self._pending_draft is not None:
            conversation_id, text = self._pending_draft
            if not self._controller.set_draft(conversation_id, text):
                return False
            self._pending_draft = None
        return self._controller.flush()

    def _save_draft(self) -> None:
        if self._flush_draft():
            self._refresh_conversations()

    def _rename_conversation(self, conversation_id: str) -> None:
        conversation = next((c for c in self._controller.list_conversations() if c.id == conversation_id), None)
        if conversation is None:
            return
        if self._controller.busy and self._controller.conversation.id == conversation_id:
            self._on_error(self.tr("Stop the response before changing this chat."))
            return
        title, accepted = QInputDialog.getText(
            self, self.tr("Rename chat"), self.tr("Chat title:"), text=conversation.title,
        )
        if accepted:
            self._controller.update_metadata(conversation_id, title=title)
            current = self._controller.conversation
            if current is not None and current.id == conversation_id:
                self._title.setText(current.title)
            self._refresh_conversations()

    def _pin_conversation(self, conversation_id: str, pinned: bool) -> None:
        if self._controller.busy and self._controller.conversation.id == conversation_id:
            self._on_error(self.tr("Stop the response before changing this chat."))
            return
        self._controller.update_metadata(conversation_id, pinned=pinned)
        self._refresh_conversations()

    def _archive_conversation(self, conversation_id: str, archived: bool) -> None:
        current = self._controller.conversation
        is_current = current is not None and current.id == conversation_id
        if archived and is_current and not self._confirm_discard_edit():
            return
        if not self._flush_draft():
            return
        if is_current:
            self._controller.stop()
        saved = self._controller.update_metadata(conversation_id, archived=archived)
        self._refresh_conversations()
        if saved and archived and is_current:
            self._new_chat()

    def _can_generate(self) -> bool:
        if self._controller.busy:
            return False
        if self._profile_combo.currentIndex() < 0:
            self._on_error(self.tr("Select a connection before sending this conversation."))
            return False
        return self._flush_draft()

    def _retry(self, user_message_id: str) -> None:
        if not self._chat.editing and self._can_generate():
            self._controller.retry(user_message_id)

    def _retry_last_attempt(self) -> None:
        conversation = self._controller.conversation
        if conversation is not None:
            self._retry(str(conversation.last_attempt.get("user_message_id", "")))

    def _regenerate(self, assistant_message_id: str) -> None:
        if self._chat.editing or not self._can_generate():
            return
        conversation = self._controller.conversation
        if (conversation is None or not conversation.messages
                or conversation.messages[-1].id != assistant_message_id
                or conversation.messages[-1].role != "assistant"):
            return
        answer = QMessageBox.question(
            self, self.tr("Replace response?"),
            self.tr("A successful regeneration will replace this response. The previous response cannot be restored. Continue?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._controller.regenerate(assistant_message_id)

    def _edit_message(self, user_message_id: str) -> None:
        self._chat.begin_edit(user_message_id)

    def _submit_message_edit(self, conversation_id: str, user_message_id: str, text: str) -> None:
        conversation = self._controller.conversation
        if (not self._chat.editing or conversation is None
                or conversation.id != conversation_id or not self._can_generate()):
            return
        self._controller.edit_and_fork(user_message_id, text)

    def _delete_conversation(self, conversation_id: str) -> None:
        target = self._store.load(conversation_id)
        name = target.title if target else self.tr("this chat")
        answer = QMessageBox.question(
            self,
            self.tr("Delete chat"),
            self.tr('Delete "{name}"? This cannot be undone.').format(name=name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        current = self._controller.conversation
        is_current = current is not None and current.id == conversation_id
        if is_current and not self._confirm_discard_edit():
            return

        if not self._flush_draft():
            return

        if is_current and self._controller.busy:
            self._controller.stop()
        try:
            self._controller.delete(conversation_id)
        except OSError:
            self._on_error(self.tr("Could not delete this chat. Try again."))
            return
        self._refresh_conversations()
        if is_current:
            self._new_chat()

    def _send(self) -> None:
        if self._chat.editing:
            self._on_error(self.tr("Send or cancel the message edit before sending a new message."))
            return
        if self._controller.busy:
            return
        if self._profile_combo.currentIndex() < 0:
            self._on_error(self.tr("Select a connection before sending this conversation."))
            return
        text = self._composer.text()
        if not text.strip():
            return
        if not self._controller.send(text):
            return
        self._draft_timer.stop()
        self._pending_draft = None
        self._composer.restore_text("")
        self._stack.setCurrentWidget(self._chat)

    def _on_message_added(self, message) -> None:
        conversation = self._controller.conversation
        if conversation is None:
            return
        self._chat.show_conversation(conversation)
        self._stack.setCurrentWidget(self._chat)
        self._title.setText(
            self.tr("New chat") if not conversation.title or (
                conversation.title == "New chat" and not conversation.title_is_custom
            )
            else conversation.title
        )
        self._refresh_conversations()
        self._config.set("last_conversation", conversation.id)

    def _on_stream_started(self) -> None:
        self._chat.set_busy(True)
        self._composer.set_busy(True)
        self._profile_combo.setEnabled(False)
        self._model_combo.setEnabled(False)
        self._hide_banner()
        self._chat.begin_stream()

    def _on_stream_finished(self, message) -> None:
        focused = QApplication.focusWidget()
        restore_composer_focus = focused is not None and self._composer.isAncestorOf(focused)
        self._chat.set_busy(False)
        self._composer.set_busy(False)
        self._profile_combo.setEnabled(True)
        self._model_combo.setEnabled(True)
        conversation = self._controller.conversation
        self._chat.end_stream(conversation)
        if conversation is not None:
            self._title.setText(
                self.tr("New chat") if not conversation.title or (
                    conversation.title == "New chat" and not conversation.title_is_custom
                )
                else conversation.title
            )
            self._refresh_conversations()
            self._config.set("last_conversation", conversation.id)
        if restore_composer_focus:
            self._composer.focus_input()

    def _on_model_changed(self, text: str) -> None:
        text = text.strip()
        profile = self._config.active_profile()
        profile.model = text
        self._config.save_profile(profile)

    def _on_error(self, message: str) -> None:
        self._composer.set_busy(self._controller.busy)
        self._banner.setText(message)
        self._banner.setTextFormat(Qt.TextFormat.PlainText)
        self._banner.setAccessibleDescription(message)
        conversation = self._controller.conversation
        attempt = conversation.last_attempt if conversation is not None else {}
        self._banner_retry.setVisible(
            not self._controller.busy and bool(attempt.get("user_message_id"))
            and attempt.get("status") in {"failed", "stopped", "interrupted"}
        )
        self._banner_wrap.show()

    def _hide_banner(self) -> None:
        self._banner_wrap.hide()

    def _apply_window_icon(self) -> None:
        self.setWindowIcon(icons.app_icon())

    def _apply_theme(self, name: str) -> None:
        app = QApplication.instance()
        if isinstance(app, QApplication):
            self._tokens = theme.apply(app, name)
        else:
            self._tokens = theme.tokens_for(name)
        icons.clear_cache()
        self._chat.set_tokens(self._tokens)
        self._empty.set_tokens(self._tokens)
        self._composer.refresh_icons(self._tokens)
        self._sidebar.refresh_icons(self._tokens)
        self._sidebar_button.setIcon(icons.icon("sidebar", theme.icon_color(self._tokens), 18))
        self._theme_button.setIcon(icons.icon("theme", theme.icon_color(self._tokens), 18))
        self._banner_retry.setIcon(icons.icon("regenerate", theme.icon_color(self._tokens), 18))
        self._title_bar.refresh_theme(self._tokens)
        self._apply_window_icon()

    def _toggle_theme(self) -> None:
        name = "light" if self._config.theme == "dark" else "dark"
        self._config.theme = name
        self._config.sync()
        self._apply_theme(name)

    def _open_settings(self) -> None:
        previous_theme = self._config.theme
        connection_unavailable = self._profile_combo.currentIndex() < 0
        dialog = SettingsDialog(
            self._config, self._credentials, self._tokens, self,
            connections_editable=not self._controller.busy,
            update_panel=self._updates(),
        )
        self._settings_dialog = dialog
        dialog.install_requested.connect(self._install_update)
        try:
            result = dialog.exec()
        finally:
            self._update_panel.install_requested.disconnect(dialog._request_install)
            self._update_panel.setParent(self)
            self._update_panel.hide()
            self._settings_dialog = None
            dialog.deleteLater()
        if result == QDialog.DialogCode.Accepted or dialog.connections_saved or self._config.theme != previous_theme:
            if self._config.theme != previous_theme:
                self._apply_theme(self._config.theme)
            if dialog.connections_saved:
                self._refresh_connection_ui()
                self._refresh_conversations()
                conversation = self._controller.conversation
                profile_ids = {profile.id for profile in self._config.profiles()}
                missing_profile = conversation is not None and (
                    conversation.profile_id or f"legacy-{conversation.provider}"
                ) not in profile_ids
                if connection_unavailable or missing_profile:
                    self._show_connection_unavailable()

    def _updates(self) -> UpdatePanel:
        if self._update_panel is None:
            self._update_panel = UpdatePanel(self._config, self)
            self._update_panel.hide()
        return self._update_panel

    def _check_updates_automatically(self) -> None:
        if self._config.get("updates/automatic") and self._settings_dialog is None:
            self._updates().check(automatic=True)

    def _install_update(self, path, release) -> None:
        if self._controller.busy:
            QMessageBox.information(self, self.tr("Update"), self.tr("Wait for the response to finish or stop it before installing."))
            return
        if not self._confirm_discard_edit():
            return
        if not self._flush_draft():
            return
        try:
            if not self._config.sync():
                raise OSError(self.tr("Could not save settings. The update was not started."))
        except OSError as exc:
            QMessageBox.warning(self, self.tr("Update failed"), str(exc))
            return
        try:
            launch_installer(path, release)
        except (OSError, ValueError) as exc:
            self._updates().installation_failed(str(exc))
            QMessageBox.warning(self, self.tr("Update failed"), str(exc))
            return
        self._update_panel.client.detach_download()
        if self._settings_dialog is not None:
            self._settings_dialog.accept()
        QApplication.instance().quit()

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self._confirm_discard_edit():
            event.ignore()
            return
        if not self._flush_draft():
            event.ignore()
            return
        self._controller.shutdown()
        if not self._controller.flush():
            event.ignore()
            return
        self._update_timer.stop()
        if self._update_panel is not None:
            self._update_panel.cancel()
        conversation = self._controller.conversation
        if conversation is not None:
            self._config.set("last_conversation", conversation.id)
        self._config.set_geometry(self.saveGeometry())
        self._config.set_splitter_state(
            self._sidebar_splitter_state
            if self._sidebar_splitter_state is not None else self._splitter.saveState()
        )
        self._config.sync()
        super().closeEvent(event)
