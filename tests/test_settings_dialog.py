from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QSettings, Qt, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QGroupBox,
    QLineEdit,
    QMessageBox,
    QStackedWidget,
)

from app.core.config import Config
from app.core.profiles import ConnectionProfile
from app.ui import theme
from app.ui.settings_dialog import SettingsDialog


@pytest.fixture(autouse=True)
def discard_unsaved_changes(monkeypatch) -> None:
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Discard)


@pytest.fixture()
def credential_writes(credentials, monkeypatch):
    store = Mock(wraps=credentials.set_secret)
    remove = Mock(wraps=credentials.delete_secret)
    monkeypatch.setattr(credentials, "set_secret", store)
    monkeypatch.setattr(credentials, "delete_secret", remove)
    return store, remove


def _dialog(workdir: Path, credentials) -> SettingsDialog:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    return SettingsDialog(config, credentials, theme.tokens_for("dark"))


@pytest.mark.parametrize("modal", [False, True])
@pytest.mark.parametrize("connections_editable", [False, True])
def test_opening_settings_focuses_navigation_without_selecting_connection_name(
    qt_app, workdir, credentials, modal, connections_editable,
) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    dialog = SettingsDialog(
        config, credentials, theme.tokens_for("dark"), connections_editable=connections_editable,
    )
    expected = dialog._connections_button if connections_editable else dialog._appearance_button
    original_name = dialog._name.text()
    observed = []

    def inspect_and_close():
        observed.append((dialog.focusWidget(), dialog._name.selectedText(), dialog._has_changes()))
        dialog.reject()

    if modal:
        QTimer.singleShot(0, inspect_and_close)
        dialog.exec()
    else:
        dialog.show()
        dialog.activateWindow()
        qt_app.processEvents()
        inspect_and_close()
    assert observed == [(expected, "", False)]
    assert config.active_profile().name == original_name


def test_only_explicit_add_selects_new_connection_name(qt_app, workdir, credentials):
    dialog = _dialog(workdir, credentials)
    dialog.show()
    dialog.activateWindow()
    qt_app.processEvents()
    assert not dialog._name.hasSelectedText()
    dialog._add_button.click()
    assert dialog._name.hasFocus()
    assert dialog._name.selectedText() == dialog._name.text()
    dialog.reject()


