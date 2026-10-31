from __future__ import annotations

from app.core.providers.registry import get_provider, provider_infos


def test_endpoint_normalization() -> None:
    provider = get_provider("openai")
    assert provider.endpoint() == "https://api.openai.com/v1/chat/completions"
    assert provider.endpoint("http://host:1234/v1/") == "http://host:1234/v1/chat/completions"
    full = "http://host:1234/v1/chat/completions"
    assert provider.endpoint(full) == full


def test_headers_include_bearer_key() -> None:
    provider = get_provider("openai")
    assert provider.headers("abc")["Authorization"] == "Bearer abc"
    assert "Authorization" not in provider.headers(None)


def test_payload_streams_with_system_prompt() -> None:
    provider = get_provider("openai")
    payload = provider.payload(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.5,
        max_tokens=256,
        system_prompt="You are terse.",
    )
    assert payload["stream"] is True
    assert payload["temperature"] == 0.5
    assert payload["max_tokens"] == 256
    messages = payload["messages"]
    assert isinstance(messages, list)
    assert messages[0] == {"role": "system", "content": "You are terse."}
    assert messages[1]["content"] == "hi"


def test_payload_skips_empty_system_prompt() -> None:
    provider = get_provider("openai")
    payload = provider.payload("m", [{"role": "user", "content": "hi"}], 0.2, 64, "  ")
    messages = payload["messages"]
    assert isinstance(messages, list)
    assert len(messages) == 1


def test_parse_delta_variants() -> None:
    provider = get_provider("openai")
    assert provider.parse_delta('{"choices":[{"delta":{"content":"Hi"}}]}') == "Hi"
    assert provider.parse_delta('{"choices":[{"delta":{}}]}') is None
    assert provider.parse_delta('{"choices":[]}') is None
    assert provider.parse_delta("not json") is None
    assert provider.parse_delta('{"choices":[{"delta":{"content":[{"text":"A"},{"text":"B"}]}}]}') == "AB"


def test_registry_ids_are_unique() -> None:
    ids = [info.id for info in provider_infos()]
    assert len(ids) == len(set(ids))
    assert "openai" in ids
