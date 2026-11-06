from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLayout,
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

from .. import __version__
from ..core.config import Config
from ..core.credentials import CredentialStore
from ..core.profiles import ConnectionProfile, endpoint_url
from ..core.providers.registry import provider_info, provider_infos
from ..net.models import ModelDiscovery
from . import icons, theme
from .about_panel import AboutPanel
from .update_panel import UpdatePanel
from .widgets import ChevronComboBox, NoWheelDoubleSpinBox, NoWheelSpinBox
from .window_chrome import FramelessWindowMixin, TitleBar


class SettingsDialog(FramelessWindowMixin, QDialog):
    """Edit connection and appearance drafts; persist only on explicit save."""

    install_requested = pyqtSignal(object, object)

    def __init__(
        self,
        config: Config,
        credentials: CredentialStore,
        tokens: dict[str, str],
        parent: QWidget | None = None,
        *,
        connections_editable: bool = True,
        update_panel: UpdatePanel | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._credentials = credentials
        self._tokens = dict(tokens)
        self._connections_editable = connections_editable
        self._update_panel = update_panel if update_panel is not None else UpdatePanel(config, self)
        self._update_panel.install_requested.connect(self._request_install)
        self.connections_saved = False
        self._profiles = config.profiles()
        self._initial_profiles = [profile.to_dict() for profile in self._profiles]
        self._initial_theme = config.theme
        self._initial_auto_updates = config.get("updates/automatic")
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

        self.setWindowTitle(self.tr("Settings"))
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
            self._connections_button.setFocus(Qt.FocusReason.OtherFocusReason)
        else:
            self._pages.widget(0).setEnabled(False)
            self._appearance_button.click()
            self._appearance_button.setFocus(Qt.FocusReason.OtherFocusReason)
            self._set_result(self.tr("Connections are read-only while a response is running. You can still change the theme."), "hint")

    def _button(self, text: str, icon_name: str, slot) -> QPushButton:
        button = QPushButton(text)
        button.setIcon(icons.icon(icon_name, self._tokens["text_muted"], 18))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setAutoDefault(False)
        button.clicked.connect(slot)
        return button

    def _build_ui(self) -> None:
        self._heading = QLabel(self.tr("Settings"))
        self._heading.setObjectName("SettingsTitle")
        self._subtitle = QLabel(self.tr("Manage your connections and application preferences."))
        self._subtitle.setObjectName("SettingsHelp")
        self._subtitle.setWordWrap(True)

        navigation = QHBoxLayout()
        self._connections_button = QPushButton(self.tr("Connections"))
        self._appearance_button = QPushButton(self.tr("Appearance"))
        self._updates_button = QPushButton(self.tr("Updates"))
        self._about_button = QPushButton(self.tr("About"))
        self._navigation = QButtonGroup(self)
        self._pages = QStackedWidget()
        for index, button in enumerate((self._connections_button, self._appearance_button, self._updates_button, self._about_button)):
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
        self._profile_list.setAccessibleName(self.tr("Connection to edit"))
        self._profile_list.currentIndexChanged.connect(self._select_profile)
        self._add_button = self._button(self.tr("Add"), "plus", self._add_profile)
        self._add_button.setAccessibleName(self.tr("Add connection"))
        self._delete_button = self._button(self.tr("Remove"), "trash", self._delete_profile)
        self._delete_button.setAccessibleName(self.tr("Remove connection"))
        self._delete_button.setToolTip(self.tr("Stage removal of this connection until you save changes"))
        profile_row = QHBoxLayout()
        profile_label = QLabel(self.tr("&Connection"))
        profile_label.setBuddy(self._profile_list)
        profile_row.addWidget(profile_label)
        profile_row.addWidget(self._profile_list, 1)
        profile_row.addWidget(self._add_button)
        profile_row.addWidget(self._delete_button)
        self._connection_context = QLabel()
        self._connection_context.setObjectName("SettingsHelp")
        self._connection_context.setWordWrap(True)
        self._use_connection = self._button(self.tr("Use this connection"), "check", self._activate_profile)
        scope_row = QHBoxLayout()
        scope_row.addWidget(self._connection_context, 1)
        scope_row.addWidget(self._use_connection)

        self._name = QLineEdit()
        self._name.setPlaceholderText(self.tr("e.g. Work gateway or Local development"))
        self._name.textEdited.connect(self._rename_profile)
        self._provider = ChevronComboBox(theme.icon_color(self._tokens))
        self._provider.setMinimumContentsLength(10)
        self._provider.setSizeAdjustPolicy(
            ChevronComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        for info in provider_infos():
            self._provider.addItem(info.label, info.id)
        self._preset_button = self._button(self.tr("Apply preset"), "check", self._apply_preset)
        self._preset_button.setToolTip(self.tr("Replace this draft's endpoint and model list with preset values"))
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
        self._reveal_key.setToolTip(self.tr("Show API key"))
        self._reveal_key.setAccessibleName(self.tr("Show API key"))
        key_input_row = QHBoxLayout()
        key_input_row.addWidget(self._key, 1)
        key_input_row.addWidget(self._reveal_key)
        self._clear_key = QCheckBox(self.tr("Remove saved API key"))
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
        self._model.setToolTip(self.tr("Select a discovered model, or enter an ID manually"))
        self._fetch_button = self._button(self.tr("Fetch models"), "refresh", self._fetch_models)
        self._fetch_button.setToolTip(self.tr("Request models from this endpoint without saving changes"))
        self._stop_fetch = self._button(self.tr("Cancel fetch"), "stop", self._cancel_fetch)
        self._stop_fetch.hide()
        self._fetch_progress = QProgressBar()
        self._fetch_progress.setRange(0, 0)
        self._fetch_progress.setTextVisible(False)
        self._fetch_progress.setAccessibleName(self.tr("Fetching models"))
        self._fetch_progress.hide()
        self._models_filter = QLineEdit()
        self._models_filter.setPlaceholderText(self.tr("Filter models..."))
        self._models_filter.setAccessibleName(self.tr("Filter saved models"))
        self._models_filter.setClearButtonEnabled(True)
        self._models_filter.textChanged.connect(self._filter_models)
        self._models_list = QListWidget()
        self._models_list.setObjectName("ModelList")
        self._models_list.setMinimumHeight(100)
        self._models_list.setMaximumHeight(160)
        self._models_list.setAccessibleName(self.tr("Saved models"))
        self._models_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._models_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._models_list.currentItemChanged.connect(
            lambda item, previous: self._model.setCurrentText(item.text()) if item else None
        )
        self._models_list.itemClicked.connect(lambda item: self._model.setCurrentText(item.text()))
        self._model_count = QLabel()
        self._model_count.setObjectName("SettingsHelp")
        self._model_count.setWordWrap(True)
        self._delete_model_button = self._button(self.tr("Remove from list"), "trash", self._delete_model)
        self._delete_model_button.setToolTip(self.tr("Remove the selected model from this profile, not from the server"))
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
        self._include_usage = QCheckBox(self.tr("Request token usage from the API"))
        self._include_usage.setToolTip(self.tr(
            "Disable if your endpoint rejects stream_options. Missing usage is shown as N/A.",
        ))
        self._input_rate = NoWheelDoubleSpinBox()
        self._output_rate = NoWheelDoubleSpinBox()
        for control in (self._input_rate, self._output_rate):
            control.setDecimals(6)
            control.setRange(-1, 1_000_000)
            control.setSingleStep(0.1)
            control.setSpecialValueText(self.tr("Not configured"))
            control.setValue(-1)
        self._system_prompt = QPlainTextEdit()
        self._system_prompt.setObjectName("SystemPrompt")
        self._system_prompt.setMinimumHeight(100)
        self._system_prompt.setPlaceholderText(self.tr("Optional system instructions for this connection"))

        details = QGroupBox(self.tr("Connection details"))
        form = QFormLayout(details)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setVerticalSpacing(12)
        self._add_field(form, self.tr("Name"), self._name, self._name)
        self._add_field(form, self.tr("Provider preset"), preset_row, self._provider)
        self._add_field(form, self.tr("Base URL"), endpoint_layout, self._base_url,
                        self.tr("Use the API base address, such as {url}.").format(url="https://api.example.com/v1"))
        self._add_field(form, self.tr("API key"), key_layout, self._key)

        models = QGroupBox(self.tr("Models"))
        model_form = QFormLayout(models)
        model_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        model_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._add_field(model_form, self.tr("Default model"), models_layout, self._model,
                        self.tr("Choose a model or enter its ID. Fetching does not save your changes."))

        self._advanced = QGroupBox(self.tr("Response defaults (optional)"))
        self._advanced.setCheckable(True)
        self._advanced.setChecked(False)
        advanced_layout = QVBoxLayout(self._advanced)
        self._advanced_body = QWidget()
        response_form = QFormLayout(self._advanced_body)
        response_form.setContentsMargins(0, 4, 0, 0)
        response_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        response_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        response_form.setVerticalSpacing(12)
        self._add_field(response_form, self.tr("Temperature"), self._temperature, self._temperature,
                        self.tr("Higher values increase variation. Supported values depend on the model."))
        self._add_field(response_form, self.tr("Maximum output tokens"), self._max_tokens, self._max_tokens,
                        self.tr("Limits response length. The model may enforce a lower limit."))
        self._add_field(response_form, self.tr("Usage statistics"), self._include_usage, self._include_usage,
                        self.tr("TTFT measures request-to-first-text time. Total ends when the request finishes. Speed is API output tokens divided by total time minus TTFT."))
        self._add_field(response_form, self.tr("Input rate (USD / 1M tokens)"), self._input_rate, self._input_rate,
                        self.tr("For the selected model on this connection. Not configured means unknown; 0 means free."))
        self._add_field(response_form, self.tr("Output rate (USD / 1M tokens)"), self._output_rate, self._output_rate,
                        self.tr("Estimates use API token counts and these rates, excluding cache discounts and other billing adjustments."))
        self._add_field(response_form, self.tr("System instructions"), self._system_prompt, self._system_prompt,
                        self.tr("Instructions sent with requests using this connection, including existing chats."))
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
        theme_group = QGroupBox(self.tr("Application theme"))
        theme_layout = QVBoxLayout(theme_group)
        theme_help = QLabel(self.tr("Applies to the whole application after you save changes."))
        theme_help.setObjectName("SettingsHelp")
        theme_help.setWordWrap(True)
        theme_layout.addWidget(theme_help)
        self._theme_dark = QRadioButton(self.tr("Dark"))
        self._theme_light = QRadioButton(self.tr("Light"))
        self._theme_dark.setAccessibleName(self.tr("Dark application theme"))
        self._theme_light.setAccessibleName(self.tr("Light application theme"))
        theme_layout.addWidget(self._theme_dark)
        theme_layout.addWidget(self._theme_light)
        appearance_layout.addWidget(theme_group)
        appearance_layout.addStretch(1)
        self._pages.addWidget(appearance)

        updates = QWidget()
        updates.setObjectName("SettingsEditor")
        updates_layout = QVBoxLayout(updates)
        updates_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        updates_layout.setContentsMargins(0, 0, 12, 12)
        updates_layout.setSpacing(18)
        update_title = QLabel(self.tr("Application updates"))
        update_title.setObjectName("UpdateHeading")
        updates_layout.addWidget(update_title)
        installed = QLabel(self.tr("Installed: {version} (stable)").format(version=__version__))
        installed.setObjectName("SettingsHelp")
        updates_layout.addWidget(installed)
        updates_layout.addWidget(self._update_panel)
        self._update_panel.show()

        automatic = QGroupBox(self.tr("Automatic checks"))
        automatic_layout = QVBoxLayout(automatic)
        automatic_layout.setContentsMargins(0, 8, 0, 0)
        self._auto_updates = QCheckBox(self.tr("Check at startup"))
        self._auto_updates.setAccessibleName(self.tr("Check for updates automatically at startup"))
        self._auto_updates.setChecked(self._initial_auto_updates)
        self._auto_updates.toggled.connect(self._update_dirty)
        automatic_layout.addWidget(self._auto_updates)
        update_help = QLabel(self.tr(
            "Uses stable GitHub releases only. Startup checks and automatic installation require the packaged Windows app. "
            "Manual checks are always available."
        ))
        update_help.setObjectName("SettingsHelp")
        update_help.setWordWrap(True)
        automatic_layout.addWidget(update_help)
        updates_layout.addWidget(automatic)
        updates_layout.addStretch(1)
        self._updates_scroll = QScrollArea()
        self._updates_scroll.setObjectName("UpdatesScroll")
        self._updates_scroll.setWidgetResizable(True)
        self._updates_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._updates_scroll.setWidget(updates)
        self._pages.addWidget(self._updates_scroll)

        self._about = AboutPanel()
        self._pages.addWidget(self._about)

        self._status = QLabel()
        self._status.setWordWrap(True)
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        self._status.setObjectName("SettingsStatus")
        self._status.setAccessibleName(self.tr("Settings status"))
        self._status.hide()
        self._dirty_label = QLabel(self.tr("No unsaved changes"))
        self._dirty_label.setObjectName("SettingsHelp")
        self._save_button = self._button(self.tr("Save changes"), "check", self._save)
        self._save_button.setObjectName("Primary")
        self._save_button.setIcon(icons.icon("check", self._tokens["accent_text"], 18))
        self._cancel_button = QPushButton(self.tr("Cancel"))
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
        self._include_usage.toggled.connect(self._update_dirty)
        self._input_rate.valueChanged.connect(self._update_dirty)
        self._output_rate.valueChanged.connect(self._update_dirty)
        self._system_prompt.textChanged.connect(self._update_dirty)
        self._theme_light.toggled.connect(self._update_dirty)
        self._theme_dark.toggled.connect(self._update_dirty)
        tab_order = (
            self._connections_button, self._appearance_button, self._updates_button,
            self._about_button, self._profile_list,
            self._add_button, self._delete_button, self._use_connection,
            self._name, self._provider, self._preset_button, self._base_url,
            self._key, self._reveal_key, self._clear_key, self._model,
            self._fetch_button, self._stop_fetch, self._models_filter, self._models_list,
            self._delete_model_button, self._advanced, self._temperature,
            self._max_tokens, self._include_usage, self._input_rate, self._output_rate,
            self._system_prompt, self._theme_dark, self._theme_light,
            self._update_panel._action, self._update_panel._check, self._update_panel._cancel,
            self._update_panel._notes, self._update_panel._release_link,
            self._update_panel._skip, self._auto_updates,
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
        ) or self._auto_updates.isChecked() != self._initial_auto_updates

    def _request_install(self, path, release) -> None:
        if self._has_changes():
            answer = QMessageBox.question(
                self, self.tr("Unsaved changes"), self.tr("Save your changes before installing the update?"),
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer == QMessageBox.StandardButton.Save:
                if not self._save(close=False):
                    return
            elif answer != QMessageBox.StandardButton.Discard:
                return
        self.install_requested.emit(path, release)

    def _update_dirty(self, *_args) -> None:
        if not self._loading:
            self._dirty_label.setText(self.tr("Unsaved changes") if self._has_changes() else self.tr("No unsaved changes"))

    def _activate_profile(self) -> None:
        if self._current is not None:
            self._active_profile_id = self._current.id
            self._update_profile_context()
            self._update_dirty()

    def _update_profile_context(self) -> None:
        active = self._current is not None and self._current.id == self._active_profile_id
        self._connection_context.setText(
            self.tr("Active connection. Changes apply to future requests after saving.")
            if active else self.tr("Editing this connection does not make it active.")
        )
        self._use_connection.setEnabled(not active)

    def _stash(self) -> None:
        profile = self._current
        if profile is None or not self._connections_editable:
            return
        self._stash_model_rates()
        model = self._model.currentText().strip()
        if model != self._rate_model:
            self._show_model_rates(model)
        profile.name = self._name.text().strip() or self.tr("Untitled connection")
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
        profile.include_usage = self._include_usage.isChecked()
        if self._clear_key.isChecked():
            self._keys[profile.id] = None
        elif self._key.isModified():
            key = self._key.text().strip()
            if key:
                self._keys[profile.id] = key
            else:
                self._keys.pop(profile.id, None)

    def _stash_model_rates(self) -> None:
        if not self._rate_model:
            return
        rates = {}
        for key, control in (("input", self._input_rate), ("output", self._output_rate)):
            original, displayed = self._loaded_rates[key]
            value = original if control.value() == displayed else control.value()
            if value is not None and value >= 0:
                rates[key] = value
        if rates:
            self._current.model_rates[self._rate_model] = rates
        else:
            self._current.model_rates.pop(self._rate_model, None)

    def _show_model_rates(self, model: str) -> None:
        self._rate_model = model
        rates = self._current.model_rates.get(model, {})
        self._loaded_rates = {}
        for key, control in (("input", self._input_rate), ("output", self._output_rate)):
            value = rates.get(key)
            control.blockSignals(True)
            control.setValue(value if value is not None else -1)
            control.blockSignals(False)
            self._loaded_rates[key] = (value, control.value())

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
        self._include_usage.setChecked(profile.include_usage)
        self._show_model_rates(profile.model)
        self._system_prompt.setPlainText(profile.system_prompt)
        self._reveal_key.setChecked(False)
        self._key.setEchoMode(QLineEdit.EchoMode.Password)
        self._reveal_key.setIcon(icons.icon("eye", self._tokens["text_muted"], 18))
        self._reveal_key.setToolTip(self.tr("Show API key"))
        self._reveal_key.setAccessibleName(self.tr("Show API key"))
        self._key.setText(self._keys.get(profile.id) or "")
        self._key.setModified(False)
        self._clear_key.blockSignals(True)
        self._clear_key.setChecked(profile.id in self._keys and self._keys[profile.id] is None)
        self._clear_key.blockSignals(False)
        stored = self._credentials.has_secret(profile.credential_name)
        self._clear_key.setVisible(stored or profile.id in self._keys)
        self._key.setEnabled(not self._clear_key.isChecked())
        self._reveal_key.setEnabled(not self._clear_key.isChecked())
        self._key.setPlaceholderText(self.tr("Saved securely; leave blank to keep") if stored else self.tr("Optional API key"))
        key_help = (
            self.tr("A key is saved securely. Leave blank to keep it, or enter a replacement.")
            if stored else self.tr("Optional for endpoints that do not require authentication.")
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
            self._profile_list.currentIndex(), text.strip() or self.tr("Untitled connection")
        )

    def _add_profile(self) -> None:
        self._stash()
        profile = ConnectionProfile(name=self.tr("Connection {number}").format(number=len(self._profiles) + 1))
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
        self._set_result(self.tr("Connection removed from this draft. Cancel to discard the removal."), "hint")
        self._update_dirty()

    def _apply_preset(self) -> None:
        info = provider_info(str(self._provider.currentData()))
        if (
            self._base_url.text().strip() and self._base_url.text().strip() != info.base_url
            or self._available_models and self._available_models != list(info.models)
        ):
            answer = QMessageBox.question(
                self, self.tr("Apply provider preset?"),
                self.tr("Replace this draft's base URL and model list? The API key and response defaults will be kept."),
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
        self._set_result(self.tr("Preset applied to this draft only. Fetch models for the latest list."), "hint")
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
        action = self.tr("Hide API key") if visible else self.tr("Show API key")
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
        self._base_url_error.setText(self.tr("Error: {error}").format(error=error) if error else "")
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
            self._set_result(self.tr("Model discovery canceled. No changes were saved."), "hint")

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
        self._set_result(self.tr("Fetching available models..."), "hint")
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
        # Distinct sources keep English singular correct without a loaded catalog.
        if len(models) == 1:
            message = self.tr("%n model found. Changes have not been saved.", None, len(models))
        elif models:
            message = self.tr("%n models found. Changes have not been saved.", None, len(models))
        else:
            message = self.tr("No models returned. Enter a model ID manually. Changes have not been saved.")
        if models:
            message += " " + self.tr(
                "Listing a model does not verify inference access or deployment availability for your API key."
            )
        self._set_result(message, "success" if models else "hint")

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
        self._set_result(self.tr("Model removed from this draft, not the server. Fetching may add it again."), "hint")

    def _filter_models(self) -> None:
        query = self._models_filter.text().casefold()
        self._models_list.blockSignals(True)
        self._models_list.clear()
        matches = [model for model in self._available_models if query in model.casefold()]
        self._models_list.addItems(matches)
        self._models_list.blockSignals(False)
        total = len(self._available_models)
        if matches:
            message = (
                self.tr("{matches} of %n model", None, total)
                if total == 1 else self.tr("{matches} of %n models", None, total)
            ).format(matches=len(matches))
        elif self._available_models:
            message = self.tr("No matching models. Try another search.")
        else:
            message = self.tr("No saved models. Fetch models or enter an ID above.")
        self._model_count.setText(message)

    def _fetch_finished(self, message: str, kind: str) -> None:
        self._fetch_button.setEnabled(True)
        self._save_button.setEnabled(True)
        self._stop_fetch.hide()
        self._fetch_progress.hide()
        self._update_delete_model_button()
        self._set_result(message, kind)

    def _set_result(self, text: str, kind: str) -> None:
        if kind == "success":
            message = self.tr("Success: {message}").format(message=text)
        elif kind == "error":
            message = self.tr("Error: {message}").format(message=text)
        else:
            message = text
        self._status.setText(message)
        self._status.setAccessibleDescription(message)
        self._status.setProperty("status", kind)
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)
        self._status.show()

    def _save(self, *, close: bool = True) -> bool:
        if self._discovery.busy:
            self._set_result(self.tr("Wait for model discovery to finish before saving."), "hint")
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
                error = self.tr("Select a model from the list, or enter its ID manually.")
                field = self._model
            if error:
                self._pages.setCurrentIndex(0)
                self._connections_button.setChecked(True)
                self._profile_list.setCurrentIndex(row)
                self._set_result(self.tr("{connection}: {error}").format(connection=item.name, error=error), "error")
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
                if key is not None:
                    message = (
                        self.tr("Could not store the key for {connection}. No changes were saved.")
                        if restored else self.tr("Could not store the key for {connection}. Credential rollback failed; check stored keys before retrying.")
                    )
                else:
                    message = (
                        self.tr("Could not remove the key for {connection}. No changes were saved.")
                        if restored else self.tr("Could not remove the key for {connection}. Credential rollback failed; check stored keys before retrying.")
                    )
                self._set_result(message.format(connection=label), "error")
                return False
            applied.append(name)

        previous = self._config.profiles()
        previous_active = self._config.active_profile().id
        previous_theme = self._config.theme
        previous_auto_updates = self._config.get("updates/automatic")
        if connections_changed:
            self._config.save_profiles(self._profiles, self._active_profile_id)
        self._config.theme = "light" if self._theme_light.isChecked() else "dark"
        self._config.set("updates/automatic", self._auto_updates.isChecked())
        if not self._config.sync():
            if connections_changed:
                self._config.save_profiles(previous, previous_active)
            self._config.theme = previous_theme
            self._config.set("updates/automatic", previous_auto_updates)
            self._config.sync()
            restored = restore_credentials()
            message = (
                self.tr("Could not save connection settings. Previous key values restored.")
                if restored else self.tr("Could not save connection settings. Credential rollback failed; check stored keys before retrying.")
            )
            self._set_result(message, "error")
            return False
        self.connections_saved = self.connections_saved or connections_changed
        if close:
            self.accept()
        else:
            self._initial_profiles = [profile.to_dict() for profile in self._profiles]
            self._initial_active = self._active_profile_id
            self._initial_theme = self._config.theme
            self._initial_auto_updates = self._config.get("updates/automatic")
            self._removed.clear()
            self._update_dirty()
        return True

    def reject(self) -> None:
        if self._has_changes():
            answer = QMessageBox.question(
                self, self.tr("Unsaved changes"), self.tr("Save your changes before closing settings?"),
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
        self._update_panel.cancel()
        self._key.setEchoMode(QLineEdit.EchoMode.Password)
        self._key.clear()
        self._keys.clear()
        super().done(result)