@pytest.mark.parametrize("theme_name", ["dark", "light"])
def test_settings_tabs_keep_themed_keyboard_focus_border(qt_app, workdir, credentials, theme_name):
    old_palette, old_qss = qt_app.palette(), qt_app.styleSheet()
    theme.apply(qt_app, theme_name)
    dialog = _dialog(workdir, credentials)
    try:
        dialog.show()
        dialog.activateWindow()
        qt_app.processEvents()
        for button in (dialog._connections_button, dialog._appearance_button):
            button.setFocus(Qt.FocusReason.TabFocusReason)
            qt_app.processEvents()
            assert button.hasFocus()
            image = button.grab().toImage()
            assert image.pixelColor(image.width() // 2, 0).name() == theme.tokens_for(theme_name)["accent_strong"].lower()
    finally:
        dialog.reject()
        qt_app.setPalette(old_palette)
        qt_app.setStyleSheet(old_qss)


def test_custom_provider_allows_api_key(qt_app: QApplication, workdir: Path, credentials) -> None:
    dialog = _dialog(workdir, credentials)
    index = dialog._provider.findData("custom")
    dialog._provider.setCurrentIndex(index)
    assert dialog._key.isEnabled()
    dialog.close()


def test_openai_provider_allows_api_key(qt_app: QApplication, workdir: Path, credentials) -> None:
    dialog = _dialog(workdir, credentials)
    index = dialog._provider.findData("openai")
    dialog._provider.setCurrentIndex(index)
    assert dialog._key.isEnabled()
    dialog.close()


def test_show_hide_key_does_not_persist_visibility(qt_app, workdir, credentials) -> None:
    dialog = _dialog(workdir, credentials)
    profile = dialog._current
    credentials.set_secret(profile.credential_name, "stored-test-secret")
    assert dialog._key.echoMode() == QLineEdit.EchoMode.Password
    assert not dialog._key.text()
    dialog._reveal_key.click()
    assert dialog._key.text() == "stored-test-secret"
    assert dialog._key.echoMode() == QLineEdit.EchoMode.Normal
    dialog._reveal_key.click()
    assert dialog._key.echoMode() == QLineEdit.EchoMode.Password
    dialog._add_profile()
    assert not dialog._key.text()
    assert not dialog._reveal_key.isChecked()
    dialog.reject()


def test_profile_drafts_keys_and_settings_are_independent(qt_app, workdir, credentials) -> None:
    dialog = _dialog(workdir, credentials)
    first_id = dialog._current.id
    dialog._key.setText("first-key")
    dialog._key.setModified(True)
    dialog._temperature.setValue(0.2)
    dialog._system_prompt.setPlainText("First connection instructions")
    dialog._add_profile()
    dialog._name.setText("Second endpoint")
    dialog._base_url.setText("http://localhost:8080/v1")
    dialog._model.setCurrentText("second-model")
    dialog._key.setText("second-key")
    dialog._key.setModified(True)
    dialog._temperature.setValue(1.3)
    dialog._system_prompt.setPlainText("Second connection instructions")
    dialog._profile_list.setCurrentIndex(0)
    assert dialog._current.id == first_id
    assert dialog._key.text() == "first-key"
    assert dialog._temperature.value() == 0.2
    dialog._profile_list.setCurrentIndex(1)
    assert dialog._key.text() == "second-key"
    assert dialog._system_prompt.toPlainText() == "Second connection instructions"
    dialog._max_tokens.setValue(4096)
    dialog._theme_light.setChecked(True)
    dialog._save()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog._config.active_profile().id == first_id
    assert dialog._config.theme == "light"
    profiles = dialog._config.profiles()
    assert profiles[0].temperature == 0.2
    assert profiles[1].temperature == 1.3
    assert profiles[0].system_prompt == "First connection instructions"
    assert profiles[1].system_prompt == "Second connection instructions"
    assert profiles[1].name == "Second endpoint"
    assert profiles[1].base_url == "http://localhost:8080/v1"
    assert profiles[1].model == "second-model"
    assert profiles[1].max_tokens == 4096
    assert credentials.get_secret(profiles[0].credential_name) == "first-key"
    assert credentials.get_secret(profiles[1].credential_name) == "second-key"
    raw = dialog._config.get("connections/profiles", "")
    assert "first-key" not in raw and "second-key" not in raw
    reopened = _dialog(workdir, credentials)
    assert reopened._config.profiles() == profiles
    assert reopened._config.active_profile().id == first_id
    assert reopened._theme_light.isChecked()
    reopened.reject()


def test_cancel_discards_drafts_and_key_changes(qt_app, workdir, credentials) -> None:
    dialog = _dialog(workdir, credentials)
    original = dialog._config.get("connections/profiles", "")
    dialog._key.setText("not-saved")
    dialog._key.setModified(True)
    dialog._add_profile()
    dialog.reject()
    assert dialog._config.get("connections/profiles", "") == original
    assert not credentials.secrets


def test_credential_failure_keeps_dialog_open(qt_app, workdir, credentials) -> None:
    dialog = _dialog(workdir, credentials)
    credentials.fail_writes = True
    dialog._key.setText("not-saved")
    dialog._key.setModified(True)
    original = dialog._config.get("connections/profiles", "")
    dialog.show()
    dialog._save()
    assert dialog.isVisible()
    assert "Could not store" in dialog._status.text()
    assert dialog._config.get("connections/profiles", "") == original
    dialog.reject()


def test_model_selection_filter_and_fetch_cache(qt_app, workdir, credentials) -> None:
    dialog = _dialog(workdir, credentials)
    dialog._models_received(["alpha", "beta", "gamma"])
    assert dialog._models_list.count() == 3
    dialog._models_filter.setText("BET")
    assert dialog._models_list.count() == 1
    item = dialog._models_list.item(0)
    dialog._models_list.itemClicked.emit(item)
    assert dialog._model.currentText() == "beta"
    dialog._save()
    assert dialog._config.active_profile().models == ["alpha", "beta", "gamma"]
    assert dialog._config.active_profile().model == "beta"


def test_failed_model_fetch_preserves_cache(qt_app, workdir, credentials) -> None:
    dialog = _dialog(workdir, credentials)
    dialog._models_received(["alpha"])
    dialog._discovery.failed.emit("Unauthorized")
    assert dialog._available_models == ["alpha"]
    assert dialog._fetch_button.isEnabled()
    dialog.reject()


def test_model_fetch_only_updates_current_draft(qt_app, workdir, credentials, credential_writes, monkeypatch) -> None:
    dialog = _dialog(workdir, credentials)
    original = dialog._config.active_profile()
    settings_write = Mock(wraps=dialog._config.set)
    monkeypatch.setattr(dialog._config, "set", settings_write)
    dialog._name.setText("Unsaved name")
    dialog._key.setText("unsaved-key")
    dialog._key.setModified(True)
    dialog._theme_light.setChecked(True)
    dialog._add_profile()
    second = dialog._current
    dialog._name.setText("Fetched endpoint")
    dialog._base_url.setText("http://localhost:8080/v1")
    dialog._key.setText("fetched-key")
    dialog._key.setModified(True)
    read_secret = Mock(wraps=credentials.get_secret)
    monkeypatch.setattr(credentials, "get_secret", read_secret)
    dialog._models_received(["alpha", "beta"])
    read_secret.assert_not_called()
    settings_write.assert_not_called()
    assert not dialog.connections_saved
    assert dialog._current.models == ["alpha", "beta"]
    assert dialog._config.active_profile() == original
    assert dialog._config.theme == "dark"
    assert credentials.get_secret(original.credential_name) is None
    assert credentials.get_secret(second.credential_name) is None
    assert dialog._config.profiles() == [original]
    for operation in credential_writes:
        operation.assert_not_called()
    dialog._profile_list.setCurrentIndex(0)
    assert dialog._name.text() == "Unsaved name"
    assert dialog._key.text() == "unsaved-key"
    assert dialog._available_models == original.models
    dialog._profile_list.setCurrentIndex(1)
    assert dialog._current.id == second.id
    assert dialog._available_models == ["alpha", "beta"]
    assert dialog._model.currentText() == "alpha"
    dialog.reject()

    reopened = _dialog(workdir, credentials)
    profiles = reopened._config.profiles()
    assert profiles == [original]
    assert reopened._config.theme == "dark"
    assert not credentials.secrets
    reopened.reject()


def test_model_fetch_does_not_commit_pending_profile_deletion(qt_app, workdir, credentials) -> None:
    dialog = _dialog(workdir, credentials)
    original = dialog._config.active_profile()
    credentials.set_secret(original.credential_name, "keep-me")
    dialog._add_profile()
    dialog._base_url.setText("http://localhost:8080/v1")
    dialog._profile_list.setCurrentIndex(0)
    dialog._delete_profile()
    dialog._models_received(["alpha"])
    assert dialog._config.profiles() == [original]
    assert credentials.get_secret(original.credential_name) == "keep-me"
    assert dialog._config.active_profile().id == original.id
    dialog.reject()


@pytest.mark.parametrize("new_profile", [False, True])
@pytest.mark.parametrize("failure", ["credentials", "settings"])
def test_model_fetch_save_failure_rolls_back(qt_app, workdir, credentials, monkeypatch, new_profile, failure) -> None:
    dialog = _dialog(workdir, credentials)
    if new_profile:
        dialog._add_profile()
        dialog._base_url.setText("http://localhost:8080/v1")
    profile = dialog._current
    credentials.set_secret(profile.credential_name, "original")
    original_settings = dialog._config.get("connections/profiles", "")
    dialog._key.setText("replacement")
    dialog._key.setModified(True)
    if failure == "credentials":
        credentials.fail_writes = True
    else:
        monkeypatch.setattr(dialog._config, "sync", lambda: False)
    dialog._models_received(["alpha", "beta"])
    assert dialog._config.get("connections/profiles", "") == original_settings
    assert credentials.get_secret(profile.credential_name) == "original"
    dialog._save()
    assert "Could not" in dialog._status.text()
    assert not dialog.connections_saved
    assert dialog._config.get("connections/profiles", "") == original_settings
    assert credentials.get_secret(profile.credential_name) == "original"
    assert dialog._available_models == ["alpha", "beta"]
    assert dialog._fetch_button.isEnabled()
    assert dialog._save_button.isEnabled()
    dialog.reject()


def test_empty_model_fetch_only_updates_new_profile_draft(qt_app, workdir, credentials, credential_writes) -> None:
    dialog = _dialog(workdir, credentials)
    original = dialog._config.profiles()
    dialog._add_profile()
    dialog._base_url.setText("http://localhost:8080/v1")
    dialog._models_received([])
    assert dialog._current.models == []
    assert dialog._model.currentText() == ""
    assert dialog._config.profiles() == original
    assert not dialog.connections_saved
    for operation in credential_writes:
        operation.assert_not_called()
    dialog.reject()


def test_model_fetch_disables_save_until_finished(qt_app, workdir, credentials, monkeypatch) -> None:
    dialog = _dialog(workdir, credentials)
    calls = []
    monkeypatch.setattr(dialog._discovery, "fetch", lambda *args: calls.append(args))
    dialog._fetch_button.click()
    assert calls
    assert not dialog._fetch_button.isEnabled()
    assert not dialog._save_button.isEnabled()
    assert not dialog._delete_model_button.isEnabled()
    dialog._discovery.failed.emit("Unauthorized")
    assert dialog._fetch_button.isEnabled()
    assert dialog._save_button.isEnabled()
    assert dialog._delete_model_button.isEnabled()
    dialog._fetch_button.click()
    dialog._cancel_fetch()
    assert dialog._fetch_button.isEnabled()
    assert dialog._save_button.isEnabled()
    dialog.reject()


@pytest.mark.parametrize(
    "models,active,deleted,remaining,selected",
    [
        (["alpha", "beta"], "alpha", "alpha", ["beta"], "beta"),
        (["alpha", "beta"], "alpha", "beta", ["alpha"], "alpha"),
        (["alpha"], "alpha", "alpha", [], ""),
        ([], "manual-model", "manual-model", [], ""),
    ],
)
def test_delete_saved_model_only_changes_draft_and_cancel_preserves_saved_model(
    qt_app, workdir, credentials, credential_writes, models, active, deleted, remaining, selected,
) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    profile = ConnectionProfile(name="Saved", base_url="https://example.com/v1", model=active, models=models)
    config.save_profiles([profile], profile.id)
    dialog = SettingsDialog(config, credentials, theme.tokens_for("dark"))
    dialog.show()
    dialog._model.setCurrentText(deleted)
    dialog._delete_model_button.click()
    assert dialog.isVisible()
    assert not dialog.connections_saved
    assert config.active_profile() == profile
    for operation in credential_writes:
        operation.assert_not_called()
    assert dialog._available_models == remaining
    assert dialog._current.models == remaining
    assert dialog._model.currentText() == selected
    assert dialog._model.findText(deleted) == -1
    assert dialog._delete_model_button.isEnabled() == bool(selected)
    dialog.reject()

    reopened = _dialog(workdir, credentials)
    assert reopened._available_models == models
    assert reopened._model.currentText() == active
    reopened.reject()


def test_delete_saved_model_does_not_save_any_settings_or_profiles(qt_app, workdir, credentials) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    first = ConnectionProfile(name="First", model="alpha", models=["alpha", "beta"])
    second = ConnectionProfile(name="Second", model="alpha", models=["alpha", "gamma"])
    config.save_profiles([first, second], first.id)
    credentials.set_secret(second.credential_name, "original-key")
    dialog = SettingsDialog(config, credentials, theme.tokens_for("dark"))
    dialog._name.setText("Unsaved first")
    dialog._profile_list.setCurrentIndex(1)
    dialog._name.setText("Unsaved second")
    dialog._base_url.setText("http://localhost:8080/v1")
    dialog._key.setText("unsaved-key")
    dialog._key.setModified(True)
    dialog._theme_light.setChecked(True)
    dialog._models_filter.setText("ALP")
    dialog._models_list.itemClicked.emit(dialog._models_list.item(0))
    dialog._delete_model_button.click()
    saved = config.profiles()
    assert saved[0] == first
    assert saved[1] == second
    assert config.active_profile().id == first.id
    assert config.theme == "dark"
    assert credentials.get_secret(second.credential_name) == "original-key"
    assert dialog._models_list.count() == 0
    assert dialog._model.currentText() == "gamma"
    dialog.reject()


def test_delete_model_from_new_profile_only_changes_draft(qt_app, workdir, credentials) -> None:
    dialog = _dialog(workdir, credentials)
    original = dialog._config.get("connections/profiles", "")
    dialog._add_profile()
    dialog._provider.setCurrentIndex(dialog._provider.findData("openai"))
    dialog._apply_preset()
    model = dialog._model.currentText()
    assert model
    dialog._delete_model_button.click()
    assert model not in dialog._available_models
    assert dialog._model.currentText() != model
    assert dialog._model.currentText() == dialog._available_models[0]
    assert not dialog.connections_saved
    assert dialog._config.get("connections/profiles", "") == original
    dialog.reject()


def test_save_after_model_deletion_sync_failure_preserves_saved_model(qt_app, workdir, credentials, monkeypatch) -> None:
    dialog = _dialog(workdir, credentials)
    dialog._models_received(["alpha", "beta"])
    dialog._save()
    dialog = _dialog(workdir, credentials)
    original = dialog._config.active_profile()
    monkeypatch.setattr(dialog._config, "sync", lambda: False)
    dialog._delete_model_button.click()
    assert dialog._available_models == ["beta"]
    assert dialog._current.models == ["beta"]
    assert dialog._model.currentText() == "beta"
    dialog._save()
    assert "Could not save connection settings" in dialog._status.text()
    assert not dialog.connections_saved
    assert dialog._config.active_profile() == original
    assert dialog._available_models == ["beta"]
    dialog.reject()


def test_save_commits_deleted_model(qt_app, workdir, credentials) -> None:
    dialog = _dialog(workdir, credentials)
    dialog._models_received(["alpha", "beta"])
    dialog._save()
    dialog = _dialog(workdir, credentials)
    dialog._delete_model_button.click()
    assert dialog._config.active_profile().models == ["alpha", "beta"]
    dialog._save()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog._config.active_profile().models == ["beta"]
    assert dialog._config.active_profile().model == "beta"


def test_blank_edited_key_keeps_saved_key(qt_app, workdir, credentials) -> None:
    dialog = _dialog(workdir, credentials)
    reference = dialog._current.credential_name
    credentials.set_secret(reference, "keep-me")
    dialog._key.setText("")
    dialog._key.setModified(True)
    assert dialog._key_value() == "keep-me"
    dialog._save()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert credentials.get_secret(reference) == "keep-me"


def test_remove_key_can_be_undone_before_save(qt_app, workdir, credentials) -> None:
    dialog = _dialog(workdir, credentials)
    original_id = dialog._current.id
    reference = dialog._current.credential_name
    credentials.set_secret(reference, "keep-me")
    dialog._clear_key.setChecked(True)
    dialog._add_profile()
    dialog._base_url.setText("http://localhost:8080/v1")
    dialog._model.setCurrentText("second-model")
    dialog._profile_list.setCurrentIndex(0)
    assert dialog._current.id == original_id
    assert dialog._clear_key.isChecked()
    dialog._clear_key.setChecked(False)
    dialog._save()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert credentials.get_secret(reference) == "keep-me"


def test_explicit_key_removal(qt_app, workdir, credentials) -> None:
    dialog = _dialog(workdir, credentials)
    reference = dialog._current.credential_name
    credentials.set_secret(reference, "remove-me")
    dialog._clear_key.setChecked(True)
    dialog._save()
    assert not credentials.has_secret(reference)


def test_canceling_profile_deletion_does_not_remove_secret(qt_app, workdir, credentials) -> None:
    dialog = _dialog(workdir, credentials)
    reference = dialog._current.credential_name
    credentials.set_secret(reference, "keep-me")
    dialog._add_profile()
    dialog._profile_list.setCurrentIndex(0)
    dialog._delete_profile()
    dialog.reject()
    assert credentials.has_secret(reference)
    assert len(dialog._config.profiles()) == 1


def test_endpoint_edit_cancels_discovery_and_clears_old_model_list(qt_app, workdir, credentials, monkeypatch) -> None:
    dialog = _dialog(workdir, credentials)
    dialog._models_received(["old-model"])
    cancellations = []
    monkeypatch.setattr(dialog._discovery, "cancel", lambda: cancellations.append(True))
    dialog._endpoint_edited()
    assert cancellations
    assert dialog._models_list.count() == 0
    assert dialog._available_models == []
    dialog.reject()


@pytest.mark.parametrize("remove_first", [True, False])
def test_multi_profile_failed_write_restores_prior_keys(qt_app, workdir, credentials, monkeypatch, remove_first) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    first = ConnectionProfile(name="First", base_url="https://first.example/v1", model="a")
    second = ConnectionProfile(name="Second", base_url="https://second.example/v1", model="b")
    config.save_profiles([first, second], first.id)
    credentials.set_secret(first.credential_name, "first-original")
    credentials.set_secret(second.credential_name, "second-original")
    original_settings = config.get("connections/profiles", "")
    original_keys = dict(credentials.secrets)
    dialog = SettingsDialog(config, credentials, theme.tokens_for("dark"))
    if remove_first:
        dialog._clear_key.setChecked(True)
    else:
        dialog._key.setText("first-replacement")
        dialog._key.setModified(True)
    dialog._profile_list.setCurrentIndex(1)
    dialog._key.setText("second-replacement")
    dialog._key.setModified(True)
    write = credentials.set_secret
    monkeypatch.setattr(credentials, "set_secret", lambda name, key: False if name == second.credential_name else write(name, key))
    dialog._save()
    assert "Could not store" in dialog._status.text()
    assert config.get("connections/profiles", "") == original_settings
    assert credentials.secrets == original_keys
    dialog.reject()
    assert credentials.secrets == original_keys


def test_settings_sync_failure_restores_credentials_and_settings(qt_app, workdir, credentials, monkeypatch) -> None:
    dialog = _dialog(workdir, credentials)
    reference = dialog._current.credential_name
    credentials.set_secret(reference, "original")
    original_settings = dialog._config.get("connections/profiles", "")
    dialog._key.setText("replacement")
    dialog._key.setModified(True)
    dialog._name.setText("Unsaved name")
    dialog._theme_light.setChecked(True)
    monkeypatch.setattr(dialog._config, "sync", lambda: False)
    dialog._save()
    assert "Could not save connection settings" in dialog._status.text()
    assert credentials.get_secret(reference) == "original"
    assert dialog._config.get("connections/profiles", "") == original_settings
    assert dialog._config.theme == "dark"
    dialog.reject()


def test_failed_delete_restores_earlier_key_update(qt_app, workdir, credentials, monkeypatch) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    first = ConnectionProfile(name="First", base_url="https://first.example/v1", model="a")
    second = ConnectionProfile(name="Second", base_url="https://second.example/v1", model="b")
    config.save_profiles([first, second], first.id)
    credentials.set_secret(first.credential_name, "first-original")
    credentials.set_secret(second.credential_name, "second-original")
    original_keys = dict(credentials.secrets)
    dialog = SettingsDialog(config, credentials, theme.tokens_for("dark"))
    dialog._key.setText("first-replacement")
    dialog._key.setModified(True)
    dialog._profile_list.setCurrentIndex(1)
    dialog._clear_key.setChecked(True)
    monkeypatch.setattr(credentials, "delete_secret", lambda name: False)
    dialog._save()
    assert "Could not remove" in dialog._status.text()
    assert credentials.secrets == original_keys
    dialog.reject()


@pytest.mark.parametrize("invalid_field", ["base_url", "model"])
def test_save_validates_non_current_draft_before_any_credential_writes(
    qt_app, workdir, credentials, credential_writes, invalid_field,
) -> None:
    dialog = _dialog(workdir, credentials)
    original = dialog._config.profiles()
    first_id = dialog._current.id
    dialog._key.setText("first-key")
    dialog._key.setModified(True)
    if invalid_field == "base_url":
        dialog._base_url.setText("not-a-url")
    else:
        dialog._model.setCurrentText("")
    dialog._add_profile()
    dialog._base_url.setText("https://second.example/v1")
    dialog._model.setCurrentText("second-model")
    dialog._key.setText("second-key")
    dialog._key.setModified(True)
    dialog._theme_light.setChecked(True)
    dialog.show()
    dialog._appearance_button.click()
    dialog._save()
    qt_app.processEvents()
    assert dialog.isVisible()
    assert dialog._current.id == first_id
    assert dialog._profile_list.currentIndex() == 0
    assert dialog._pages.currentIndex() == 0
    invalid_control = dialog._base_url if invalid_field == "base_url" else dialog._model
    assert invalid_control.hasFocus()
    assert dialog._status.text()
    assert dialog._config.profiles() == original
    assert dialog._config.theme == "dark"
    assert not dialog.connections_saved
    for operation in credential_writes:
        operation.assert_not_called()
    dialog.reject()


@pytest.mark.parametrize("active_index", [0, 1])
def test_saving_another_profile_preserves_saved_active_profile(qt_app, workdir, credentials, active_index) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    profiles = [
        ConnectionProfile(name="First", base_url="https://first.example/v1", model="first-model"),
        ConnectionProfile(name="Second", base_url="https://second.example/v1", model="second-model"),
    ]
    config.save_profiles(profiles, profiles[active_index].id)
    dialog = SettingsDialog(config, credentials, theme.tokens_for("dark"))
    dialog._profile_list.setCurrentIndex(1 - active_index)
    dialog._name.setText("Edited, not activated")
    dialog._save()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert config.active_profile().id == profiles[active_index].id
    assert config.profiles()[1 - active_index].name == "Edited, not activated"


def test_saving_deleted_active_profile_uses_first_remaining_profile(qt_app, workdir, credentials) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    profiles = [
        ConnectionProfile(name=name, base_url=f"https://{name.lower()}.example/v1", model="model")
        for name in ["First", "Active", "Last"]
    ]
    config.save_profiles(profiles, profiles[1].id)
    credentials.set_secret(profiles[1].credential_name, "remove-with-profile")
    dialog = SettingsDialog(config, credentials, theme.tokens_for("dark"))
    dialog._delete_profile()
    dialog._profile_list.setCurrentIndex(1)
    assert config.active_profile().id == profiles[1].id
    assert credentials.has_secret(profiles[1].credential_name)
    dialog._save()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert config.active_profile().id == profiles[0].id
    assert [profile.id for profile in config.profiles()] == [profiles[0].id, profiles[2].id]
    assert not credentials.has_secret(profiles[1].credential_name)


@pytest.mark.parametrize(
    "choice",
    [QMessageBox.StandardButton.Save, QMessageBox.StandardButton.Discard, QMessageBox.StandardButton.Cancel],
)
def test_reject_dirty_dialog_respects_save_discard_cancel(qt_app, workdir, credentials, monkeypatch, choice) -> None:
    dialog = _dialog(workdir, credentials)
    original = dialog._config.profiles()
    reference = dialog._current.credential_name
    dialog._name.setText("Changed connection")
    dialog._key.setText("changed-key")
    dialog._key.setModified(True)
    dialog._theme_light.setChecked(True)
    question = Mock(return_value=choice)
    monkeypatch.setattr(QMessageBox, "question", question)
    dialog.show()
    dialog.reject()
    question.assert_called_once()
    args, kwargs = question.call_args
    buttons = kwargs.get("buttons", args[3] if len(args) > 3 else None)
    assert buttons == (
        QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel
    )
    if choice == QMessageBox.StandardButton.Save:
        assert dialog.result() == QDialog.DialogCode.Accepted
        assert not dialog.isVisible()
        assert dialog._config.active_profile().name == "Changed connection"
        assert dialog._config.theme == "light"
        assert credentials.get_secret(reference) == "changed-key"
    else:
        assert dialog.result() == QDialog.DialogCode.Rejected
        assert dialog.isVisible() == (choice == QMessageBox.StandardButton.Cancel)
        assert dialog._config.profiles() == original
        assert dialog._config.theme == "dark"
        assert not credentials.secrets
        if choice == QMessageBox.StandardButton.Cancel:
            assert dialog._name.text() == "Changed connection"
            assert dialog._key.text() == "changed-key"
            monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Discard)
            dialog.reject()


