from __future__ import annotations

import json

from PyQt6.QtCore import QUrl
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..core.config import Config
from ..core.credentials import CredentialStore
from ..core.providers.registry import provider_info, provider_infos
from ..net.client import error_message
from . import theme
from .widgets import ChevronComboBox


class SettingsDialog(QDialog):
    def __init__(
        self,
        config: Config,
        credentials: CredentialStore,
        tokens: dict[str, str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._credentials = credentials
        self._tokens = dict(tokens)
        self._manager = QNetworkAccessManager(self)
        self._test_reply: QNetworkReply | None = None
        self._status_style = ""

        self.setWindowTitle("Settings")
        self.setMinimumWidth(560)

        heading = QLabel("Settings")
        heading.setObjectName("EmptyTitle")
        subtitle = QLabel("Konfigurasi provider, model, dan preferensi tampilan.")
        subtitle.setObjectName("TopMeta")

        self._provider = ChevronComboBox(theme.icon_color(self._tokens))
        for info in provider_infos():
            self._provider.addItem(info.label, info.id)

        self._base_url = QLineEdit()
        self._base_url.setPlaceholderText("https://api.example.com/v1")

        self._model = ChevronComboBox(theme.icon_color(self._tokens))
        self._model.setEditable(True)

        self._key = QLineEdit()
        self._key.setEchoMode(QLineEdit.EchoMode.Password)
        self._clear_key = QCheckBox("Hapus API key tersimpan")
        self._clear_key.hide()

        key_row = QWidget()
        key_layout = QVBoxLayout(key_row)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.setSpacing(6)
        key_layout.addWidget(self._key)
        key_layout.addWidget(self._clear_key)

        self._temperature = QDoubleSpinBox()
        self._temperature.setRange(0.0, 2.0)
        self._temperature.setSingleStep(0.1)
        self._temperature.setDecimals(1)

        self._max_tokens = QSpinBox()
        self._max_tokens.setRange(128, 128_000)
        self._max_tokens.setSingleStep(128)

        self._system_prompt = QPlainTextEdit()
        self._system_prompt.setObjectName("SystemPrompt")
        self._system_prompt.setFixedHeight(72)
        self._system_prompt.setPlaceholderText("Opsional, instruksi sistem untuk semua chat")

        self._theme = ChevronComboBox(theme.icon_color(self._tokens))
        self._theme.addItem("Dark", "dark")
        self._theme.addItem("Light", "light")

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        form.addRow("Provider", self._provider)
        form.addRow("Base URL", self._base_url)
        form.addRow("Model", self._model)
        form.addRow("API key", key_row)
        form.addRow("Temperature", self._temperature)
        form.addRow("Max tokens", self._max_tokens)
        form.addRow("System prompt", self._system_prompt)
        form.addRow("Tema", self._theme)

        self._test_button = QPushButton("Test connection")
        self._test_result = QLabel("")
        self._test_result.setObjectName("Hint")
        self._test_result.setWordWrap(True)

        test_row = QHBoxLayout()
        test_row.setSpacing(10)
        test_row.addWidget(self._test_button)
        test_row.addWidget(self._test_result, 1)

        self._save_button = QPushButton("Simpan")
        self._save_button.setObjectName("Primary")
        self._cancel_button = QPushButton("Batal")
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self._cancel_button)
        buttons.addWidget(self._save_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)
        layout.addWidget(heading)
        layout.addWidget(subtitle)
        layout.addSpacing(6)
        layout.addLayout(form)
        layout.addLayout(test_row)
        layout.addStretch(1)
        layout.addLayout(buttons)

        self._provider.currentIndexChanged.connect(self._load_provider)
        self._test_button.clicked.connect(self._test_connection)
        self._save_button.clicked.connect(self._save)
        self._cancel_button.clicked.connect(self.reject)

        self._load_initial()
        self._test_button.setCursor(self._test_button.cursor())

    def _load_initial(self) -> None:
        provider_id = str(self._config.get("provider", "openai"))
        index = self._provider.findData(provider_id)
        self._provider.setCurrentIndex(index if index >= 0 else 0)
        self._load_provider()

        self._temperature.setValue(float(self._config.get("temperature", 0.7)))
        self._max_tokens.setValue(int(self._config.get("max_tokens", 2048)))
        theme = self._config.theme
        theme_index = self._theme.findData(theme)
        self._theme.setCurrentIndex(max(theme_index, 0))

    def _selected_provider(self) -> str:
        return str(self._provider.currentData() or "openai")

    def _load_provider(self) -> None:
        provider_id = self._selected_provider()
        info = provider_info(provider_id)
        base_url = self._config.base_url_for(provider_id) or info.base_url
        self._base_url.setText(base_url)

        saved_model = self._config.model_for(provider_id) or info.default_model
        self._model.blockSignals(True)
        self._model.clear()
        if info.models:
            self._model.addItems(list(info.models))
        self._model.setCurrentText(saved_model)
        self._model.blockSignals(False)

        stored = self._credentials.has_secret(provider_id)
        self._key.clear()
        self._key.setEnabled(True)
        if stored:
            self._key.setPlaceholderText("Tersimpan di Windows Credential Manager")
        elif info.requires_key:
            self._key.setPlaceholderText("Masukkan API key")
        else:
            self._key.setPlaceholderText("Opsional (tidak diperlukan)")
        self._clear_key.setChecked(False)
        self._clear_key.setVisible(stored)
        self._system_prompt.setPlainText(str(self._config.get("system_prompt", "")))
        self._set_result("", "hint")

    def _set_result(self, text: str, kind: str) -> None:
        color = self._tokens["text_faint"]
        if kind == "success":
            color = self._tokens["success"]
        elif kind == "error":
            color = self._tokens["danger"]
        self._test_result.setText(text)
        self._test_result.setStyleSheet(f"color: {color};")

    def _test_connection(self) -> None:
        base_url = self._base_url.text().strip()
        if not base_url:
            self._set_result("Isi base URL terlebih dahulu.", "error")
            return
        provider_id = self._selected_provider()
        key = self._key.text().strip() or self._credentials.get_secret(provider_id) or ""
        request = QNetworkRequest(QUrl(base_url.rstrip("/") + "/models"))
        request.setRawHeader(b"Accept", b"application/json")
        if key:
            request.setRawHeader(b"Authorization", f"Bearer {key}".encode())
        request.setTransferTimeout(15_000)

        self._test_button.setEnabled(False)
        self._set_result("Menghubungkan...", "hint")
        self._test_reply = self._manager.get(request)
        self._test_reply.finished.connect(self._on_test_finished)

    def _on_test_finished(self) -> None:
        reply, self._test_reply = self._test_reply, None
        if reply is None:
            return
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        body = bytes(reply.readAll())
        error = reply.error()
        reply.deleteLater()
        self._test_button.setEnabled(True)

        if status is not None and int(status) < 400 and error == QNetworkReply.NetworkError.NoError:
            count = 0
            try:
                payload = json.loads(body.decode("utf-8", errors="replace"))
                if isinstance(payload, dict) and isinstance(payload.get("data"), list):
                    count = len(payload["data"])
            except ValueError:
                pass
            message = f"Terhubung. {count} model terdeteksi." if count else "Terhubung."
            self._set_result(message, "success")
            return
        if status is not None:
            self._set_result(error_message(body) or f"HTTP {int(status)}", "error")
        else:
            self._set_result(f"Gagal terhubung: {reply.errorString()}", "error")

    def _save(self) -> None:
        provider_id = self._selected_provider()
        info = provider_info(provider_id)
        self._config.set("provider", provider_id)

        base_url = self._base_url.text().strip()
        self._config.set_base_url_for(
            provider_id, "" if base_url == info.base_url else base_url
        )
        self._config.set_model_for(provider_id, self._model.currentText().strip())
        self._config.set("temperature", round(self._temperature.value(), 2))
        self._config.set("max_tokens", int(self._max_tokens.value()))
        self._config.set("system_prompt", self._system_prompt.toPlainText().strip())
        self._config.set("theme", str(self._theme.currentData()))

        key = self._key.text().strip()
        if self._clear_key.isChecked():
            self._credentials.delete_secret(provider_id)
        elif key:
            self._credentials.set_secret(provider_id, key)

        self._config.sync()
        self.accept()
