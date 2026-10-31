from __future__ import annotations

import re
from dataclasses import dataclass, field

_SEPARATOR = re.compile(rb"\r?\n\r?\n")


@dataclass
class SSEEvent:
    data: str = ""
    event: str = "message"
    id: str | None = None
    retry: int | None = None
    comments: list[str] = field(default_factory=list)


class SSEParser:
    """Incremental server-sent events parser.

    Feed raw bytes as they arrive; only complete events are decoded so that
    multi-byte UTF-8 sequences split across network chunks are safe.
    """

    def __init__(self) -> None:
        self._buffer = bytearray()

    def reset(self) -> None:
        self._buffer.clear()

    def feed(self, chunk: bytes) -> list[SSEEvent]:
        if chunk:
            self._buffer.extend(chunk)
        events: list[SSEEvent] = []
        while True:
            match = _SEPARATOR.search(self._buffer)
            if match is None:
                break
            block = bytes(self._buffer[: match.start()])
            del self._buffer[: match.end()]
            event = self._parse_block(block)
            if event is not None:
                events.append(event)
        return events

    def flush(self) -> list[SSEEvent]:
        """Parse whatever remains without a trailing blank line."""
        if not self._buffer:
            return []
        block = bytes(self._buffer)
        self._buffer.clear()
        event = self._parse_block(block)
        return [event] if event is not None else []

    @staticmethod
    def _parse_block(block: bytes) -> SSEEvent | None:
        if not block.strip():
            return None
        data_lines: list[str] = []
        comments: list[str] = []
        event = SSEEvent()
        has_field = False
        for raw_line in block.splitlines():
            line = raw_line.decode("utf-8", errors="replace")
            if not line:
                continue
            if line.startswith(":"):
                comments.append(line[1:].lstrip())
                continue
            name, _, value = line.partition(":")
            if value.startswith(" "):
                value = value[1:]
            if name == "data":
                data_lines.append(value)
                has_field = True
            elif name == "event":
                event.event = value or "message"
                has_field = True
            elif name == "id":
                event.id = value
                has_field = True
            elif name == "retry":
                try:
                    event.retry = int(value)
                except ValueError:
                    pass
                has_field = True
        event.data = "\n".join(data_lines)
        event.comments = comments
        if not has_field and not comments:
            return None
        return event