def test_reject_save_with_invalid_draft_keeps_dialog_open(qt_app, workdir, credentials, monkeypatch) -> None:
    dialog = _dialog(workdir, credentials)
    original = dialog._config.profiles()
    dialog._model.setCurrentText("")
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Save)
    dialog.show()
    dialog.reject()
    assert dialog.isVisible()
    assert dialog._config.profiles() == original
    assert not dialog.connections_saved
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Discard)
    dialog.reject()


def test_clean_reject_does_not_prompt(qt_app, workdir, credentials, monkeypatch) -> None:
    dialog = _dialog(workdir, credentials)
    question = Mock(return_value=QMessageBox.StandardButton.Cancel)
    monkeypatch.setattr(QMessageBox, "question", question)
    dialog.show()
    dialog.reject()
    question.assert_not_called()
    assert not dialog.isVisible()


def test_appearance_is_separate_and_response_controls_expand(qt_app, workdir, credentials) -> None:
    dialog = _dialog(workdir, credentials)
    dialog.show()
    assert isinstance(dialog._profile_list, QComboBox)
    assert isinstance(dialog._pages, QStackedWidget)
    assert dialog._pages.count() == 4
    assert dialog._pages.currentIndex() == 0
    assert dialog._base_url.isVisible()
    assert not dialog._theme_light.isVisible()
    assert isinstance(dialog._advanced, QGroupBox)
    assert dialog._advanced.isCheckable()
    assert not dialog._advanced.isChecked()
    assert not dialog._advanced_body.isVisible()
    assert not dialog._temperature.isVisible()
    dialog._advanced.setChecked(True)
    assert dialog._advanced_body.isVisible()
    assert dialog._temperature.isVisible()
    assert dialog._max_tokens.isVisible()
    assert dialog._system_prompt.isVisible()
    dialog._advanced.setChecked(False)
    assert not dialog._advanced_body.isVisible()
    dialog._appearance_button.click()
    assert dialog._pages.currentIndex() == 1
    assert dialog._theme_light.isVisible()
    assert dialog._theme_dark.isVisible()
    assert not dialog._base_url.isVisible()
    dialog._updates_button.click()
    assert dialog._pages.currentIndex() == 2
    assert dialog._auto_updates.isVisible()
    assert not dialog._theme_dark.isVisible()
    dialog._about_button.click()
    assert dialog._pages.currentWidget() is dialog._about
    assert dialog._about.isVisible()
    assert not dialog._auto_updates.isVisible()
    dialog._connections_button.click()
    assert dialog._pages.currentIndex() == 0
    assert dialog._base_url.isVisible()
    assert not dialog._has_changes()
    dialog.reject()


