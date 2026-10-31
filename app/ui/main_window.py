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
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.config import Config
from ..core.credentials import CredentialStore
from ..core.models import Conversation
from ..core.providers.registry import provider_info
from ..core.store import ConversationStore
from . import icons, theme
from .chat_controller import ChatController
from .chat_view import ChatView
from .composer import Composer
from .empty_state import EmptyState
from .settings_dialog import SettingsDialog
from .sidebar import Sidebar
from .widgets import ChevronComboBox


class MainWindow(QMainWindow):
    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        self._tokens = theme.tokens_for(config.theme)
        self._store = ConversationStore()
        self._credentials = CredentialStore()
        self._controller = ChatController(config, self._store, self._credentials, self)

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
        composer_wrap = QWidget()
        composer_layout = QVBoxLayout(composer_wrap)
        composer_layout.setContentsMargins(24, 10, 24, 18)
        composer_layout.addWidget(self._composer)
        right_layout.addWidget(composer_wrap)

        self._splitter.addWidget(right)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([268, 912])
        self.setCentralWidget(self._splitter)

    def _build_topbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(58)

        self._title = QLabel("New chat")
        self._title.setObjectName("TopTitle")
        self._meta = QLabel("OpenAI")
        self._meta.setObjectName("TopMeta")

        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.addWidget(self._title)
        title_box.addWidget(self._meta)

        self._model_combo = ChevronComboBox(theme.icon_color(self._tokens))
        self._model_combo.setEditable(True)
        self._model_combo.setMinimumWidth(200)
        self._model_combo.setMaximumWidth(320)
        self._model_combo.setToolTip("Model untuk percakapan ini")

        self._theme_button = QPushButton()
        self._theme_button.setObjectName("IconButton")
        self._theme_button.setFixedSize(34, 34)
        self._theme_button.setToolTip("Ganti tema")
        self._theme_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_button.setIcon(icons.icon("theme", theme.icon_color(self._tokens), 18))

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 0, 18, 0)
        layout.setSpacing(12)
        layout.addLayout(title_box)
        layout.addStretch(1)
        layout.addWidget(self._model_combo)
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
        self._controller.stream_delta.connect(self._chat.feed)
        self._controller.stream_finished.connect(self._on_stream_finished)
        self._controller.error.connect(self._on_error)

        self._model_combo.currentTextChanged.connect(self._on_model_changed)
        self._theme_button.clicked.connect(self._toggle_theme)

        QShortcut(QKeySequence.StandardKey.New, self, activated=self._new_chat)
        QShortcut(QKeySequence("Ctrl+,"), self, activated=self._open_settings)
        QShortcut(QKeySequence("Esc"), self, activated=self._controller.stop)

    def _restore_state(self) -> None:
        geometry = self._config.geometry()
        if geometry is not None:
            self.restoreGeometry(geometry)
        state = self._config.splitter_state()
        if state is not None:
            self._splitter.restoreState(state)

        self._refresh_provider_ui()
        self._refresh_conversations()

        last = str(self._config.get("last_conversation", "") or "")
        if last and self._controller.open(last) and self._controller.conversation is not None:
            self._show_conversation(self._controller.conversation)
        else:
            self._show_empty()
            self._composer.focus_input()

    def _refresh_provider_ui(self) -> None:
        provider_id = str(self._config.get("provider", "openai"))
        info = provider_info(provider_id)
        self._meta.setText(info.label)

        model = self._config.model_for(provider_id) or info.default_model
        models = list(info.models)
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
        combo.setEnabled(bool(model or info.models))

    def _refresh_conversations(self) -> None:
        self._sidebar.set_conversations(self._store.list())

    def _show_empty(self) -> None:
        self._stack.setCurrentWidget(self._empty)
        self._title.setText("New chat")

    def _show_conversation(self, conversation: Conversation) -> None:
        if conversation.provider and conversation.provider != str(
            self._config.get("provider", "openai")
        ):
            self._config.set("provider", conversation.provider)
            self._refresh_provider_ui()

        self._chat.show_conversation(conversation)
        self._stack.setCurrentWidget(self._chat)
        self._title.setText(conversation.title or "New chat")
        self._composer.focus_input()

        if conversation.model:
            self._model_combo.blockSignals(True)
            self._model_combo.setCurrentText(conversation.model)
            self._model_combo.blockSignals(False)

        self._sidebar.select(conversation.id)
        self._config.set("last_conversation", conversation.id)
        self._hide_banner()

    def show_demo(self) -> None:
        from ..core.models import Message

        conversation = Conversation(title="Cara kerja transformer")
        conversation.provider = str(self._config.get("provider", "openai"))
        conversation.model = self._config.model_for(conversation.provider) or "gpt-4o-mini"
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
        self._hide_banner()
        self._chat.begin_stream()

    def _on_stream_finished(self, message) -> None:
        self._composer.set_busy(False)
        conversation = self._controller.conversation
        self._chat.end_stream(conversation)
        if conversation is not None:
            self._title.setText(conversation.title or "New chat")
            self._refresh_conversations()
            self._config.set("last_conversation", conversation.id)
        self._composer.focus_input()

    def _on_model_changed(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        provider_id = str(self._config.get("provider", "openai"))
        self._config.set_model_for(provider_id, text)

    def _on_error(self, message: str) -> None:
        self._composer.set_busy(False)
        self._banner.setText(message)
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
        self._model_combo.set_chevron_color(theme.icon_color(self._tokens))
        self._theme_button.setIcon(icons.icon("theme", theme.icon_color(self._tokens), 18))
        self._apply_window_icon()

    def _toggle_theme(self) -> None:
        name = "light" if self._config.theme == "dark" else "dark"
        self._config.theme = name
        self._config.sync()
        self._apply_theme(name)

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self._config, self._credentials, self._tokens, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._apply_theme(self._config.theme)
            self._refresh_provider_ui()
            self._refresh_conversations()

    def closeEvent(self, event) -> None:  # noqa: N802
        conversation = self._controller.conversation
        if conversation is not None:
            self._config.set("last_conversation", conversation.id)
        self._config.set_geometry(self.saveGeometry())
        self._config.set_splitter_state(self._splitter.saveState())
        self._config.sync()
        self._controller.shutdown()
        super().closeEvent(event)
