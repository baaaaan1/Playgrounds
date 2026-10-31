from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QByteArray, QSettings

DEFAULTS: dict[str, Any] = {
    "theme": "dark",
    "provider": "openai",
    "temperature": 0.7,
    "max_tokens": 2048,
    "system_prompt": "",
    "sidebar_visible": True,
    "last_conversation": "",
}


class Config:
    """Typed wrapper around QSettings for non-secret preferences."""

    def __init__(self, settings: QSettings | None = None) -> None:
        self._settings = settings or QSettings("Playgrounds", "Playgrounds")

    def get(self, key: str, default: Any = None) -> Any:
        fallback = DEFAULTS.get(key, default)
        if fallback is None:
            return self._settings.value(key, None)
        return self._settings.value(key, fallback, type=type(fallback))

    def set(self, key: str, value: Any) -> None:
        self._settings.setValue(key, value)

    def sync(self) -> None:
        self._settings.sync()

    @property
    def theme(self) -> str:
        theme = str(self.get("theme", "dark"))
        return theme if theme in {"dark", "light"} else "dark"

    @theme.setter
    def theme(self, value: str) -> None:
        self.set("theme", "light" if value == "light" else "dark")

    def model_for(self, provider_id: str) -> str:
        return str(self._settings.value(f"model/{provider_id}", "", type=str))

    def set_model_for(self, provider_id: str, model: str) -> None:
        self._settings.setValue(f"model/{provider_id}", model)

    def base_url_for(self, provider_id: str) -> str:
        return str(self._settings.value(f"base_url/{provider_id}", "", type=str))

    def set_base_url_for(self, provider_id: str, base_url: str) -> None:
        self._settings.setValue(f"base_url/{provider_id}", base_url)

    def geometry(self) -> QByteArray | None:
        value = self._settings.value("window/geometry")
        return value if isinstance(value, QByteArray) else None

    def set_geometry(self, geometry: QByteArray) -> None:
        self._settings.setValue("window/geometry", geometry)

    def splitter_state(self) -> QByteArray | None:
        value = self._settings.value("window/splitter")
        return value if isinstance(value, QByteArray) else None

    def set_splitter_state(self, state: QByteArray) -> None:
        self._settings.setValue("window/splitter", state)