def test_settings_controls_have_accessible_names_and_save_is_not_default(qt_app, workdir, credentials) -> None:
    dialog = _dialog(workdir, credentials)
    for control in [
        dialog._profile_list, dialog._name, dialog._provider, dialog._base_url,
        dialog._key, dialog._model, dialog._models_filter, dialog._models_list,
        dialog._temperature, dialog._max_tokens, dialog._system_prompt,
        dialog._theme_light, dialog._theme_dark, dialog._reveal_key,
    ]:
        assert control.accessibleName(), control.objectName() or type(control).__name__
    assert dialog._reveal_key.accessibleName() == "Show API key"
    dialog._reveal_key.click()
    assert dialog._reveal_key.accessibleName() == "Hide API key"
    assert not dialog._save_button.autoDefault()
    assert not dialog._save_button.isDefault()
    dialog.reject()


def test_navigation_and_revealing_keys_do_not_mark_settings_dirty(qt_app, workdir, credentials, monkeypatch) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    profiles = [
        ConnectionProfile(name="First", base_url="https://first.example/v1", model="first-model"),
        ConnectionProfile(name="Second", base_url="https://second.example/v1", model="second-model"),
    ]
    config.save_profiles(profiles, profiles[0].id)
    credentials.set_secret(profiles[0].credential_name, "stored-key")
    dialog = SettingsDialog(config, credentials, theme.tokens_for("dark"))
    assert not dialog._has_changes()
    assert dialog._dirty_label.text() == "No unsaved changes"
    dialog._reveal_key.click()
    assert dialog._key.text() == "stored-key"
    assert not dialog._has_changes()
    dialog._profile_list.setCurrentIndex(1)
    dialog._profile_list.setCurrentIndex(0)
    dialog._appearance_button.click()
    dialog._connections_button.click()
    dialog._advanced.setChecked(True)
    assert not dialog._has_changes()
    assert dialog._dirty_label.text() == "No unsaved changes"
    question = Mock(return_value=QMessageBox.StandardButton.Cancel)
    monkeypatch.setattr(QMessageBox, "question", question)
    dialog.reject()
    question.assert_not_called()
    assert config.active_profile().id == profiles[0].id


