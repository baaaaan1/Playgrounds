from __future__ import annotations

from pathlib import Path

from app.core.models import Conversation, Message
from app.core.store import ConversationStore


def test_save_and_load_roundtrip(workdir: Path) -> None:
    store = ConversationStore(workdir)
    conversation = Conversation(title="Hello world")
    conversation.add(Message(role="user", content="Hi"))
    conversation.add(Message(role="assistant", content="Halo"))
    store.save(conversation)

    loaded = store.load(conversation.id)
    assert loaded is not None
    assert loaded.title == "Hello world"
    assert [message.content for message in loaded.messages] == ["Hi", "Halo"]


def test_list_orders_by_updated_at(workdir: Path) -> None:
    store = ConversationStore(workdir)
    first = Conversation(title="first")
    first.updated_at = 10.0
    second = Conversation(title="second")
    second.updated_at = 20.0
    store.save(first)
    store.save(second)

    titles = [conversation.title for conversation in store.list()]
    assert titles == ["second", "first"]


def test_delete_removes_file(workdir: Path) -> None:
    store = ConversationStore(workdir)
    conversation = Conversation()
    store.save(conversation)
    store.delete(conversation.id)
    assert store.load(conversation.id) is None


def test_load_unknown_returns_none(workdir: Path) -> None:
    store = ConversationStore(workdir)
    assert store.load("missing") is None


def test_title_derives_from_first_user_message() -> None:
    conversation = Conversation()
    conversation.add(Message(role="user", content="  Jelaskan   transformer  "))
    assert conversation.title == "Jelaskan transformer"
