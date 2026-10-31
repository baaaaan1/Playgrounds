from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSettings

from app.core.config import Config


def _config(path: Path) -> Config:
    return Config(QSettings(str(path), QSettings.Format.IniFormat))


def test_defaults(workdir: Path) -> None:
    config = _config(workdir / "settings.ini")
    assert config.theme == "dark"
    assert config.get("temperature") == 0.7
    assert config.get("max_tokens") == 2048
    assert config.model_for("openai") == ""


def test_persists_values(workdir: Path) -> None:
    path = workdir / "settings.ini"
    config = _config(path)
    config.theme = "light"
    config.set("temperature", 1.2)
    config.set_model_for("openai", "gpt-4o")
    config.set_base_url_for("custom", "http://localhost:8080/v1")
    config.sync()

    reloaded = _config(path)
    assert reloaded.theme == "light"
    assert reloaded.get("temperature") == 1.2
    assert reloaded.model_for("openai") == "gpt-4o"
    assert reloaded.base_url_for("custom") == "http://localhost:8080/v1"


def test_invalid_theme_falls_back_to_dark(workdir: Path) -> None:
    config = _config(workdir / "settings.ini")
    config.set("theme", "neon")
    assert config.theme == "dark"
