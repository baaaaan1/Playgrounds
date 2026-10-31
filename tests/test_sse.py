from __future__ import annotations

from app.net.sse import SSEParser


def test_single_event() -> None:
    parser = SSEParser()
    events = parser.feed(b"data: hello\n\n")
    assert len(events) == 1
    assert events[0].data == "hello"
    assert events[0].event == "message"


def test_multiple_events_in_one_chunk() -> None:
    parser = SSEParser()
    events = parser.feed(b"data: one\n\ndata: two\n\n")
    assert [event.data for event in events] == ["one", "two"]


def test_split_across_chunks() -> None:
    parser = SSEParser()
    assert parser.feed(b"data: hel") == []
    events = parser.feed(b"lo world\n\n")
    assert [event.data for event in events] == ["hello world"]


def test_multibyte_split_across_chunks() -> None:
    payload = 'data: {"text":"halo \U0001f600 dunia"}\n\n'.encode()
    parser = SSEParser()
    split = payload.index("\U0001f600".encode()) + 2
    assert parser.feed(payload[:split]) == []
    events = parser.feed(payload[split:])
    assert len(events) == 1
    assert "\U0001f600" in events[0].data


def test_crlf_separator() -> None:
    parser = SSEParser()
    events = parser.feed(b"data: value\r\n\r\n")
    assert [event.data for event in events] == ["value"]


def test_comments_and_fields() -> None:
    parser = SSEParser()
    block = b": keep-alive\nevent: delta\nid: 7\nretry: 1500\ndata: payload\n\n"
    events = parser.feed(block)
    assert len(events) == 1
    event = events[0]
    assert event.event == "delta"
    assert event.id == "7"
    assert event.retry == 1500
    assert event.data == "payload"
    assert event.comments == ["keep-alive"]


def test_multi_line_data_is_joined() -> None:
    parser = SSEParser()
    events = parser.feed(b"data: line 1\ndata: line 2\n\n")
    assert events[0].data == "line 1\nline 2"


def test_flush_parses_incomplete_event() -> None:
    parser = SSEParser()
    assert parser.feed(b"data: tail") == []
    events = parser.flush()
    assert [event.data for event in events] == ["tail"]


def test_done_marker() -> None:
    parser = SSEParser()
    events = parser.feed(b"data: [DONE]\n\n")
    assert events[0].data == "[DONE]"


def test_empty_block_is_ignored() -> None:
    parser = SSEParser()
    assert parser.feed(b"\n\n") == []