@pytest.mark.parametrize("theme_name", ["dark", "light"])
@pytest.mark.parametrize("width,height", [(600, 480), (820, 780)])
def test_settings_layout_keeps_editor_and_footer_within_window(qt_app, workdir, credentials, theme_name, width, height) -> None:
    original_style = qt_app.styleSheet()
    theme.apply(qt_app, theme_name)
    dialog = _dialog(workdir, credentials)
    dialog._name.setText("Long connection " * 30)
    dialog._model.setCurrentText("long-model-id-" * 40)
    dialog.resize(width, height)
    dialog.show()
    qt_app.processEvents()
    try:
        assert dialog.width() == width
        assert dialog.height() == height
        assert dialog._heading.isVisible() == (height >= 620)
        assert dialog._scroll.widget().width() <= dialog._scroll.viewport().width()
        assert dialog._scroll.viewport().height() >= 130
        for control in (dialog._profile_list, dialog._cancel_button, dialog._save_button):
            assert dialog.rect().contains(control.mapTo(dialog, control.rect().topLeft()))
            assert dialog.rect().contains(control.mapTo(dialog, control.rect().bottomRight()))
        dialog._advanced.setChecked(True)
        qt_app.processEvents()
        assert dialog._scroll.widget().width() <= dialog._scroll.viewport().width()
    finally:
        dialog.reject()
        qt_app.setStyleSheet(original_style)


