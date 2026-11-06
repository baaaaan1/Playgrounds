from __future__ import annotations

import json

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QDialog, QMessageBox

from app.core.config import Config
from app.core.models import Conversation, Message, ResponseStatistics
from app.core.profiles import ConnectionProfile
from app.core.providers.registry import get_provider
from app.core.store import ConversationStore
from app.net.client import StreamClient
from app.net.sse import SSEEvent
from app.ui import chat_controller, theme
from app.ui.chat_controller import ChatController
from app.ui.chat_view import ChatView
from app.ui.settings_dialog import SettingsDialog


@pytest.fixture()
def statistics_workflow(qt_app, workdir, credentials, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(chat_controller, "monotonic", lambda: now[0])
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    profile = ConnectionProfile(
        name="Test", base_url="https://example.test/v1", model="alpha",
        model_rates={"alpha": {"input": 2.0, "output": 8.0}},
    )
    config.save_profiles([profile], profile.id)
    store = ConversationStore(workdir / "chats")
    controller = ChatController(config, store, credentials)
    calls = []
    monkeypatch.setattr(controller._client, "start", lambda *args: calls.append(args))
    yield controller, store, config, calls, now
    controller.shutdown()


def test_usage_timing_speed_and_cost_survive_reopen(statistics_workflow):
    controller, store, config, calls, now = statistics_workflow
    controller.send("Question")
    assert calls[0][2]["stream_options"] == {"include_usage": True}
    # Later configuration changes must not reprice an in-flight or historical response.
    profile = config.active_profile()
    profile.model_rates["alpha"] = {"input": 100, "output": 200}
    config.save_profiles([profile], profile.id)
    now[0] = 101
    controller._client.delta.emit("Answer")
    now[0] = 106
    controller._client.usage.emit({"input_tokens": 1000, "output_tokens": 250})
    controller._client.completed.emit()
    message = store.load(controller.conversation.id).messages[-1]
    assert message.thinking_seconds == 1
    assert message.statistics.duration_seconds == 6
    assert message.statistics.input_tokens == 1000
    assert message.statistics.output_tokens == 250
    assert message.statistics.tokens_per_second(message.thinking_seconds) == 50
    assert message.statistics.estimated_cost == pytest.approx(0.004)
    assert message.statistics.input_rate == 2
    assert message.statistics.output_rate == 8
    # Telemetry is not inserted into message content or future API history.
    assert message.content == "Answer"
    controller.send("Follow up")
    assert calls[-1][2]["messages"][-2] == {"role": "assistant", "content": "Answer"}


@pytest.mark.parametrize("finish", ["complete", "stop", "fail"])
def test_partial_and_missing_usage_are_not_fabricated(statistics_workflow, finish):
    controller, store, _, _, now = statistics_workflow
    controller.send("Question")
    now[0] = 102
    controller._client.delta.emit("Partial answer")
    controller._client.usage.emit({"input_tokens": 10})
    now[0] = 105
    if finish == "stop":
        controller.stop()
    elif finish == "fail":
        controller._client.failed.emit("Disconnected")
    else:
        controller._client.completed.emit()
    stats = store.load(controller.conversation.id).messages[-1].statistics
    assert stats.duration_seconds == 5
    assert stats.input_tokens == 10
    assert stats.output_tokens is None
    assert stats.tokens_per_second(2) is None
    assert stats.estimated_cost is None
    controller.send("Next")
    now[0] = 106
    controller._client.delta.emit("Next answer")
    now[0] = 108
    controller._client.completed.emit()
    stats = controller.conversation.messages[-1].statistics
    assert stats.duration_seconds == 3
    assert stats.input_tokens is None and stats.output_tokens is None


def test_usage_only_chunks_and_invalid_usage(qt_app):
    client = StreamClient()
    client._provider = get_provider("openai")
    received = []
    deltas = []
    client.usage.connect(received.append)
    client.delta.connect(deltas.append)
    for usage in (None, [], {}, {"prompt_tokens": True, "completion_tokens": -1},
                  {"prompt_tokens": "20", "completion_tokens": 2.5}):
        client._handle_event(SSEEvent(data=json.dumps({"choices": [], "usage": usage})))
    assert received == []
    client._handle_event(SSEEvent(data=json.dumps({
        "choices": [], "usage": {"prompt_tokens": 20, "completion_tokens": 0},
    })))
    client._handle_event(SSEEvent(data=json.dumps({
        "choices": [{"delta": {"content": "Answer"}}],
        "usage": {"input_tokens": 30, "output_tokens": 10},
    })))
    assert received == [
        {"input_tokens": 20, "output_tokens": 0},
        {"input_tokens": 30, "output_tokens": 10},
    ]
    assert deltas == ["Answer"]
    client._handle_event(SSEEvent(data="[DONE]"))
    client._handle_event(SSEEvent(data='{"usage":{"prompt_tokens":999}}'))
    assert len(received) == 2


def test_stale_usage_cannot_affect_new_response(statistics_workflow):
    controller, _, _, _, now = statistics_workflow
    controller.send("First")
    stale_usage = controller._usage_callback
    controller._client.delta.emit("First answer")
    controller._client.completed.emit()
    stale_usage({"input_tokens": 9000})
    controller.send("Second")
    stale_usage({"input_tokens": 9000})
    now[0] = 101
    controller._client.delta.emit("Second answer")
    controller._client.usage.emit({"output_tokens": 5})
    controller._client.usage.emit({"input_tokens": 8})
    now[0] = 103
    controller._client.completed.emit()
    stats = controller.conversation.messages[-1].statistics
    assert stats.input_tokens == 8 and stats.output_tokens == 5


def test_failed_regeneration_preserves_original_statistics(statistics_workflow):
    controller, _, _, _, now = statistics_workflow
    controller.send("Question")
    now[0] = 101
    controller._client.delta.emit("Original")
    controller._client.usage.emit({"input_tokens": 10, "output_tokens": 20})
    now[0] = 105
    controller._client.completed.emit()
    original = controller.conversation.messages[-1].to_dict()
    controller.regenerate(original["id"])
    now[0] = 106
    controller._client.delta.emit("Unfinished")
    controller._client.usage.emit({"input_tokens": 100, "output_tokens": 200})
    controller._client.failed.emit("Disconnected")
    assert controller.conversation.messages[-1].to_dict() == original
    controller.retry(controller.conversation.messages[0].id)
    now[0] = 107
    controller._client.delta.emit("Replacement")
    now[0] = 108
    controller._client.completed.emit()
    assert controller.conversation.messages[-1].id == original["id"]
    assert controller.conversation.messages[-1].statistics.input_tokens is None


def test_stream_usage_request_can_be_disabled(statistics_workflow):
    controller, _, config, calls, _ = statistics_workflow
    profile = config.active_profile()
    profile.include_usage = False
    config.save_profiles([profile], profile.id)
    controller.send("Question")
    assert "stream_options" not in calls[0][2]


def test_statistics_legacy_and_malformed_metadata(workdir):
    assert Message.from_dict({"role": "assistant", "content": "Old"}).statistics is None
    assert "statistics" not in Message("user", "Question").to_dict()
    for raw in (None, [], "invalid"):
        assert Message.from_dict({"statistics": raw}).statistics is None
    stats = ResponseStatistics.from_dict({
        "duration_seconds": float("nan"), "input_tokens": True, "output_tokens": 1.5,
        "input_rate": -1, "output_rate": "invalid", "extra": 10,
    })
    assert stats == ResponseStatistics()
    store = ConversationStore(workdir)
    conversation = Conversation(messages=[Message("assistant", "Answer", statistics=stats)])
    store.save(conversation)
    assert store.load(conversation.id).messages[0].statistics == stats


def test_speed_and_cost_require_complete_data_and_positive_generation_interval():
    stats = ResponseStatistics(duration_seconds=2, input_tokens=0, output_tokens=0,
                               input_rate=0, output_rate=0)
    assert stats.estimated_cost == 0
    assert stats.tokens_per_second(1) == 0
    assert stats.tokens_per_second(2) is None
    assert stats.tokens_per_second(3) is None
    assert stats.tokens_per_second(None) is None
    stats.input_rate = None
    assert stats.estimated_cost is None


@pytest.mark.parametrize("theme_name", ["dark", "light"])
def test_footer_for_each_assistant_not_users_and_not_copied(qt_app, theme_name):
    view = ChatView(theme.tokens_for(theme_name))
    message = Message("assistant", "Answer", thinking_seconds=1, statistics=ResponseStatistics(
        duration_seconds=6, input_tokens=1000, output_tokens=250, input_rate=2, output_rate=8,
    ))
    try:
        view.show_conversation(Conversation(messages=[Message("user", "Question"), message,
                                                     Message("assistant", "Legacy answer")]))
        text = view.toPlainText().replace("\xa0", " ")
        assert text.count("TTFT:") == 2
        assert "TTFT: 1.00s" in text and "Total: 6.00s" in text
        assert "Input: 1,000" in text and "Output: 250" in text
        assert "Speed: 50.0 tok/s" in text and "Est. cost: USD 0.004000" in text
        assert "TTFT: N/A" in text and "Est. cost: N/A" in text
        assert ("copy", "Answer") in view._actions.values()
        view.set_tokens(theme.tokens_for("light" if theme_name == "dark" else "dark"))
        assert view.toPlainText().count("TTFT:") == 2
    finally:
        view.close()


def test_rates_are_per_model_and_connection_and_save_only_on_confirmation(
    qt_app, workdir, credentials, monkeypatch,
):
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Discard)
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    first = ConnectionProfile(name="First", base_url="https://example.test/v1", model="alpha")
    second = ConnectionProfile(name="Second", base_url="https://other.test/v1", model="alpha")
    config.save_profiles([first, second], first.id)
    dialog = SettingsDialog(config, credentials, theme.tokens_for("dark"))
    assert not dialog._has_changes()
    dialog._input_rate.setValue(2)
    dialog._output_rate.setValue(8)
    dialog._model.setCurrentText("beta")
    assert dialog._input_rate.value() == -1
    dialog._input_rate.setValue(0)
    dialog._output_rate.setValue(1)
    dialog._model.setCurrentText("alpha")
    assert dialog._input_rate.value() == 2 and dialog._output_rate.value() == 8
    dialog._profile_list.setCurrentIndex(1)
    assert dialog._input_rate.value() == -1 and dialog._output_rate.value() == -1
    dialog._include_usage.setChecked(False)
    assert config.profiles() == [first, second]
    assert dialog._save()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert config.profiles()[0].model_rates == {
        "alpha": {"input": 2, "output": 8}, "beta": {"input": 0, "output": 1},
    }
    assert config.profiles()[1].model_rates == {}
    assert not config.profiles()[1].include_usage
    reopened = SettingsDialog(config, credentials, theme.tokens_for("dark"))
    assert reopened._input_rate.value() == 2
    assert not reopened._has_changes()
    reopened._input_rate.setValue(100)
    reopened.reject()
    assert config.profiles()[0].model_rates["alpha"]["input"] == 2


def test_profile_rates_validate_and_preserve_unedited_precision(qt_app, workdir, credentials):
    profile = ConnectionProfile.from_dict({
        "base_url": "https://example.test/v1", "model": "alpha",
        "model_rates": {
            "alpha": {"input": 0.123456789, "output": 0},
            "bad": {"input": float("inf"), "output": True, "extra": 2},
            "other": [],
        },
    })
    assert profile.model_rates == {"alpha": {"input": 0.123456789, "output": 0}, "bad": {}}
    config = Config(QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat))
    config.save_profiles([profile], profile.id)
    dialog = SettingsDialog(config, credentials, theme.tokens_for("dark"))
    assert not dialog._has_changes()
    dialog._name.setText("Renamed")
    assert dialog._save()
    assert config.active_profile().model_rates == profile.model_rates
