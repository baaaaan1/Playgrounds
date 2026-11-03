from __future__ import annotations

import html
from time import monotonic

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QFrame, QTextBrowser

from ..core.models import Conversation, Message
from .markdown import render_markdown

_LABELS = {"user": "ANDA", "assistant": "ASISTEN"}


class ChatView(QTextBrowser):
    """QTextBrowser that renders a conversation and streams new tokens."""

    def __init__(self, tokens: dict[str, str], parent=None) -> None:
        super().__init__(parent)
        self._tokens = dict(tokens)
        self._conversation: Conversation | None = None
        self._streaming = False
        self._pending = ""
        self._stream_text = ""
        self._stream_format = QTextCharFormat()
        self._thinking_started = 0.0
        self._thinking_seconds: float | None = None
        self._thinking_cursor: QTextCursor | None = None

        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setOpenExternalLinks(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().setDocumentMargin(56)
        self.setStyleSheet("background: transparent; border: none;")

        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(50)
        self._flush_timer.timeout.connect(self._flush)
        self._thinking_timer = QTimer(self)
        self._thinking_timer.setInterval(100)
        self._thinking_timer.timeout.connect(self._update_thinking)
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.timeout.connect(self._scroll_after_layout)

    def set_tokens(self, tokens: dict[str, str]) -> None:
        self._tokens = dict(tokens)
        if self._streaming:
            # The current response is not in the conversation until completion.
            text = self._stream_text + self._pending
            thinking_started = self._thinking_started
            thinking_seconds = self._thinking_seconds
            at_bottom = self._at_bottom()
            position = self.verticalScrollBar().value()
            self._rebuild()
            self.begin_stream()
            self._thinking_started = thinking_started
            if thinking_seconds is not None:
                self.set_thinking_time(thinking_seconds)
            else:
                self._update_thinking()
            self.feed(text)
            self._flush()
            if not at_bottom:
                self._scroll_timer.stop()
                self.verticalScrollBar().setValue(position)
        elif self._conversation is not None:
            self._rebuild()

    def show_conversation(self, conversation: Conversation | None) -> None:
        self._conversation = conversation
        self._rebuild()

    def clear_chat(self) -> None:
        self._streaming = False
        self._pending = ""
        self._stream_text = ""
        self._flush_timer.stop()
        self._thinking_timer.stop()
        self._thinking_cursor = None
        self._conversation = None
        self.clear()

    def begin_stream(self) -> None:
        self._streaming = True
        self._pending = ""
        self._stream_text = ""
        self._thinking_started = monotonic()
        self._thinking_seconds = None
        self._flush_timer.start()
        self._thinking_timer.start()

        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(
            f'<div style="margin-top:10px; margin-bottom:6px; color:{self._tokens["text_faint"]};'
            f' font-size:8pt; letter-spacing:1.4px;">ASISTEN | </div>'
        )
        start = cursor.position()
        cursor.insertText("Thinking... 0.0s")
        self._thinking_cursor = QTextCursor(cursor)
        self._thinking_cursor.setPosition(start, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertBlock()
        self.setTextCursor(cursor)

        fmt = QTextCharFormat()
        fmt.setForeground(QColor(self._tokens["text"]))
        fmt.setBackground(QColor(self._tokens["assistant_surface"]))
        fmt.setFontPointSize(10.5)
        self._stream_format = fmt
        self._scroll_to_bottom()

    def set_thinking_time(self, seconds: float) -> None:
        if not self._streaming:
            return
        self._thinking_seconds = seconds
        self._thinking_timer.stop()
        self._update_thinking()

    def _update_thinking(self) -> None:
        if not self._streaming or self._thinking_cursor is None:
            return
        if self._thinking_seconds is None:
            text = f"Thinking... {max(0.0, monotonic() - self._thinking_started):.1f}s"
        else:
            text = f"Thought for {self._thinking_seconds:.1f}s"
        cursor = self._thinking_cursor
        start = cursor.selectionStart()
        cursor.insertText(text)
        cursor.setPosition(start, QTextCursor.MoveMode.KeepAnchor)

    def feed(self, delta: str) -> None:
        if not self._streaming or not delta:
            return
        self._pending += delta

    def end_stream(self, conversation: Conversation | None = None) -> None:
        if not self._streaming:
            if conversation is not None:
                self.show_conversation(conversation)
            return
        self._flush()
        self._flush_timer.stop()
        self._thinking_timer.stop()
        self._thinking_cursor = None
        self._streaming = False
        self._stream_text = ""
        if conversation is not None:
            self._conversation = conversation
        self._rebuild()

    def _flush(self) -> None:
        if not self._pending:
            return
        text = self._pending
        self._pending = ""
        self._stream_text += text
        at_bottom = self._at_bottom()
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text, self._stream_format)
        self.setTextCursor(cursor)
        if at_bottom:
            self._scroll_to_bottom()

    def _rebuild(self) -> None:
        if self._conversation is None or not self._conversation.messages:
            self.clear()
            return
        keep_bottom = self._at_bottom()
        blocks = "".join(
            self._message_block(message) for message in self._conversation.messages
        )
        self.setHtml(blocks)
        if keep_bottom:
            self._scroll_to_bottom()

    def _message_block(self, message: Message) -> str:
        tokens = self._tokens
        is_user = message.role == "user"
        surface = tokens["user_surface"] if is_user else tokens["assistant_surface"]
        accent = tokens["accent"] if is_user else tokens["border_strong"]
        label = _LABELS.get(message.role, message.role.upper())
        if message.role == "assistant" and message.thinking_seconds is not None:
            label += f" | Thought for {message.thinking_seconds:.1f}s"
        if is_user:
            body = (
                f'<p style="margin:0; color:{tokens["text"]}; line-height:150%;">'
                f"{html.escape(message.content, quote=False).replace(chr(10), '<br>')}</p>"
            )
        else:
            body = render_markdown(message.content, tokens)
        return (
            '<table width="100%" cellspacing="0" cellpadding="0" style="margin:0 0 14px 0;">'
            f'<tr><td style="background-color:{surface}; border-left:2px solid {accent};'
            f' padding:12px 16px;">'
            f'<div style="color:{tokens["text_faint"]}; font-size:8pt; letter-spacing:1.4px;'
            f' margin-bottom:6px;">{label}</div>'
            f"<div>{body}</div>"
            "</td></tr></table>"
        )

    def _at_bottom(self) -> bool:
        bar = self.verticalScrollBar()
        return bar.value() >= bar.maximum() - 40

    def _scroll_to_bottom(self) -> None:
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())
        self._scroll_timer.start(0)

    def _scroll_after_layout(self) -> None:
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())
