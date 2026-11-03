from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlsplit, urlunsplit


def endpoint_url(base_url: str, resource: str) -> str:
    """Resolve a resource without duplicating a pasted completions/models suffix."""
    parts = urlsplit(base_url.strip())
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("Use a valid http:// or https:// base URL.")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("Base URL must not contain credentials, query parameters, or a fragment.")
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

    def __post_init__(self) -> None:
        if not self.credential_name:
            self.credential_name = f"profile/{self.id}"

    def to_dict(self) -> dict[str, Any]:
        # Only a credential reference is persisted, never the secret itself.
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConnectionProfile:
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{key: value for key, value in data.items() if key in allowed})
