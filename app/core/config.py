from __future__ import annotations

import json
from typing import Any

from PyQt6.QtCore import QByteArray, QSettings

from .profiles import ConnectionProfile
from .providers.registry import provider_infos

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

    def sync(self) -> bool:
        self._settings.sync()
        return self._settings.status() == QSettings.Status.NoError

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

    def profiles(self) -> list[ConnectionProfile]:
        raw = self._settings.value("connections/profiles", "", type=str)
        if raw:
            # Do not silently replace existing profiles if their data is corrupt.
            data = json.loads(raw)
            if not isinstance(data, list) or not data:
                raise ValueError("Saved connection profiles are invalid.")
            return [ConnectionProfile.from_dict(item) for item in data]

        profiles: list[ConnectionProfile] = []
        selected = str(self.get("provider", "openai"))
        for info in provider_infos():
            if info.id != selected and not any(
                self._settings.contains(f"{group}/{info.id}") for group in ("model", "base_url")
            ):
                continue
            profiles.append(ConnectionProfile(
                id=f"legacy-{info.id}",
                name=info.label,
                base_url=self.base_url_for(info.id) or info.base_url,
                model=self.model_for(info.id) or info.default_model,
                models=list(info.models),
                temperature=float(self.get("temperature")),
                max_tokens=int(self.get("max_tokens")),
                system_prompt=str(self.get("system_prompt")),
                preset=info.id,
                credential_name=info.id,
            ))
        if not profiles:
            profiles = [ConnectionProfile()]
        active_id = next((p.id for p in profiles if p.preset == selected), profiles[0].id)
        self.save_profiles(profiles, active_id)
        return profiles

    def save_profiles(self, profiles: list[ConnectionProfile], active_id: str) -> None:
        ids = [profile.id for profile in profiles]
        if not ids or len(set(ids)) != len(ids) or active_id not in ids:
            raise ValueError("Profiles must have unique IDs and a valid active selection.")
        self.set("connections/profiles", json.dumps([p.to_dict() for p in profiles]))
        self.set("connections/active", active_id)

    def active_profile(self) -> ConnectionProfile:
        profiles = self.profiles()
        selected = self.get("connections/active", "")
        return next((p for p in profiles if p.id == selected), profiles[0])

    def select_profile(self, profile_id: str) -> None:
        if not any(p.id == profile_id for p in self.profiles()):
            raise ValueError("Unknown connection profile.")
        self.set("connections/active", profile_id)

    def save_profile(self, profile: ConnectionProfile) -> None:
        profiles = self.profiles()
        for index, existing in enumerate(profiles):
            if existing.id == profile.id:
                profiles[index] = profile
                break
        else:
            profiles.append(profile)
        self.save_profiles(profiles, self.active_profile().id)

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
