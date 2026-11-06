from __future__ import annotations

import json
from copy import deepcopy

import pytest
from PyQt6.QtCore import QObject, QSettings, pyqtSignal
from PyQt6.QtNetwork import QNetworkReply

from app.core.config import Config
from app.core.models import Conversation, Message
from app.core.profiles import ConnectionProfile
from app.core.providers.registry import get_provider
from app.core.store import ConversationStore
from app.net.client import StreamClient, error_message
from app.net.sse import SSEEvent
from app.ui.chat_controller import ChatController


@pytest.fixture()
def workflow(qt_app, workdir, credentials, monkeypatch):
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    profile = ConnectionProfile(name="Test", base_url="https://example.test/v1", model="test")
    config.save_profiles([profile], profile.id)
    store = ConversationStore(workdir / "chats")
    controller = ChatController(config, store, credentials)
    calls = []
    monkeypatch.setattr(controller._client, "start", lambda *args: calls.append(args))
    yield controller, store, calls
    controller.shutdown()


def finish(controller, text="Answer"):
    controller._on_delta(text)
    controller._on_completed()


def test_retry_reuses_user_and_replaces_partial(workflow):
    controller, store, calls = workflow
    assert controller.send("Question")
    controller._on_delta("Partial")
    controller._on_failed("Disconnected")
    user, partial = controller.conversation.messages
    assert partial.status == "failed"
    assert controller.retry(user.id)
    assert not controller.retry(user.id)
    assert calls[-1][2]["messages"] == [{"role": "user", "content": "Question"}]
    finish(controller, "Retried")
    saved = store.load(controller.conversation.id)
    assert [(m.role, m.content) for m in saved.messages] == [("user", "Question"), ("assistant", "Retried")]
    assert saved.messages[0].id == user.id
    assert saved.messages[1].id == partial.id
    assert saved.messages[1].status == "complete"


def test_zero_token_failure_is_retryable_after_reopen(workflow):
    controller, store, _ = workflow
    controller.send("Question")
    controller._on_failed("Failed")
    conversation = store.load(controller.conversation.id)
    assert conversation.last_attempt["status"] == "failed"
    controller.new_conversation()
    assert controller.open(conversation.id)
    assert controller.retry(conversation.messages[0].id)
    finish(controller)
    assert len(controller.conversation.messages) == 2


@pytest.mark.parametrize("outcome", ["failed", "stopped", "empty"])
def test_regeneration_keeps_original_on_unsuccessful_attempt(workflow, outcome):
    controller, store, calls = workflow
    controller.send("Question")
    finish(controller, "Original")
    original = deepcopy(controller.conversation.messages[-1])
    assert controller.regenerate(original.id)
    assert calls[-1][2]["messages"] == [{"role": "user", "content": "Question"}]
    if outcome != "empty":
        controller._on_delta("Unfinished replacement")
    if outcome == "failed":
        controller._on_failed("Failed")
    elif outcome == "stopped":
        controller.stop()
    else:
        controller._on_completed()
    assert controller.conversation.messages[-1] == original
    assert store.load(controller.conversation.id).messages[-1] == original
    assert controller.retry(controller.conversation.messages[0].id)
    finish(controller, "Replacement")
    assert len(controller.conversation.messages) == 2
    assert controller.conversation.messages[-1].content == "Replacement"


def test_regenerate_latest_turn_only_and_correct_history(workflow):
    controller, _, calls = workflow
    controller.send("First")
    finish(controller, "One")
    old_answer = controller.conversation.messages[-1].id
    controller.send("Second")
    finish(controller, "Two")
    assert not controller.regenerate(old_answer)
    assert controller.regenerate(controller.conversation.messages[-1].id)
    assert [m["content"] for m in calls[-1][2]["messages"]] == ["First", "One", "Second"]
    finish(controller, "New two")
    assert [m.content for m in controller.conversation.messages] == ["First", "One", "Second", "New two"]


def test_edit_forks_prefix_without_mutating_source(workflow):
    controller, store, calls = workflow
    controller.send("First")
    finish(controller, "One")
    controller.send("Second")
    finish(controller, "Two")
    controller.send("Third")
    finish(controller, "Three")
    source = controller.conversation
    source.pinned = True
    source.draft_text = "Unsent source draft"
    store.save(source)
    before = source.to_dict()
    assert controller.edit_and_fork(source.messages[2].id, "Edited second")
    fork = controller.conversation
    assert fork.id != source.id
    assert fork.forked_from_conversation_id == source.id
    assert fork.forked_from_message_id == source.messages[2].id
    assert not fork.pinned and not fork.archived and fork.draft_text == ""
    assert [m["content"] for m in calls[-1][2]["messages"]] == ["First", "One", "Edited second"]
    assert not {m.id for m in fork.messages} & {m.id for m in source.messages}
    controller._on_failed("Failed")
    assert source.to_dict() == before
    assert store.load(source.id).to_dict() == before


