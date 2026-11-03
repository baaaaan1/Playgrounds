from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.config import Config
from ..core.credentials import CredentialStore
from ..core.profiles import ConnectionProfile, endpoint_url
from ..core.providers.registry import provider_info, provider_infos
from ..net.models import ModelDiscovery
from . import icons, theme
from .widgets import ChevronComboBox, NoWheelDoubleSpinBox, NoWheelSpinBox
from .window_chrome import FramelessWindowMixin, TitleBar


class SettingsDialog(FramelessWindowMixin, QDialog):
    """Edit connection and appearance drafts; persist only on explicit save."""

    def __init__(
        self,
        config: Config,
        credentials: CredentialStore,
        tokens: dict[str, str],
        parent: QWidget | None = None,
        *,
        connections_editable: bool = True,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._credentials = credentials
        self._tokens = dict(tokens)
        self._connections_editable = connections_editable
        self.connections_saved = False
        self._profiles = config.profiles()
        self._initial_profiles = [profile.to_dict() for profile in self._profiles]
        self._initial_theme = config.theme
        self._active_profile_id = config.active_profile().id
        self._initial_active = self._active_profile_id
        self._loading = True
        self._current: ConnectionProfile | None = None
        self._keys: dict[str, str | None] = {}
        self._removed: list[ConnectionProfile] = []
        self._available_models: list[str] = []
        self._discovery = ModelDiscovery(self)
        self._discovery.models_ready.connect(self._models_received)
        self._discovery.failed.connect(lambda message: self._fetch_finished(message, "error"))

        self.setWindowTitle("Settings")
        self.setObjectName("SettingsDialog")
        self.resize(820, 780)
        self.setMinimumSize(600, 480)
        self.setup_frameless_window()
        self._build_ui()
        self._reload_profiles(self._active_profile_id)
        self._theme_light.setChecked(config.theme == "light")
        self._theme_dark.setChecked(config.theme == "dark")
        self._loading = False
        self._update_dirty()
        if connections_editable:
            self._name.setFocus()
        else:
            self._pages.widget(0).setEnabled(False)
            self._appearance_button.click()
            self._theme_dark.setFocus()
            self._set_result("Connections are read-only while a response is running. You can still change the theme.", "hint")

    def _button(self, text: str, icon_name: str, slot) -> QPushButton:
        button = QPushButton(text)
        button.setIcon(icons.icon(icon_name, self._tokens["text_muted"], 18))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setAutoDefault(False)
        button.clicked.connect(slot)
        return button

    def _build_ui(self) -> None:
        self._heading = QLabel("Settings")
        self._heading.setObjectName("SettingsTitle")
        self._subtitle = QLabel("Manage your connections and application preferences.")
        self._subtitle.setObjectName("SettingsHelp")
        self._subtitle.setWordWrap(True)

        navigation = QHBoxLayout()
        self._connections_button = QPushButton("Connections")
        self._appearance_button = QPushButton("Appearance")
        self._navigation = QButtonGroup(self)
        self._pages = QStackedWidget()
        for index, button in enumerate((self._connections_button, self._appearance_button)):
            button.setObjectName("SettingsTab")
            button.setCheckable(True)
            button.setAutoDefault(False)
            self._navigation.addButton(button, index)
            navigation.addWidget(button)
        self._navigation.idClicked.connect(self._pages.setCurrentIndex)
        self._connections_button.setChecked(True)
        navigation.addStretch(1)

        self._profile_list = ChevronComboBox(theme.icon_color(self._tokens))
        self._profile_list.setMinimumWidth(0)
        self._profile_list.setMinimumContentsLength(10)
        self._profile_list.setSizeAdjustPolicy(
            ChevronComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self._profile_list.setAccessibleName("Connection to edit")
        self._profile_list.currentIndexChanged.connect(self._select_profile)
        self._add_button = self._button("Add", "plus", self._add_profile)
        self._add_button.setAccessibleName("Add connection")
        self._delete_button = self._button("Remove", "trash", self._delete_profile)
        self._delete_button.setAccessibleName("Remove connection")
        self._delete_button.setToolTip("Stage removal of this connection until you save changes")
        profile_row = QHBoxLayout()
        profile_label = QLabel("&Connection")
        profile_label.setBuddy(self._profile_list)
        profile_row.addWidget(profile_label)
        profile_row.addWidget(self._profile_list, 1)
        profile_row.addWidget(self._add_button)
        profile_row.addWidget(self._delete_button)
        self._connection_context = QLabel()
        self._connection_context.setObjectName("SettingsHelp")
        self._connection_context.setWordWrap(True)
        self._use_connection = self._button("Use this connection", "check", self._activate_profile)
        scope_row = QHBoxLayout()
        scope_row.addWidget(self._connection_context, 1)
        scope_row.addWidget(self._use_connection)

        self._name = QLineEdit()
        self._name.setPlaceholderText("e.g. Work gateway or Local development")
        self._name.textEdited.connect(self._rename_profile)
        self._provider = ChevronComboBox(theme.icon_color(self._tokens))
        self._provider.setMinimumContentsLength(10)
        self._provider.setSizeAdjustPolicy(
            ChevronComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        for info in provider_infos():
            self._provider.addItem(info.label, info.id)
        self._preset_button = self._button("Apply preset", "check", self._apply_preset)
        self._preset_button.setToolTip("Replace this draft's endpoint and model list with preset values")
        preset_row = QHBoxLayout()
        preset_row.addWidget(self._provider, 1)
        preset_row.addWidget(self._preset_button)

        self._base_url = QLineEdit()
        self._base_url.setPlaceholderText("https://api.example.com/v1")
        self._base_url.textEdited.connect(self._endpoint_edited)
        self._base_url.editingFinished.connect(self._validate_base_url)
        self._base_url_error = QLabel()
        self._base_url_error.setObjectName("SettingsFieldError")
        self._base_url_error.setWordWrap(True)
        self._base_url_error.hide()
        endpoint_layout = QVBoxLayout()
        endpoint_layout.addWidget(self._base_url)
        endpoint_layout.addWidget(self._base_url_error)

        self._key = QLineEdit()
        self._key.setEchoMode(QLineEdit.EchoMode.Password)
        self._key.textEdited.connect(self._cancel_fetch)
        self._reveal_key = self._button("", "eye", self._toggle_key_visibility)
        self._reveal_key.setObjectName("IconButton")
        self._reveal_key.setFixedSize(34, 34)
        self._reveal_key.setCheckable(True)
        self._reveal_key.setToolTip("Show API key")
        self._reveal_key.setAccessibleName("Show API key")
        key_input_row = QHBoxLayout()
        key_input_row.addWidget(self._key, 1)
        key_input_row.addWidget(self._reveal_key)
        self._clear_key = QCheckBox("Remove saved API key")
        self._clear_key.toggled.connect(self._key_removal_toggled)
        self._key_hint = QLabel()
        self._key_hint.setObjectName("SettingsHelp")
        self._key_hint.setWordWrap(True)
        key_layout = QVBoxLayout()
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.addLayout(key_input_row)
        key_layout.addWidget(self._key_hint)
        key_layout.addWidget(self._clear_key)

        self._model = ChevronComboBox(theme.icon_color(self._tokens))
        self._model.setMinimumContentsLength(10)
        self._model.setSizeAdjustPolicy(
            ChevronComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self._model.setEditable(True)
        self._model.setToolTip("Select a discovered model, or enter an ID manually")
        self._fetch_button = self._button("Fetch models", "refresh", self._fetch_models)
        self._fetch_button.setToolTip("Request models from this endpoint without saving changes")
        self._stop_fetch = self._button("Cancel fetch", "stop", self._cancel_fetch)
        self._stop_fetch.hide()
        self._fetch_progress = QProgressBar()
        self._fetch_progress.setRange(0, 0)
        self._fetch_progress.setTextVisible(False)
        self._fetch_progress.setAccessibleName("Fetching models")
        self._fetch_progress.hide()
        self._models_filter = QLineEdit()
        self._models_filter.setPlaceholderText("Filter models...")
        self._models_filter.setAccessibleName("Filter saved models")
        self._models_filter.setClearButtonEnabled(True)
        self._models_filter.textChanged.connect(self._filter_models)
        self._models_list = QListWidget()
        self._models_list.setObjectName("ModelList")
        self._models_list.setMinimumHeight(100)
        self._models_list.setMaximumHeight(160)
        self._models_list.setAccessibleName("Saved models")
        self._models_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._models_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._models_list.currentItemChanged.connect(
            lambda item, previous: self._model.setCurrentText(item.text()) if item else None
        )
        self._models_list.itemClicked.connect(lambda item: self._model.setCurrentText(item.text()))
        self._model_count = QLabel()
        self._model_count.setObjectName("SettingsHelp")
        self._model_count.setWordWrap(True)
        self._delete_model_button = self._button("Remove from list", "trash", self._delete_model)
        self._delete_model_button.setToolTip("Remove the selected model from this profile, not from the server")
        self._delete_model_button.setEnabled(False)
        self._model.currentTextChanged.connect(self._update_delete_model_button)
        models_footer = QHBoxLayout()
        models_footer.addWidget(self._model_count, 1)
        models_footer.addWidget(self._delete_model_button)
        model_header = QHBoxLayout()
        model_header.addWidget(self._model, 1)
        model_header.addWidget(self._fetch_button)
        model_header.addWidget(self._stop_fetch)
        models_layout = QVBoxLayout()
        models_layout.addLayout(model_header)
        models_layout.addWidget(self._fetch_progress)
        models_layout.addWidget(self._models_filter)
        models_layout.addWidget(self._models_list)
        models_layout.addLayout(models_footer)

        self._temperature = NoWheelDoubleSpinBox()
        self._temperature.setRange(0.0, 2.0)
        self._temperature.setSingleStep(0.1)
        self._temperature.setDecimals(2)
        self._max_tokens = NoWheelSpinBox()
        self._max_tokens.setRange(1, 128_000)
        self._max_tokens.setSingleStep(128)
        self._system_prompt = QPlainTextEdit()
        self._system_prompt.setObjectName("SystemPrompt")
        self._system_prompt.setMinimumHeight(100)
        self._system_prompt.setPlaceholderText("Optional system instructions for this connection")

        details = QGroupBox("Connection details")
        form = QFormLayout(details)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setVerticalSpacing(12)
        self._add_field(form, "Name", self._name, self._name)
        self._add_field(form, "Provider preset", preset_row, self._provider)
        self._add_field(form, "Base URL", endpoint_layout, self._base_url,
                        "Use the API base address, such as https://api.example.com/v1.")
        self._add_field(form, "API key", key_layout, self._key)

        models = QGroupBox("Models")
        model_form = QFormLayout(models)
        model_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        model_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._add_field(model_form, "Default model", models_layout, self._model,
                        "Choose a model or enter its ID. Fetching does not save your changes.")

        self._advanced = QGroupBox("Response defaults (optional)")
        self._advanced.setCheckable(True)
        self._advanced.setChecked(False)
        advanced_layout = QVBoxLayout(self._advanced)
        self._advanced_body = QWidget()
        response_form = QFormLayout(self._advanced_body)
        response_form.setContentsMargins(0, 4, 0, 0)
        response_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        response_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        response_form.setVerticalSpacing(12)
        self._add_field(response_form, "Temperature", self._temperature, self._temperature,
                        "Higher values increase variation. Supported values depend on the model.")
        self._add_field(response_form, "Maximum output tokens", self._max_tokens, self._max_tokens,
                        "Limits response length. The model may enforce a lower limit.")
        self._add_field(response_form, "System instructions", self._system_prompt, self._system_prompt,
                        "Instructions sent with requests using this connection, including existing chats.")
        advanced_layout.addWidget(self._advanced_body)
        self._advanced_body.hide()
        self._advanced.toggled.connect(self._advanced_body.setVisible)

        editor = QWidget()
        editor.setObjectName("SettingsEditor")
        editor_layout = QVBoxLayout(editor)
        editor_layout.setContentsMargins(0, 0, 8, 0)
        editor_layout.setSpacing(24)
        editor_layout.addWidget(details)
        editor_layout.addWidget(models)
        editor_layout.addWidget(self._advanced)
        editor_layout.addStretch(1)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(editor)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        connections = QWidget()
        content = QVBoxLayout(connections)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(12)
        content.addLayout(profile_row)
        content.addLayout(scope_row)
        content.addWidget(self._scroll, 1)
        self._pages.addWidget(connections)

        appearance = QWidget()
        appearance_layout = QVBoxLayout(appearance)
        appearance_layout.setContentsMargins(0, 0, 0, 0)
        theme_group = QGroupBox("Application theme")
        theme_layout = QVBoxLayout(theme_group)
        theme_help = QLabel("Applies to the whole application after you save changes.")
        theme_help.setObjectName("SettingsHelp")
        theme_help.setWordWrap(True)
        theme_layout.addWidget(theme_help)
        self._theme_dark = QRadioButton("Dark")
        self._theme_light = QRadioButton("Light")
        self._theme_dark.setAccessibleName("Dark application theme")
        self._theme_light.setAccessibleName("Light application theme")
        theme_layout.addWidget(self._theme_dark)
        theme_layout.addWidget(self._theme_light)
        appearance_layout.addWidget(theme_group)
        appearance_layout.addStretch(1)
        self._pages.addWidget(appearance)

        self._status = QLabel()
        self._status.setWordWrap(True)
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        self._status.setObjectName("SettingsStatus")
        self._status.setAccessibleName("Settings status")
        self._status.hide()
        self._dirty_label = QLabel("No unsaved changes")
        self._dirty_label.setObjectName("SettingsHelp")
        self._save_button = self._button("Save changes", "save", self._save)
        self._save_button.setObjectName("Primary")
        self._save_button.setIcon(icons.icon("save", self._tokens["accent_text"], 18))
        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.setAutoDefault(False)
        self._cancel_button.clicked.connect(self.reject)
        footer = QHBoxLayout()
        footer.addWidget(self._dirty_label)
        footer.addStretch(1)
        footer.addWidget(self._cancel_button)
        footer.addWidget(self._save_button)

        content_panel = QWidget()
        content_panel.setObjectName("Root")
        layout = self._content_layout = QVBoxLayout(content_panel)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)
        layout.addWidget(self._heading)
        layout.addWidget(self._subtitle)
        layout.addLayout(navigation)
        layout.addWidget(self._pages, 1)
        layout.addWidget(self._status)
        layout.addLayout(footer)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)
        self._title_bar = TitleBar(
            self, self._tokens, show_minimize=False, show_maximize=False,
        )
        outer.addWidget(self._title_bar)
        outer.addWidget(content_panel, 1)

        for control in (self._name, self._base_url):
            control.textChanged.connect(self._update_dirty)
        self._key.textEdited.connect(self._update_dirty)
        self._model.currentTextChanged.connect(self._update_dirty)
        self._temperature.valueChanged.connect(self._update_dirty)
        self._max_tokens.valueChanged.connect(self._update_dirty)
        self._system_prompt.textChanged.connect(self._update_dirty)
        self._theme_light.toggled.connect(self._update_dirty)
        self._theme_dark.toggled.connect(self._update_dirty)
        tab_order = (
            self._connections_button, self._appearance_button, self._profile_list,
            self._add_button, self._delete_button, self._use_connection,
            self._name, self._provider, self._preset_button, self._base_url,
            self._key, self._reveal_key, self._clear_key, self._model,
            self._fetch_button, self._stop_fetch, self._models_filter, self._models_list,
            self._delete_model_button, self._advanced, self._temperature,
            self._max_tokens, self._system_prompt, self._theme_dark, self._theme_light,
            self._cancel_button, self._save_button,
        )
        for first, second in zip(tab_order, tab_order[1:], strict=False):
            QWidget.setTabOrder(first, second)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "_content_layout"):
            compact = self.height() < 620
            self._heading.setVisible(not compact)
            self._subtitle.setVisible(not compact)
            margin = 16 if compact else 24
            self._content_layout.setContentsMargins(margin, 12 if compact else 22, margin, 16 if compact else 20)
            self._content_layout.setSpacing(10 if compact else 14)

    def _add_field(self, form, text, field, control, description="") -> None:
        label = QLabel(text)
        label.setBuddy(control)
        control.setAccessibleName(text)
        wrapper = QVBoxLayout()
        wrapper.setSpacing(6)
        if isinstance(field, QWidget):
            wrapper.addWidget(field)
        else:
            wrapper.addLayout(field)
        if description:
            hint = QLabel(description)
            hint.setObjectName("SettingsHelp")
            hint.setWordWrap(True)
            wrapper.addWidget(hint)
            control.setAccessibleDescription(description)
            control.setProperty("helpText", description)
        form.addRow(label, wrapper)

    def _has_connection_changes(self) -> bool:
        self._stash()
        return (
            [profile.to_dict() for profile in self._profiles] != self._initial_profiles
            or self._active_profile_id != self._initial_active
            or any(
                self._keys[profile.id] != self._credentials.get_secret(profile.credential_name)
                for profile in self._profiles
                if profile.id in self._keys
            )
        )

    def _has_changes(self) -> bool:
        return self._has_connection_changes() or (
            ("light" if self._theme_light.isChecked() else "dark") != self._initial_theme
        )

    def _update_dirty(self, *_args) -> None:
        if not self._loading:
            self._dirty_label.setText("Unsaved changes" if self._has_changes() else "No unsaved changes")

    def _activate_profile(self) -> None:
        if self._current is not None:
            self._active_profile_id = self._current.id
            self._update_profile_context()
            self._update_dirty()

    def _update_profile_context(self) -> None:
        active = self._current is not None and self._current.id == self._active_profile_id
        self._connection_context.setText(
            "Active connection. Changes apply to future requests after saving."
            if active else "Editing this connection does not make it active."
        )
        self._use_connection.setEnabled(not active)

    def _stash(self) -> None:
        profile = self._current
        if profile is None or not self._connections_editable:
            return
        profile.name = self._name.text().strip() or "Untitled connection"
        profile.base_url = self._base_url.text().strip()
        profile.model = self._model.currentText().strip()
        profile.models = list(self._available_models)
        # Preserve saved values that the editor cannot represent until explicitly changed.
        profile.temperature = (
            self._loaded_temperature[0] if self._temperature.value() == self._loaded_temperature[1]
            else self._temperature.value()
        )
        profile.max_tokens = (
            self._loaded_max_tokens[0] if self._max_tokens.value() == self._loaded_max_tokens[1]
            else self._max_tokens.value()
        )
        profile.system_prompt = self._system_prompt.toPlainText()
        if self._clear_key.isChecked():
            self._keys[profile.id] = None
        elif self._key.isModified():
            key = self._key.text().strip()
            if key:
                self._keys[profile.id] = key
            else:
                self._keys.pop(profile.id, None)

    def _reload_profiles(self, selected_id: str) -> None:
        self._profile_list.blockSignals(True)
        self._profile_list.clear()
        selected_row = 0
        for row, profile in enumerate(self._profiles):
            self._profile_list.addItem(profile.name, profile.id)
            if profile.id == selected_id:
                selected_row = row
        self._profile_list.setCurrentIndex(selected_row)
        self._profile_list.blockSignals(False)
        self._select_profile(selected_row)
        self._delete_button.setEnabled(len(self._profiles) > 1)

    def _select_profile(self, row: int) -> None:
        if not 0 <= row < len(self._profiles):
            return
        self._stash()
        was_loading = self._loading
        self._loading = True
        self._cancel_fetch()
        profile = self._profiles[row]
        self._current = profile
        self._name.setText(profile.name)
        self._base_url.setText(profile.base_url)
        self._base_url_error.hide()
        self._base_url.setAccessibleDescription(self._base_url.property("helpText"))
        self._provider.setCurrentIndex(max(self._provider.findData(profile.preset), 0))
        self._model.clear()
        self._model.addItems(list(dict.fromkeys([profile.model, *profile.models])))
        self._model.setCurrentText(profile.model)
        self._available_models = list(profile.models)
        self._models_filter.clear()
        self._filter_models()
        self._temperature.setValue(profile.temperature)
        self._max_tokens.setValue(profile.max_tokens)
        self._loaded_temperature = (profile.temperature, self._temperature.value())
        self._loaded_max_tokens = (profile.max_tokens, self._max_tokens.value())
        self._system_prompt.setPlainText(profile.system_prompt)
        self._reveal_key.setChecked(False)
        self._key.setEchoMode(QLineEdit.EchoMode.Password)
        self._reveal_key.setIcon(icons.icon("eye", self._tokens["text_muted"], 18))
        self._reveal_key.setToolTip("Show API key")
        self._reveal_key.setAccessibleName("Show API key")
        self._key.setText(self._keys.get(profile.id) or "")
        self._key.setModified(False)
        self._clear_key.blockSignals(True)
        self._clear_key.setChecked(profile.id in self._keys and self._keys[profile.id] is None)
        self._clear_key.blockSignals(False)
        stored = self._credentials.has_secret(profile.credential_name)
        self._clear_key.setVisible(stored or profile.id in self._keys)
        self._key.setEnabled(not self._clear_key.isChecked())
        self._reveal_key.setEnabled(not self._clear_key.isChecked())
        self._key.setPlaceholderText("Saved securely; leave blank to keep" if stored else "Optional API key")
        key_help = (
            "A key is saved securely. Leave blank to keep it, or enter a replacement."
            if stored else "Optional for endpoints that do not require authentication."
        )
        self._key_hint.setText(key_help)
        self._key.setAccessibleDescription(key_help)
        self._update_profile_context()
        self._status.clear()
        self._status.hide()
        self._loading = was_loading
        self._update_dirty()

    def _rename_profile(self, text: str) -> None:
        self._profile_list.setItemText(
            self._profile_list.currentIndex(), text.strip() or "Untitled connection"
        )

    def _add_profile(self) -> None:
        self._stash()
        profile = ConnectionProfile(name=f"Connection {len(self._profiles) + 1}")
        self._profiles.append(profile)
        self._reload_profiles(profile.id)
        self._name.setFocus()
        self._name.selectAll()
        self._scroll.verticalScrollBar().setValue(0)
        self._update_dirty()

    def _delete_profile(self) -> None:
        if self._current is None or len(self._profiles) <= 1:
            return
        self._removed.append(self._current)
        self._profiles.remove(self._current)
        self._keys.pop(self._current.id, None)
        self._current = None
        if not any(profile.id == self._active_profile_id for profile in self._profiles):
            self._active_profile_id = self._profiles[0].id
        self._reload_profiles(self._profiles[0].id)
        self._set_result("Connection removed from this draft. Cancel to discard the removal.", "hint")
        self._update_dirty()

    def _apply_preset(self) -> None:
        info = provider_info(str(self._provider.currentData()))
        if (
            self._base_url.text().strip() and self._base_url.text().strip() != info.base_url
            or self._available_models and self._available_models != list(info.models)
        ):
            answer = QMessageBox.question(
                self, "Apply provider preset?",
                "Replace this draft's base URL and model list? The API key and response defaults will be kept.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._loading = True
        if self._current is not None:
            self._current.preset = info.id
        self._cancel_fetch()
        self._base_url.setText(info.base_url)
        self._model.clear()
        self._model.addItems(list(info.models))
        self._model.setCurrentText(info.default_model)
        self._available_models = list(info.models)
        self._filter_models()
        self._loading = False
        self._set_result("Preset applied to this draft only. Fetch models for the latest list.", "hint")
        self._update_dirty()

    def _key_value(self) -> str:
        profile = self._current
        if profile is None or self._clear_key.isChecked():
            return ""
        if self._key.isModified():
            key = self._key.text().strip()
            return key or self._credentials.get_secret(profile.credential_name) or ""
        if profile.id in self._keys:
            return self._keys[profile.id] or ""
        return self._credentials.get_secret(profile.credential_name) or ""

    def _toggle_key_visibility(self) -> None:
        visible = self._reveal_key.isChecked()
        if visible and not self._key.text() and not self._key.isModified():
            self._key.setText(self._key_value())
            self._key.setModified(False)
        self._key.setEchoMode(QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)
        action = "Hide API key" if visible else "Show API key"
        self._reveal_key.setToolTip(action)
        self._reveal_key.setAccessibleName(action)
        self._reveal_key.setIcon(icons.icon("eye-off" if visible else "eye", self._tokens["text_muted"], 18))

    def _key_removal_toggled(self, checked: bool) -> None:
        self._cancel_fetch()
        self._key.setEnabled(not checked)
        self._reveal_key.setEnabled(not checked)
        if checked:
            self._reveal_key.setChecked(False)
            self._toggle_key_visibility()
            self._key.clear()
            self._key.setModified(False)
        elif self._current is not None and self._keys.get(self._current.id, "") is None:
            self._keys.pop(self._current.id)
        self._update_dirty()

    def _endpoint_edited(self) -> None:
        self._cancel_fetch()
        self._available_models = []
        selected = self._model.currentText()
        self._model.clear()
        self._model.setCurrentText(selected)
        self._filter_models()
        if not self._base_url_error.isHidden():
            self._validate_base_url()
        self._update_dirty()

    def _validate_base_url(self) -> bool:
        error = ""
        try:
            endpoint_url(self._base_url.text(), "models")
        except ValueError as exc:
            error = str(exc)
        self._base_url_error.setText("Error: " + error if error else "")
        self._base_url_error.setVisible(bool(error))
        self._base_url.setAccessibleDescription(error or self._base_url.property("helpText"))
        return not error

    def _cancel_fetch(self) -> None:
        was_busy = self._stop_fetch.isVisible()
        self._discovery.cancel()
        self._fetch_button.setEnabled(True)
        self._save_button.setEnabled(True)
        self._stop_fetch.hide()
        self._fetch_progress.hide()
        self._update_delete_model_button()
        if was_busy:
            self._set_result("Model discovery canceled. No changes were saved.", "hint")

    def _fetch_models(self) -> None:
        try:
            endpoint_url(self._base_url.text(), "models")
        except ValueError as exc:
            self._set_result(str(exc), "error")
            self._validate_base_url()
            self._base_url.setFocus()
            self._scroll.ensureWidgetVisible(self._base_url)
            return
        self._fetch_button.setEnabled(False)
        self._save_button.setEnabled(False)
        self._delete_model_button.setEnabled(False)
        self._stop_fetch.show()
        self._fetch_progress.show()
        self._set_result("Fetching available models...", "hint")
        self._discovery.fetch(self._base_url.text(), self._key_value())

    def _models_received(self, models: list[str]) -> None:
        self._loading = True
        self._available_models = list(models)
        selected = self._model.currentText()
        self._model.clear()
        self._model.addItems(models)
        self._model.setCurrentText(selected if selected in models else (models[0] if models else selected))
        self._filter_models()
        self._fetch_button.setEnabled(True)
        self._save_button.setEnabled(True)
        self._stop_fetch.hide()
        self._fetch_progress.hide()
        self._loading = False
        self._update_delete_model_button()
        self._update_dirty()
        self._set_result(
            f"{len(models)} models found. Changes have not been saved."
            if models else "No models returned. Enter a model ID manually. Changes have not been saved.",
            "success" if models else "hint",
        )

    def _update_delete_model_button(self) -> None:
        self._delete_model_button.setEnabled(
            bool(self._model.currentText().strip()) and not self._discovery.busy
        )

    def _delete_model(self) -> None:
        profile = self._current
        model = self._model.currentText().strip()
        if profile is None or not model or self._discovery.busy:
            return
        self._loading = True
        self._available_models = [item for item in self._available_models if item != model]
        selected = next(iter(self._available_models), "")
        profile.models = list(self._available_models)
        profile.model = selected
        self._model.clear()
        self._model.addItems(list(dict.fromkeys(item for item in [selected, *self._available_models] if item)))
        self._model.setCurrentText(selected)
        self._filter_models()
        self._update_delete_model_button()
        self._loading = False
        self._update_dirty()
        self._set_result("Model removed from this draft, not the server. Fetching may add it again.", "hint")

    def _filter_models(self) -> None:
        query = self._models_filter.text().casefold()
        self._models_list.blockSignals(True)
        self._models_list.clear()
        matches = [model for model in self._available_models if query in model.casefold()]
        self._models_list.addItems(matches)
        self._models_list.blockSignals(False)
        self._model_count.setText(
            f"{len(matches)} of {len(self._available_models)} models"
            if matches else (
                "No matching models. Try another search."
                if self._available_models else "No saved models. Fetch models or enter an ID above."
            )
        )

    def _fetch_finished(self, message: str, kind: str) -> None:
        self._fetch_button.setEnabled(True)
        self._save_button.setEnabled(True)
        self._stop_fetch.hide()
        self._fetch_progress.hide()
        self._update_delete_model_button()
        self._set_result(message, kind)

    def _set_result(self, text: str, kind: str) -> None:
        prefix = {"success": "Success: ", "error": "Error: "}.get(kind, "")
        self._status.setText(prefix + text)
        self._status.setAccessibleDescription(prefix + text)
        self._status.setProperty("status", kind)
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)
        self._status.show()

    def _save(self) -> bool:
        if self._discovery.busy:
            self._set_result("Wait for model discovery to finish before saving.", "hint")
            return False
        connections_changed = self._has_connection_changes()
        profile = self._current
        if profile is None:
            return False
        for row, item in enumerate(self._profiles if connections_changed else []):
            error = ""
            field = self._base_url
            try:
                endpoint_url(item.base_url, "models")
            except ValueError as exc:
                error = str(exc)
            if not error and not item.model:
                error = "Select a model from the list, or enter its ID manually."
                field = self._model
            if error:
                self._pages.setCurrentIndex(0)
                self._connections_button.setChecked(True)
                self._profile_list.setCurrentIndex(row)
                self._set_result(f"{item.name}: {error}", "error")
                if field is self._base_url:
                    self._validate_base_url()
                else:
                    field.setAccessibleDescription(error)
                field.setFocus()
                self._scroll.ensureWidgetVisible(field)
                return False
        profiles = self._profiles
        updates = {
            item.credential_name: (item.name, self._keys[item.id])
            for item in profiles if item.id in self._keys
        }
        references = {item.credential_name for item in self._profiles}
        for item in self._removed:
            if item.credential_name not in references:
                updates[item.credential_name] = (item.name, None)
        originals = {name: self._credentials.get_secret(name) for name in updates}
        applied: list[str] = []

        def restore_credentials() -> bool:
            restored = True
            for name in reversed(applied):
                old = originals[name]
                ok = (
                    self._credentials.set_secret(name, old) if old is not None
                    else self._credentials.delete_secret(name)
                )
                restored = ok and restored
            return restored

        # Write replacements before destructive operations. Credential Manager has
        # no transactions, so keep snapshots to roll back any successful edits.
        for name, (label, key) in sorted(updates.items(), key=lambda pair: pair[1][1] is None):
            if originals[name] == key:
                continue
            ok = (
                self._credentials.set_secret(name, key) if key is not None
                else self._credentials.delete_secret(name)
            )
            if not ok:
                restored = restore_credentials()
                action = "store" if key is not None else "remove"
                suffix = "No changes were saved." if restored else "Credential rollback failed; check stored keys before retrying."
                self._set_result(f"Could not {action} the key for {label}. {suffix}", "error")
                return False
            applied.append(name)

        previous = self._config.profiles()
        previous_active = self._config.active_profile().id
        previous_theme = self._config.theme
        if connections_changed:
            self._config.save_profiles(self._profiles, self._active_profile_id)
        self._config.theme = "light" if self._theme_light.isChecked() else "dark"
        if not self._config.sync():
            if connections_changed:
                self._config.save_profiles(previous, previous_active)
            self._config.theme = previous_theme
            self._config.sync()
            restored = restore_credentials()
            suffix = "Previous key values restored." if restored else "Credential rollback failed; check stored keys before retrying."
            self._set_result(f"Could not save connection settings. {suffix}", "error")
            return False
        self.connections_saved = connections_changed
        self.accept()
        return True

    def reject(self) -> None:
        if self._has_changes():
            answer = QMessageBox.question(
                self, "Unsaved changes", "Save your changes before closing settings?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer == QMessageBox.StandardButton.Save:
                self._save()
                return
            if answer != QMessageBox.StandardButton.Discard:
                return
        super().reject()

    def done(self, result: int) -> None:
        self._discovery.cancel()
        self._key.setEchoMode(QLineEdit.EchoMode.Password)
        self._key.clear()
        self._keys.clear()
        super().done(result)
