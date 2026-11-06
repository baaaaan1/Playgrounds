from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from math import isfinite
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from PyQt6.QtCore import QCoreApplication


def endpoint_url(base_url: str, resource: str) -> str:
    """Resolve a resource without duplicating a pasted completions/models suffix."""
    parts = urlsplit(base_url.strip())
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError(QCoreApplication.translate(
            "ConnectionProfile", "Use a valid http:// or https:// base URL.",
        ))
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError(QCoreApplication.translate(
            "ConnectionProfile", "Base URL must not contain credentials, query parameters, or a fragment.",
        ))
    path = parts.path.rstrip("/")
    for suffix in ("/chat/completions", "/models"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    return urlunsplit((parts.scheme, parts.netloc, f"{path}/{resource}", "", ""))


@dataclass
class ConnectionProfile:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    name: str = "New connection"
    base_url: str = ""
    model: str = ""
    models: list[str] = field(default_factory=list)
    temperature: float = 0.7
    max_tokens: int = 2048
    system_prompt: str = ""
    preset: str = "custom"
    credential_name: str = ""
    include_usage: bool = True
    model_rates: dict[str, dict[str, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.credential_name:
            self.credential_name = f"profile/{self.id}"

    def to_dict(self) -> dict[str, Any]:
        # Only a credential reference is persisted, never the secret itself.
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConnectionProfile:
        allowed = cls.__dataclass_fields__.keys()
        values = {key: value for key, value in data.items() if key in allowed}
        rates = values.get("model_rates")
        values["model_rates"] = {
            model: {
                key: value for key, value in rate.items()
                if key in {"input", "output"} and type(value) in {int, float}
                and isfinite(value) and value >= 0
            }
            for model, rate in (rates.items() if isinstance(rates, dict) else [])
            if isinstance(model, str) and isinstance(rate, dict)
        }
        return cls(**values)