def test_keyboard_can_select_model_without_mouse(qt_app, workdir, credentials) -> None:
    dialog = _dialog(workdir, credentials)
    dialog._models_received(["alpha", "beta"])
    dialog.show()
    dialog._models_list.setFocus()
    dialog._models_list.setCurrentRow(0)
    QTest.keyClick(dialog._models_list, Qt.Key.Key_Down)
    assert dialog._model.currentText() == "beta"
    assert dialog._dirty_label.text() == "Unsaved changes"
    dialog.reject()


def test_key_typing_updates_unsaved_indicator(qt_app, workdir, credentials) -> None:
    dialog = _dialog(workdir, credentials)
    dialog.show()
    QTest.keyClicks(dialog._key, "replacement-key")
    assert dialog._dirty_label.text() == "Unsaved changes"
    assert not credentials.secrets
    dialog.reject()


def test_close_button_respects_keep_editing(qt_app, workdir, credentials, monkeypatch) -> None:
    dialog = _dialog(workdir, credentials)
    dialog.show()
    dialog._name.setText("Keep editing this connection")
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Cancel)
    dialog._title_bar.close_button.click()
    assert dialog.isVisible()
    assert dialog._name.text() == "Keep editing this connection"
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Discard)
    dialog._title_bar.close_button.click()
    assert not dialog.isVisible()


