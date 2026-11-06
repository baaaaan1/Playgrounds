from __future__ import annotations

import html
from time import monotonic
from uuid import uuid4

from PyQt6.QtCore import QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QDesktopServices,
    QImage,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QTextBrowser,
    QTextEdit,
    QToolButton,
    QToolTip,
    QWidget,
)

from ..core.models import Conversation, Message, ResponseStatistics
from . import icons
from .markdown import render_markdown
from .message_editor import MessageEditor


class ChatView(QTextBrowser):
    """QTextBrowser that renders a conversation and streams new tokens."""

    edit_requested = pyqtSignal(str)
    edit_submitted = pyqtSignal(str, str, str)
    regenerate_requested = pyqtSignal(str)
    retry_requested = pyqtSignal(str)
    error = pyqtSignal(str)
    find_changed = pyqtSignal(int, int)

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
        self._busy = False
        self._actions: dict[str, tuple[str, str]] = {}
        self._action_buttons: list[tuple[QToolButton, QTextCursor]] = []
        self._icon_actions: dict[str, tuple[str, str]] = {}
        self._message_anchors: dict[str, str] = {}
        self._message_ranges: dict[str, tuple[int, int]] = {}
        self._find_query = ""
        self._find_matches: list[QTextCursor] = []
        self._find_index = -1
        self._editor: MessageEditor | None = None
        self._edit_message_id = ""
        self._edit_cursor: QTextCursor | None = None
        self._positioning_editor = False

        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setOpenExternalLinks(False)
        self.setOpenLinks(False)
        self.anchorClicked.connect(self._activate_link)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().setDocumentMargin(56)
        self.setStyleSheet("QTextBrowser { background: transparent; border: none; }")
        self.verticalScrollBar().valueChanged.connect(self._position_action_buttons)
        self.horizontalScrollBar().valueChanged.connect(self._position_action_buttons)
        self.document().documentLayout().documentSizeChanged.connect(self._position_action_buttons)

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
        if self._editor is not None and (
            conversation is None or self._conversation is None
            or conversation.id != self._conversation.id
            or not any(m.id == self._edit_message_id and m.role == "user"
                       for m in conversation.messages)
        ):
            self._clear_editor()
        self._conversation = conversation
        self._rebuild()

    @property
    def editing(self) -> bool:
        return self._editor is not None

    @property
    def has_unsaved_edit(self) -> bool:
        return self._editor is not None and self._editor.dirty

    def begin_edit(self, message_id: str) -> None:
        if self._busy or self._streaming or self._conversation is None:
            return
        if self._editor is not None:
            self._editor.setFocus()
            return
        message = next((m for m in self._conversation.messages
                        if m.id == message_id and m.role == "user"), None)
        if message is None:
            return
        self._edit_message_id = message_id
        self._editor = MessageEditor(message.content, self.viewport())
        self._editor.submitted.connect(self._submit_edit)
        self._editor.canceled.connect(self.cancel_edit)
        self._rebuild()
        self.find_message(message_id)
        self._position_inline_editor()
        self._editor.setFocus()

    def _submit_edit(self, text: str) -> None:
        if self._editor is not None and not self._busy and not self._streaming:
            self.edit_submitted.emit(self._conversation.id, self._edit_message_id, text)

    def _clear_editor(self) -> None:
        if self._editor is not None:
            self._editor.hide()
            self._editor.deleteLater()
            self._editor = None
        self._edit_message_id = ""
        self._edit_cursor = None

    def cancel_edit(self) -> None:
        if self._editor is None:
            return
        message_id = self._edit_message_id
        self._clear_editor()
        self._rebuild()
        self.find_message(message_id)
        self.setFocus()

    def set_busy(self, busy: bool) -> None:
        if self._busy == busy:
            return
        self._busy = busy
        if busy:
            self._clear_editor()
        if not self._streaming:
            self._rebuild()

    def clear_chat(self) -> None:
        self._clear_editor()
        self._streaming = False
        self._pending = ""
        self._stream_text = ""
        self._flush_timer.stop()
        self._thinking_timer.stop()
        self._scroll_timer.stop()
        self._thinking_cursor = None
        self._conversation = None
        self._actions.clear()
        self._clear_action_buttons()
        self._message_anchors.clear()
        self._message_ranges.clear()
        self.clear()
        self._refresh_find()

    def begin_stream(self) -> None:
        if self.editing:
            self._clear_editor()
            self._rebuild()
        self._streaming = True
        for button, _cursor in self._action_buttons:
            button.setEnabled(button.property("actionKind") == "copy")
        self._pending = ""
        self._stream_text = ""
        self._thinking_started = monotonic()
        self._thinking_seconds = None
        self._flush_timer.start()
        self._thinking_timer.start()

        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(
            f'<div style="margin-top:10px; margin-bottom:6px; color:{self._tokens["text_faint"]};'
            f' font-size:8pt; letter-spacing:1.4px;">{html.escape(self.tr("ASSISTANT"))} | </div>'
        )
        start = cursor.position()
        cursor.insertText(self.tr("Thinking... {seconds:.1f}s").format(seconds=0.0))
        self._thinking_cursor = QTextCursor(cursor)
        self._thinking_cursor.setPosition(start, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertBlock()

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
            text = self.tr("Thinking... {seconds:.1f}s").format(
                seconds=max(0.0, monotonic() - self._thinking_started)
            )
        else:
            text = self.tr("Thought for {seconds:.1f}s").format(seconds=self._thinking_seconds)
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
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text, self._stream_format)
        if self._find_query:
            self._refresh_find()
        if at_bottom:
            self._scroll_to_bottom()

    def _rebuild(self) -> None:
        self._scroll_timer.stop()
        self._edit_cursor = None
        self._clear_action_buttons()
        find_position = (self._find_matches[self._find_index].selectionStart()
                         if 0 <= self._find_index < len(self._find_matches) else None)
        self._actions.clear()
        self._message_anchors.clear()
        self._message_ranges.clear()
        if self._conversation is None or not self._conversation.messages:
            self.clear()
            self._refresh_find()
            return
        keep_bottom = self._at_bottom()
        position = self.verticalScrollBar().value()
        blocks = "".join(
            self._message_block(message) for message in self._conversation.messages
        )
        # clear() drops document resources, so restore transparent inline spacers on each rebuild.
        placeholder = QImage(24, 24, QImage.Format.Format_ARGB32)
        placeholder.fill(Qt.GlobalColor.transparent)
        for name in ("chat-action-placeholder", "chat-editor-placeholder"):
            self.document().addResource(
                QTextDocument.ResourceType.ImageResource, QUrl(name), placeholder,
            )
        self.setHtml(blocks)
        self._collect_message_ranges()
        self._create_action_buttons()
        self._position_inline_editor()
        self._refresh_find(find_position)
        if keep_bottom and not self.editing:
            self._scroll_to_bottom()
        if not keep_bottom or self._find_query:
            self.verticalScrollBar().setValue(position)

    def _message_block(self, message: Message) -> str:
        tokens = self._tokens
        is_user = message.role == "user"
        surface = tokens["user_surface"] if is_user else tokens["assistant_surface"]
        accent = tokens["accent_strong"] if is_user else tokens["border_strong"]
        label = {"user": self.tr("YOU"), "assistant": self.tr("ASSISTANT")}.get(
            message.role, message.role.upper()
        )
        if message.role == "assistant" and message.thinking_seconds is not None:
            label = self.tr("ASSISTANT | Thought for {seconds:.1f}s").format(
                seconds=message.thinking_seconds
            )
        if message.role == "assistant" and message.status in {"failed", "stopped"}:
            status_label = self.tr("Failed") if message.status == "failed" else self.tr("Stopped")
            label = self.tr("{label} | {status}").format(label=label, status=status_label)
        label = html.escape(label)
        anchor = "message-" + uuid4().hex
        self._message_anchors[message.id] = anchor
        actions: list[str] = []
        if is_user:
            if message.id == self._edit_message_id:
                body = '<img src="chat-editor-placeholder" width="1" height="300">'
            else:
                actions.append(self._action_link("edit", message.id, self.tr("Edit"), icon_button=True))
                body = (
                    f'<p style="margin:0; color:{tokens["text"]}; line-height:150%;">'
                    f"{html.escape(message.content, quote=False).replace(chr(10), '<br>')}</p>"
                )
        else:
            actions.append(self._action_link(
                "copy", message.content, self.tr("Copy response"), icon_button=True,
            ))
            body = render_markdown(
                message.content, tokens,
                lambda index, code: self._action_link("copy", code, self.tr("Copy code")),
            )
        messages = self._conversation.messages
        if message is messages[-1]:
            user = next((item for item in reversed(messages) if item.role == "user"), None)
            attempt = self._conversation.last_attempt
            retry_statuses = {"failed", "stopped", "interrupted"}
            if message.role == "assistant":
                if message.status == "complete":
                    actions.append(self._action_link(
                        "regenerate", message.id, self.tr("Regenerate"), icon_button=True,
                    ))
                failed_replacement = (
                    user is not None and attempt.get("user_message_id") == user.id
                    and attempt.get("replaces_message_id") == message.id
                    and attempt.get("status") in retry_statuses
                )
                if user is not None and (message.status in retry_statuses or failed_replacement):
                    actions.append(self._action_link("retry", user.id, self.tr("Retry"), icon_button=True))
            elif is_user:
                if (attempt.get("user_message_id") == message.id
                        and attempt.get("status") in retry_statuses):
                    actions.append(self._action_link("retry", message.id, self.tr("Retry"), icon_button=True))
        return (
            '<table width="100%" cellspacing="0" cellpadding="0" style="margin:0 0 14px 0;">'
            f'<tr><td style="background-color:{surface}; border-left:2px solid {accent};'
            f' padding:12px 16px;">'
            f'<div style="color:{tokens["text_faint"]}; font-size:8pt; letter-spacing:1.4px;'
            f' margin-bottom:6px;"><a name="{anchor}">{label}</a></div>'
            f"<div>{body}</div>"
            f'<p style="margin:6px 0 0 0; font-size:8pt;">{" &nbsp; ".join(actions)}</p>'
            f'{self._statistics_block(message) if message.role == "assistant" else ""}'
            "</td></tr></table>"
        )

    def _statistics_block(self, message: Message) -> str:
        stats = message.statistics or ResponseStatistics()
        unavailable = self.tr("N/A")
        ttft = message.thinking_seconds
        speed = stats.tokens_per_second(ttft)
        cost = stats.estimated_cost
        metrics = [
            self.tr("TTFT: {value}").format(value=f"{ttft:.2f}s" if ttft is not None else unavailable),
            self.tr("Total: {value}").format(
                value=f"{stats.duration_seconds:.2f}s" if stats.duration_seconds is not None else unavailable,
            ),
            self.tr("Input: {value}").format(
                value=f"{stats.input_tokens:,}" if stats.input_tokens is not None else unavailable,
            ),
            self.tr("Output: {value}").format(
                value=f"{stats.output_tokens:,}" if stats.output_tokens is not None else unavailable,
            ),
            self.tr("Speed: {value}").format(value=f"{speed:.1f} tok/s" if speed is not None else unavailable),
            self.tr("Est. cost: {value}").format(value=f"USD {cost:.6f}" if cost is not None else unavailable),
        ]
        return (
            f'<p style="margin:8px 0 0 0; font-size:8pt; color:{self._tokens["text_muted"]};">'
            + " &nbsp;|&nbsp; ".join(html.escape(metric) for metric in metrics) + "</p>"
        )

    def _action_link(
        self, action: str, payload: str, label: str, *, icon_button: bool = False,
    ) -> str:
        escaped_label = html.escape(label)
        blocked = action != "copy" and (self._busy or self._streaming or self.editing)
        if blocked and not icon_button:
            return f'<span style="color:{self._tokens["text_faint"]};">{escaped_label}</span>'
        # Only application-generated opaque links can dispatch transcript actions.
        url = "chat-action:" + uuid4().hex
        if not blocked:
            self._actions[url] = action, payload
        if icon_button:
            self._icon_actions[url] = action, label
            return (
                f'<a href="{url}" title="{escaped_label}">'
                '<img src="chat-action-placeholder" width="24" height="24"></a>'
            )
        return f'<a href="{url}" style="color:{self._tokens["accent_strong"]};">{escaped_label}</a>'

    def _clear_action_buttons(self) -> None:
        for button, _cursor in self._action_buttons:
            button.hide()
            button.setParent(None)
            button.deleteLater()
        self._action_buttons.clear()
        self._icon_actions.clear()

    def _create_action_buttons(self) -> None:
        cursor = QTextCursor(self.document())
        while True:
            cursor = self.document().find("\ufffc", cursor)
            if cursor.isNull():
                break
            fmt = cursor.charFormat()
            if fmt.isImageFormat() and fmt.toImageFormat().name() == "chat-editor-placeholder":
                self._edit_cursor = QTextCursor(cursor)
                continue
            url = fmt.anchorHref()
            if (not fmt.isImageFormat() or fmt.toImageFormat().name() != "chat-action-placeholder"
                    or url not in self._icon_actions):
                continue
            kind, label = self._icon_actions[url]
            name, icon = {
                "copy": ("CopyResponse", "copy"),
                "edit": ("EditMessage", "edit"),
                "regenerate": ("RegenerateResponse", "regenerate"),
                "retry": ("RetryResponse", "regenerate"),
            }[kind]
            button = QToolButton(self.viewport())
            button.setObjectName(name)
            button.setProperty("chatAction", True)
            button.setProperty("actionKind", kind)
            button.setIcon(icons.icon(icon, self._tokens["text_muted"], 16))
            button.setIconSize(QSize(16, 16))
            button.setFixedSize(24, 24)
            button.setToolTip(label)
            button.setAccessibleName(label)
            button.setEnabled(url in self._actions)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            button.clicked.connect(lambda _checked=False, link=url: self._activate_link(QUrl(link)))
            position = QTextCursor(cursor)
            position.setPosition(cursor.selectionStart())
            self._action_buttons.append((button, position))
        self._position_action_buttons()

    def _position_action_buttons(self) -> None:
        self._position_inline_editor()
        for button, cursor in self._action_buttons:
            button.move(self.cursorRect(cursor).topLeft())
            button.setVisible(self.viewport().rect().intersects(button.geometry()))

    def _position_inline_editor(self) -> None:
        if self._editor is None or self._edit_cursor is None or self._positioning_editor:
            return
        self._positioning_editor = True
        try:
            cursor = QTextCursor(self._edit_cursor)
            cursor.setPosition(cursor.selectionStart())
            point = self.cursorRect(cursor).topLeft()
            width = max(1, self.viewport().width() - point.x()
                        - int(self.document().documentMargin()) - 18)
            layout = self._editor.layout()
            height = max(layout.minimumSize().height(), layout.totalHeightForWidth(width))
            self._editor.setGeometry(point.x(), point.y(), width, height)
            # Reserve the panel's actual height in the transcript, including wrapped help text.
            fmt = self._edit_cursor.charFormat().toImageFormat()
            if fmt.height() != height:
                fmt.setHeight(height)
                self._edit_cursor.setCharFormat(fmt)
                self._editor.move(self.cursorRect(cursor).topLeft())
            self._editor.show()
        finally:
            self._positioning_editor = False

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._position_action_buttons()

    def focusNextPrevChild(self, next: bool) -> bool:  # noqa: N802
        if self._editor is not None and self._editor.isAncestorOf(QApplication.focusWidget()):
            # QTextBrowser normally traverses document links instead of child controls.
            return QWidget.focusNextPrevChild(self, next)
        return super().focusNextPrevChild(next)

    def _activate_link(self, url: QUrl) -> None:
        action = self._actions.get(url.toString())
        if action is not None:
            kind, payload = action
            if kind == "copy":
                try:
                    QApplication.clipboard().setText(payload)
                    QToolTip.showText(QCursor.pos(), self.tr("Copied"), self, self.rect(), 1500)
                except Exception as exc:
                    self.error.emit(self.tr("Could not copy to the clipboard: {detail}").format(
                        detail=str(exc),
                    ))
            elif not self._busy and not self._streaming and not self.editing:
                {"edit": self.edit_requested, "regenerate": self.regenerate_requested,
                 "retry": self.retry_requested}[kind].emit(payload)
            return
        if url.isValid() and url.scheme().lower() in {"http", "https"} and url.host():
            if not QDesktopServices.openUrl(url):
                self.error.emit(self.tr("Could not open the link in your browser."))

    def _collect_message_ranges(self) -> None:
        anchor_ids = {anchor: message_id for message_id, anchor in self._message_anchors.items()}
        starts: list[tuple[str, int]] = []
        block = self.document().begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                for anchor in fragment.charFormat().anchorNames():
                    if anchor in anchor_ids:
                        starts.append((anchor_ids[anchor], fragment.position()))
                iterator += 1
            block = block.next()
        for index, (message_id, start) in enumerate(starts):
            end = starts[index + 1][1] if index + 1 < len(starts) else self.document().characterCount() - 1
            self._message_ranges[message_id] = start, end

    def set_find_query(self, query: str) -> None:
        self._find_query = query
        self._find_index = -1
        self._refresh_find()
        if self._find_matches:
            self._show_find_hit()

    def clear_find(self) -> None:
        self._find_query = ""
        self._refresh_find()

    def find_next(self) -> None:
        self._move_find(1)

    def find_previous(self) -> None:
        self._move_find(-1)

    def _move_find(self, direction: int) -> None:
        if self._find_matches:
            self._find_index = (self._find_index + direction) % len(self._find_matches)
            self._paint_find()
            self._show_find_hit()

    def _refresh_find(self, previous: int | None = None) -> None:
        if previous is None and 0 <= self._find_index < len(self._find_matches):
            previous = self._find_matches[self._find_index].selectionStart()
        self._find_matches = []
        if self._find_query:
            cursor = QTextCursor(self.document())
            while True:
                cursor = self.document().find(self._find_query, cursor)
                if cursor.isNull():
                    break
                self._find_matches.append(cursor)
        self._find_index = 0 if self._find_matches else -1
        if previous is not None and self._find_matches:
            self._find_index = min(
                range(len(self._find_matches)),
                key=lambda index: abs(self._find_matches[index].selectionStart() - previous),
            )
        self._paint_find()

    def _paint_find(self) -> None:
        selections = []
        for index, cursor in enumerate(self._find_matches):
            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor
            color = QColor(self._tokens["accent_strong"])
            color.setAlpha(150 if index == self._find_index else 65)
            selection.format.setBackground(color)
            selections.append(selection)
        self.setExtraSelections(selections)
        self.find_changed.emit(self._find_index + 1, len(self._find_matches))

    def _show_find_hit(self) -> None:
        self._scroll_timer.stop()
        rect = self.cursorRect(self._find_matches[self._find_index])
        if rect.top() < 0 or rect.bottom() > self.viewport().height():
            bar = self.verticalScrollBar()
            bar.setValue(bar.value() + rect.top() - self.viewport().height() // 3)

    def find_message(self, message_id: str, query: str = "") -> bool:
        bounds = self._message_ranges.get(message_id)
        if bounds is None:
            return False
        self._scroll_timer.stop()
        self.scrollToAnchor(self._message_anchors[message_id])
        if query:
            self._find_query = query
            self._refresh_find()
            for index, cursor in enumerate(self._find_matches):
                if bounds[0] <= cursor.selectionStart() < bounds[1]:
                    self._find_index = index
                    self._paint_find()
                    self._show_find_hit()
                    break
        return True

    def _at_bottom(self) -> bool:
        bar = self.verticalScrollBar()
        return bar.value() >= bar.maximum() - 40

    def _scroll_to_bottom(self) -> None:
        if self._find_query:
            return
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())
        self._scroll_timer.start(0)

    def _scroll_after_layout(self) -> None:
        if self._find_query:
            return
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())
