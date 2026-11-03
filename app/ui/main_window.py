from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
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
from . import icons, theme
from .chat_controller import ChatController
from .chat_view import ChatView
from .composer import Composer
from .empty_state import EmptyState
from .settings_dialog import SettingsDialog
from .sidebar import Sidebar
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
        self.setup_frameless_window()

        self._banner_timer = QTimer(self)
        self._banner_timer.setSingleShot(True)
        self._banner_timer.setInterval(12_000)
        self._banner_timer.timeout.connect(self._hide_banner)

        self._build_ui()
        self._wire()
        self._restore_state()

    def _build_ui(self) -> None:
        self.setWindowTitle("Playgrounds")
        self.setMinimumSize(880, 560)
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
        self._banner_wrap = QWidget()
        banner_layout = QVBoxLayout(self._banner_wrap)
        banner_layout.setContentsMargins(24, 10, 24, 0)
        banner_layout.addWidget(self._banner)
        self._banner_wrap.hide()
        right_layout.addWidget(self._banner_wrap)

        self._stack = QStackedWidget()
        self._empty = EmptyState(self._tokens)
        self._chat = ChatView(self._tokens)
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

        self._title = QLabel("New chat")
        self._title.setObjectName("TopTitle")
        self._title.setTextFormat(Qt.TextFormat.PlainText)
        self._title.setMinimumWidth(100)
        self._title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._meta = QLabel("OpenAI")
        self._meta.setObjectName("TopMeta")

        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.addWidget(self._title)
        title_box.addWidget(self._meta)

        self._theme_button = QPushButton()
        self._theme_button.setObjectName("IconButton")
        self._theme_button.setFixedSize(34, 34)
        self._theme_button.setToolTip("Ganti tema")
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

        self._composer.submitted.connect(self._send)
        self._composer.stop_requested.connect(self._controller.stop)
        self._empty.suggestion_chosen.connect(self._composer.set_text)

        self._controller.message_added.connect(self._on_message_added)
        self._controller.stream_started.connect(self._on_stream_started)
        self._controller.thinking_finished.connect(self._chat.set_thinking_time)
        self._controller.stream_delta.connect(self._chat.feed)
        self._controller.stream_finished.connect(self._on_stream_finished)
        self._controller.error.connect(self._on_error)

        self._model_combo.currentTextChanged.connect(self._on_model_changed)
        self._profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        self._theme_button.clicked.connect(self._toggle_theme)
        self._sidebar_button.clicked.connect(self._toggle_sidebar)

        QShortcut(QKeySequence.StandardKey.New, self, activated=self._new_chat)
        QShortcut(QKeySequence("Ctrl+B"), self, activated=self._toggle_sidebar)
        QShortcut(QKeySequence("Ctrl+,"), self, activated=self._open_settings)
        QShortcut(QKeySequence("Esc"), self, activated=self._controller.stop)

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
        action = "Hide sidebar" if visible else "Show sidebar"
        self._sidebar_button.setToolTip(f"{action} (Ctrl+B)")
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
        combo.setCurrentText(model)
        combo.blockSignals(False)
        combo.setEnabled(not self._controller.busy)

    def _on_profile_changed(self) -> None:
        profile_id = self._profile_combo.currentData()
        if profile_id and not self._controller.busy:
            self._config.select_profile(str(profile_id))
            self._refresh_connection_ui()

    def _refresh_conversations(self) -> None:
        self._sidebar.set_conversations(self._store.list())

    def _show_empty(self) -> None:
        self._stack.setCurrentWidget(self._empty)
        self._title.setText("New chat")

    def _show_conversation(self, conversation: Conversation) -> None:
        profiles = self._config.profiles()
        profile_id = conversation.profile_id or f"legacy-{conversation.provider}"
        restored = next((p for p in profiles if p.id == profile_id), None)
        if restored is not None:
            self._config.select_profile(restored.id)
            if conversation.model:
                restored.model = conversation.model
                self._config.save_profile(restored)
        self._refresh_connection_ui()

        self._chat.show_conversation(conversation)
        self._stack.setCurrentWidget(self._chat)
        self._title.setText(conversation.title or "New chat")
        self._composer.focus_input()

        self._sidebar.select(conversation.id)
        self._config.set("last_conversation", conversation.id)
        self._hide_banner()
        if restored is None:
            self._show_connection_unavailable()

    def _show_connection_unavailable(self) -> None:
        self._profile_combo.blockSignals(True)
        self._profile_combo.setCurrentIndex(-1)
        self._profile_combo.blockSignals(False)
        self._model_combo.setEnabled(False)
        self._meta.setText("Connection unavailable")
        self._on_error("This chat's connection no longer exists. Select a connection before sending.")

    def show_demo(self) -> None:
        from ..core.models import Message

        conversation = Conversation(title="Cara kerja transformer")
        profile = self._config.active_profile()
        conversation.provider = profile.preset
        conversation.profile_id = profile.id
        conversation.model = profile.model
        conversation.add(
            Message(role="user", content="Jelaskan cara kerja transformer secara sederhana.")
        )
        conversation.add(
            Message(
                role="assistant",
                content=(
                    "Transformer memproses semua token secara paralel dengan **self-attention**.\n\n"
                    "1. Token diubah menjadi vektor (embedding).\n"
                    "2. Attention menghitung relevansi antar token.\n"
                    "3. Feed-forward network memproses tiap posisi.\n\n"
                    "Contoh implementasi singkat:\n\n"
                    "```python\n"
                    "attn = softmax(q @ k.T / sqrt(d)) @ v\n"
                    "```\n\n"
                    "Hasilnya konteks kalimat ditangkap tanpa perlu urutan rekuren."
                ),
            )
        )
        self._controller.use(conversation)
        self._show_conversation(conversation)
        self._refresh_conversations()

    def _new_chat(self) -> None:
        if self._controller.busy:
            self._controller.stop()
        self._controller.new_conversation()
        self._refresh_connection_ui()
        self._chat.clear_chat()
        self._sidebar.clear_selection()
        self._show_empty()
        self._hide_banner()
        self._config.set("last_conversation", "")
        self._composer.focus_input()

    def _open_conversation(self, conversation_id: str) -> None:
        if self._controller.busy:
            self._controller.stop()
        if not self._controller.open(conversation_id):
            return
        conversation = self._controller.conversation
        if conversation is not None:
            self._show_conversation(conversation)

    def _delete_conversation(self, conversation_id: str) -> None:
        target = self._store.load(conversation_id)
        name = target.title if target else "percakapan ini"
        answer = QMessageBox.question(
            self,
            "Hapus percakapan",
            f'Hapus "{name}"? Tindakan ini tidak bisa dibatalkan.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        current = self._controller.conversation
        is_current = current is not None and current.id == conversation_id
        if is_current and self._controller.busy:
            self._controller.stop()
        self._controller.delete(conversation_id)
        self._refresh_conversations()
        if is_current:
            self._new_chat()

    def _send(self) -> None:
        if self._controller.busy:
            return
        if self._profile_combo.currentIndex() < 0:
            self._on_error("Select a connection before sending this conversation.")
            return
        text = self._composer.text()
        if not text.strip():
            return
        self._controller.send(text)
        if not self._controller.busy:
            return
        self._composer.clear()
        self._stack.setCurrentWidget(self._chat)
        self._hide_banner()

    def _on_message_added(self, message) -> None:
        conversation = self._controller.conversation
        if conversation is None:
            return
        self._chat.show_conversation(conversation)
        self._stack.setCurrentWidget(self._chat)
        self._title.setText(conversation.title or "New chat")
        self._refresh_conversations()
        self._config.set("last_conversation", conversation.id)

    def _on_stream_started(self) -> None:
        self._composer.set_busy(True)
        self._profile_combo.setEnabled(False)
        self._model_combo.setEnabled(False)
        self._hide_banner()
        self._chat.begin_stream()

    def _on_stream_finished(self, message) -> None:
        self._composer.set_busy(False)
        self._profile_combo.setEnabled(True)
        self._model_combo.setEnabled(True)
        conversation = self._controller.conversation
        self._chat.end_stream(conversation)
        if conversation is not None:
            self._title.setText(conversation.title or "New chat")
            self._refresh_conversations()
            self._config.set("last_conversation", conversation.id)
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
        self._banner_wrap.show()
        self._banner_timer.start()

    def _hide_banner(self) -> None:
        self._banner_timer.stop()
        self._banner_wrap.hide()

    def _apply_window_icon(self) -> None:
        self.setWindowIcon(
            icons.app_icon(
                self._tokens["accent"],
                self._tokens["accent_hover"],
                self._tokens["accent_text"],
            )
        )

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
        )
        if dialog.exec() == QDialog.DialogCode.Accepted or dialog.connections_saved:
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

    def closeEvent(self, event) -> None:  # noqa: N802
        conversation = self._controller.conversation
        if conversation is not None:
            self._config.set("last_conversation", conversation.id)
        self._config.set_geometry(self.saveGeometry())
        self._config.set_splitter_state(
            self._sidebar_splitter_state
            if self._sidebar_splitter_state is not None else self._splitter.saveState()
        )
        self._config.sync()
        self._controller.shutdown()
        super().closeEvent(event)