def test_inline_endpoint_validation_is_accessible_and_non_destructive(qt_app, workdir, credentials) -> None:
    dialog = _dialog(workdir, credentials)
    original = dialog._config.profiles()
    dialog._base_url.setText("not a URL")
    dialog._base_url.editingFinished.emit()
    assert not dialog._base_url_error.isHidden()
    assert "valid http" in dialog._base_url_error.text()
    assert "valid http" in dialog._base_url.accessibleDescription()
    assert dialog._config.profiles() == original
    dialog._base_url.setText("http://localhost:8080/v1")
    dialog._base_url.editingFinished.emit()
    assert dialog._base_url_error.isHidden()
    assert "API base address" in dialog._base_url.accessibleDescription()
    dialog.reject()


@pytest.mark.parametrize("answer", [QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No])
def test_applying_preset_confirms_overwriting_customized_draft(qt_app, workdir, credentials, monkeypatch, answer) -> None:
    dialog = _dialog(workdir, credentials)
    dialog._base_url.setText("http://localhost:8080/v1")
    dialog._key.setText("keep-draft-key")
    dialog._key.setModified(True)
    dialog._temperature.setValue(1.2)
    original = dialog._config.profiles()
    monkeypatch.setattr(QMessageBox, "question", lambda *args: answer)
    dialog._provider.setCurrentIndex(dialog._provider.findData("openai"))
    dialog._preset_button.click()
    assert dialog._base_url.text() == (
        "https://api.openai.com/v1" if answer == QMessageBox.StandardButton.Yes else "http://localhost:8080/v1"
    )
    assert dialog._key.text() == "keep-draft-key"
    assert dialog._temperature.value() == 1.2
    assert dialog._config.profiles() == original
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Discard)
    dialog.reject()


