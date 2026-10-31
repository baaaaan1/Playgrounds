from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    label: str
    base_url: str
    default_model: str
    models: tuple[str, ...] = ()
    requires_key: bool = True
    hint: str = ""


class Provider(Protocol):
    info: ProviderInfo

    def endpoint(self, base_url: str | None = None) -> str: ...

    def headers(self, api_key: str | None) -> dict[str, str]: ...

    def payload(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        system_prompt: str = "",
    ) -> dict[str, object]: ...

    def parse_delta(self, data: str) -> str | None: ...
