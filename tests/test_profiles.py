from __future__ import annotations

import pytest
from PyQt6.QtCore import QSettings

from app.core.config import Config
from app.core.profiles import ConnectionProfile, endpoint_url


def test_legacy_provider_settings_and_key_references_migrate(workdir) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    config.set("provider", "custom")
    config.set_base_url_for("custom", "https://gateway.example/v1")
    config.set_model_for("custom", "my-model")
    config.set_base_url_for("groq", "https://second.example/v1")
    config.set("temperature", 1.2)
    profiles = config.profiles()
    selected = config.active_profile()
    assert selected.id == "legacy-custom"
    assert selected.base_url == "https://gateway.example/v1"
    assert selected.model == "my-model"
    assert selected.temperature == 1.2
    assert selected.credential_name == "custom"
    assert {p.preset for p in profiles} == {"custom", "groq"}
    config.set_base_url_for("custom", "https://ignored-legacy-value.example")
    assert config.active_profile().base_url == "https://gateway.example/v1"


def test_same_provider_profiles_remain_independent(workdir) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    first = ConnectionProfile(name="Work", preset="custom", base_url="https://work.example/v1")
    second = ConnectionProfile(name="Home", preset="custom", base_url="http://localhost:8080/v1")
    config.save_profiles([first, second], second.id)
    first.model = "work-model"
    first.models = ["work-model"]
    config.save_profile(first)
    assert config.active_profile().id == second.id
    assert config.active_profile().model == ""
    assert first.credential_name != second.credential_name
    config.select_profile(first.id)
    assert config.active_profile().model == "work-model"


def test_profile_selection_is_validated(workdir) -> None:
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    with pytest.raises(ValueError):
        config.select_profile("does-not-exist")
    with pytest.raises(ValueError):
        config.save_profiles([], "missing")


@pytest.mark.parametrize("suffix", ["", "/", "/models", "/chat/completions"])
def test_endpoint_suffix_normalization(suffix) -> None:
    assert endpoint_url("https://gateway.example/v1" + suffix, "models") == "https://gateway.example/v1/models"
    assert endpoint_url("https://gateway.example/v1" + suffix, "chat/completions") == "https://gateway.example/v1/chat/completions"


@pytest.mark.parametrize("url", ["", "file:///etc/passwd", "https://user:pass@host/v1", "https://host/v1?api_key=x", "https://host/v1#fragment"])
def test_invalid_or_secret_bearing_urls_rejected(url) -> None:
    with pytest.raises(ValueError):
        endpoint_url(url, "models")