@pytest.mark.parametrize("theme_name", ["dark", "light"])
def test_settings_theme_contrast(theme_name) -> None:
    tokens = theme.tokens_for(theme_name)

    def luminance(color):
        channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
        return sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722), strict=True))

    for foreground, background, minimum in [
        ("text", "bg", 4.5), ("text_muted", "bg", 4.5),
        ("settings_success", "surface", 4.5), ("settings_error", "surface", 4.5),
        ("settings_control_border", "surface", 3), ("accent_strong", "surface", 3),
        ("accent_text", "accent", 4.5),
    ]:
        first, second = sorted([luminance(tokens[foreground]), luminance(tokens[background])])
        assert (second + 0.05) / (first + 0.05) >= minimum, (foreground, background)


@pytest.mark.parametrize("connections_editable", [False, True])
def test_appearance_save_does_not_validate_or_write_unchanged_connections(
    qt_app, workdir, credentials, credential_writes, monkeypatch, connections_editable,
) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    first = ConnectionProfile(name="First", base_url="https://example.com/v1", model="a", temperature=0.755, max_tokens=64)
    incomplete = ConnectionProfile(name="Incomplete connection")
    config.save_profiles([first, incomplete], first.id)
    dialog = SettingsDialog(config, credentials, theme.tokens_for("dark"), connections_editable=connections_editable)
    assert not dialog._has_changes()
    dialog._appearance_button.click()
    dialog._theme_light.setChecked(True)
    save_profiles = Mock(wraps=config.save_profiles)
    monkeypatch.setattr(config, "save_profiles", save_profiles)
    assert dialog._save()
    save_profiles.assert_not_called()
    assert config.profiles() == [first, incomplete]
    assert config.active_profile().id == first.id
    assert config.theme == "light"
    assert not dialog.connections_saved
    for write in credential_writes:
        write.assert_not_called()


def test_connection_edit_preserves_untouched_numeric_values(qt_app, workdir, credentials) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    first = ConnectionProfile(name="First", base_url="https://example.com/v1", model="a", temperature=0.755, max_tokens=200_000)
    config.save_profiles([first], first.id)
    dialog = SettingsDialog(config, credentials, theme.tokens_for("dark"))
    assert not dialog._has_changes()
    dialog._name.setText("Renamed connection")
    assert dialog._save()
    assert config.active_profile().name == "Renamed connection"
    assert config.active_profile().temperature == 0.755
    assert config.active_profile().max_tokens == 200_000


def test_dirty_indicator_tracks_edits_and_reverting_them(qt_app, workdir, credentials) -> None:
    dialog = _dialog(workdir, credentials)
    original_name = dialog._name.text()
    dialog._name.setText("Changed")
    assert dialog._has_changes()
    assert dialog._dirty_label.text() == "Unsaved changes"
    dialog._name.setText(original_name)
    assert not dialog._has_changes()
    assert dialog._dirty_label.text() == "No unsaved changes"
    dialog._theme_light.setChecked(True)
    assert dialog._has_changes()
    assert dialog._dirty_label.text() == "Unsaved changes"
    dialog._theme_dark.setChecked(True)
    assert not dialog._has_changes()
    assert dialog._dirty_label.text() == "No unsaved changes"
    dialog.reject()