def test_stale_callbacks_do_not_affect_new_generation(workflow):
    controller, _, _ = workflow
    controller.send("First")
    stale_delta, stale_complete, stale_failure = controller._callbacks
    first_id = controller.conversation.id
    controller.new_conversation()
    assert controller.conversation.id != first_id
    assert controller.send("Second")
    stale_delta("Wrong chat")
    stale_complete()
    stale_failure("Stale failure")
    assert controller.busy
    assert controller._buffer == ""
    finish(controller, "Correct chat")
    assert [m.content for m in controller.conversation.messages] == ["Second", "Correct chat"]


def test_failed_save_does_not_send_or_clear_draft(workflow, monkeypatch):
    controller, store, calls = workflow
    conversation = controller.new_conversation()
    controller.set_draft(conversation.id, "Keep this")

    def fail_save(conversation):
        raise OSError("Disk full")

    monkeypatch.setattr(store, "save", fail_save)
    assert not controller.send("Keep this")
    assert calls == []
    assert controller.conversation.draft_text == "Keep this"
    assert controller.conversation.messages == []


def test_completion_save_failure_is_kept_and_flushable(workflow, monkeypatch):
    controller, store, _ = workflow
    controller.send("Question")
    save = store.save

    def fail_save(conversation):
        raise OSError("Disk full")

    monkeypatch.setattr(store, "save", fail_save)
    finish(controller, "Do not lose this answer")
    conversation_id = controller.conversation.id
    assert conversation_id in controller._unsaved
    controller.new_conversation()
    assert controller.open(conversation_id)
    assert controller.conversation.messages[-1].content == "Do not lose this answer"
    monkeypatch.setattr(store, "save", save)
    assert controller.flush()
    assert store.load(conversation_id).messages[-1].content == "Do not lose this answer"


def test_metadata_and_draft_do_not_change_activity_timestamp(workflow):
    controller, store, _ = workflow
    conversation = controller.new_conversation()
    activity = conversation.updated_at
    assert controller.set_draft(conversation.id, "Draft")
    assert controller.update_metadata(conversation.id, title="New chat", pinned=True, archived=True)
    assert controller.conversation.updated_at == activity
    assert controller.conversation.title_is_custom
    controller.send("Question")
    finish(controller)
    assert store.load(conversation.id).title == "New chat"
    assert controller.conversation.draft_text == ""


def test_legacy_ids_are_stable_and_invalid_files_are_skipped(workdir):
    store = ConversationStore(workdir)
    legacy = {"id": "old", "messages": [{"role": "user", "content": "Old"}]}
    (workdir / "old.json").write_text(json.dumps(legacy), encoding="utf-8")
    (workdir / "broken.json").write_text('{"messages": [null]}', encoding="utf-8")
    (workdir / "array.json").write_text('[]', encoding="utf-8")
    first = store.load("old")
    assert first.messages[0].id == store.load("old").messages[0].id
    assert not first.pinned and not first.archived and first.draft_text == ""
    assert [c.id for c in store.list()] == ["old"]
    store.save(first)
    assert store.load("old").to_dict() == first.to_dict()


def test_pending_attempt_recovers_as_interrupted(workflow):
    controller, store, _ = workflow
    conversation = Conversation(messages=[Message("user", "Question")])
    conversation.last_attempt = {"user_message_id": conversation.messages[0].id, "status": "pending"}
    store.save(conversation)
    assert controller.open(conversation.id)
    assert controller.conversation.last_attempt["status"] == "interrupted"
    assert controller.retry(conversation.messages[0].id)


def test_missing_profile_guard_applies_to_every_generation_action(workflow):
    controller, store, calls = workflow
    source = Conversation(profile_id="deleted", messages=[Message("user", "Question"), Message("assistant", "Answer")])
    controller.use(source)
    assert not controller.send("Follow up")
    assert not controller.regenerate(source.messages[-1].id)
    assert not controller.edit_and_fork(source.messages[0].id, "Edited")
    source.messages[-1].status = "failed"
    assert not controller.retry(source.messages[0].id)
    assert not calls
    controller.select_connection(controller._config.active_profile().id)
    assert controller.retry(source.messages[0].id)
    finish(controller)
    assert store.load(source.id).profile_id != "deleted"


def test_sse_error_and_non_object_events_are_not_successful_content(qt_app):
    client = StreamClient()
    client._provider = get_provider("openai")
    deltas = []
    client.delta.connect(deltas.append)
    client._handle_event(SSEEvent(data="[]"))
    client._handle_event(SSEEvent(data='{"error":{"message":"Quota exhausted"}}'))
    client._handle_event(SSEEvent(data='{"choices":[{"delta":{"content":"Wrong"}}]}'))
    assert client._stream_error == "Quota exhausted"
    assert deltas == []


