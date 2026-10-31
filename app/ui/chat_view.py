from __future__ import annotations

import html

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
        self._stream_format = QTextCharFormat()

        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setOpenExternalLinks(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().setDocumentMargin(56)
        self.setStyleSheet("background: transparent; border: none;")

        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(50)
        self._flush_timer.timeout.connect(self._flush)

    def set_tokens(self, tokens: dict[str, str]) -> None:
        self._tokens = dict(tokens)
        if self._conversation is not None:
            self._rebuild()

    def show_conversation(self, conversation: Conversation | None) -> None:
        self._conversation = conversation
        self._rebuild()

    def clear_chat(self) -> None:
        self._streaming = False
        self._pending = ""
        self._flush_timer.stop()
        self._conversation = None
        self.clear()

    def begin_stream(self) -> None:
        self._streaming = True
        self._pending = ""
        self._flush_timer.start()

        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(
            f'<div style="margin-top:10px; margin-bottom:6px; color:{self._tokens["text_faint"]};'
            f' font-size:8pt; letter-spacing:1.4px;">ASISTEN</div>'
        )
        self.setTextCursor(cursor)

        fmt = QTextCharFormat()
        fmt.setForeground(QColor(self._tokens["text"]))
        fmt.setBackground(QColor(self._tokens["assistant_surface"]))
        fmt.setFontPointSize(10.5)
        self._stream_format = fmt
        self._scroll_to_bottom()

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
        self._streaming = False
        if conversation is not None:
            self._conversation = conversation
        self._rebuild()

    def _flush(self) -> None:
        if not self._pending:
            return
        text = self._pending
        self._pending = ""
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
        QTimer.singleShot(0, lambda: bar.setValue(bar.maximum()))