def test_stale_network_reply_cannot_finalize_current_request(qt_app):
    class Reply(QObject):
        finished = pyqtSignal()

    client = StreamClient()
    old = Reply()
    current = Reply()
    old.finished.connect(client._on_finished)
    client._reply = current
    old.finished.emit()
    assert client._reply is current
    client._reply = None


def test_unterminated_sse_tail_is_flushed_on_finish(qt_app):
    class Reply(QObject):
        def readAll(self):  # noqa: N802
            return b""

        def attribute(self, name):
            return 200

        def error(self):
            return QNetworkReply.NetworkError.NoError

        def errorString(self):  # noqa: N802
            return ""

    client = StreamClient()
    client._provider = get_provider("openai")
    client._reply = Reply()
    client._parser.feed(b'data: {"choices":[{"delta":{"content":"Tail"}}]}')
    deltas = []
    client.delta.connect(deltas.append)
    client._on_finished()
    assert deltas == ["Tail"]


@pytest.mark.parametrize("body", [
    b"404 page not found\n",
    b'{"error":{"message":"The model is not available"}}',
    b'{"status":404,"title":"Not Found","detail":"Function is not available"}',
])
@pytest.mark.parametrize("split", [False, True])
def test_http_404_preserves_detail_and_fails_once_with_recovery_hint(qt_app, body, split):
    class Reply(QObject):
        def __init__(self):
            super().__init__()
            self.chunks = [body[:8], body[8:]] if split else [body]

        def readAll(self):  # noqa: N802
            return self.chunks.pop(0) if self.chunks else b""

        def attribute(self, name):
            return 404

        def error(self):
            return QNetworkReply.NetworkError.ContentNotFoundError

        def errorString(self):  # noqa: N802
            return "Not Found"

    client = StreamClient()
    client._provider = get_provider("openai")
    client._reply = Reply()
    failures, completions, deltas = [], [], []
    client.failed.connect(failures.append)
    client.completed.connect(lambda: completions.append(True))
    client.delta.connect(deltas.append)
    if split:
        client._on_ready_read()
    client._on_finished()
    assert len(failures) == 1
    assert "Check the base URL" in failures[0]
    assert "available on this connection" in failures[0]
    assert failures[0].endswith(error_message(body))
    assert not completions and not deltas
    assert not client.busy


@pytest.mark.parametrize("payload, expected", [
    ({"status": 404, "title": "Not Found", "detail": "Deployment unavailable"}, "Deployment unavailable"),
    ({"status": 404, "title": "Not Found"}, "Not Found"),
    ({"message": "Primary error", "detail": "Additional detail"}, "Primary error"),
    ({"error": {"message": "Nested error"}, "detail": "Additional detail"}, "Nested error"),
    ({"detail": {"unexpected": "object"}, "title": "Not Found"}, "Not Found"),
    ({"detail": "", "title": "Not Found"}, "Not Found"),
])
def test_problem_json_error_details_are_extracted(payload, expected):
    assert error_message(json.dumps(payload).encode()) == expected


def test_nvidia_function_account_404_reports_deployment_access_not_url():
    detail = "Function 'test-function': Not found for account 'test-account'"
    body = json.dumps({"status": 404, "title": "Not Found", "detail": detail}).encode()
    message = StreamClient._describe_http(404, body)
    assert "deployment is unavailable for this API account" in message
    assert "may be retired or access may be restricted" in message
    assert "Choose another model" in message
    assert "Check the base URL" not in message
    assert message.endswith(detail)
    assert '"status"' not in message
    assert "deployment is unavailable" not in StreamClient._describe_http(500, body)


@pytest.mark.parametrize("partial", ["", "Partial answer"])
def test_failure_reason_is_sanitized_persisted_and_emitted_once(workflow, credentials, partial):
    controller, store, _ = workflow
    profile = controller._config.active_profile()
    credentials.set_secret(profile.credential_name, "secret-test-key")
    errors = []
    controller.error.connect(errors.append)
    assert controller.send("Question")
    if partial:
        controller._on_delta(partial)
    controller._on_failed("Unauthorized: Bearer secret-test-key\napi_key=other-secret")
    saved = store.load(controller.conversation.id)
    message = saved.last_attempt["error"]
    assert saved.last_attempt["status"] == "failed"
    assert "secret-test-key" not in message
    assert "other-secret" not in message
    assert "\n" not in message
    assert "Unauthorized" in message
    assert errors == [message]
    controller.new_conversation()
    assert controller.open(saved.id)
    assert controller.conversation.last_attempt["error"] == message
    assert controller.retry(saved.messages[0].id)
    assert "error" not in controller.conversation.last_attempt
    finish(controller)
    assert "error" not in store.load(saved.id).last_attempt


def test_empty_response_keeps_actionable_failure_reason(workflow):
    controller, store, _ = workflow
    assert controller.send("Question")
    controller._on_completed()
    attempt = store.load(controller.conversation.id).last_attempt
    assert attempt["status"] == "failed"
    assert "No response" in attempt["error"]
