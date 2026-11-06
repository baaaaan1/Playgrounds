from __future__ import annotations

import html
import re
from collections.abc import Callable

_INLINE_PART = re.compile(r"`([^`\n]+)`|\[([^\]]+)\]\((https?://[^)\s]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?!\*)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_UNORDERED = re.compile(r"^\s*[-*+]\s+(.*)$")
_ORDERED = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})([^\r\n]*)$")
_RULE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")


def _inline(text: str, tokens: dict[str, str]) -> str:
    def prose(value: str) -> str:
        escaped = html.escape(value, quote=False)
        return _ITALIC.sub(r"<i>\1</i>", _BOLD.sub(r"<b>\1</b>", escaped))

    parts: list[str] = []
    start = 0
    for match in _INLINE_PART.finditer(text):
        parts.append(prose(text[start:match.start()]))
        if match.group(1) is not None:
            parts.append(
                f'<span style="font-family:Consolas,monospace;'
                f' background-color:{tokens["code_bg"]}; color:{tokens["code_text"]};">'
                f'&nbsp;{html.escape(match.group(1))}&nbsp;</span>'
            )
        else:
            parts.append(
                f'<a href="{html.escape(match.group(3), quote=True)}" '
                f'style="color:{tokens["accent_strong"]}; text-decoration:underline;">'
                f'{prose(match.group(2))}</a>'
            )
        start = match.end()
    parts.append(prose(text[start:]))
    return "".join(parts)


def parse_fenced_code(text: str) -> list[tuple[str | None, str]]:
    """Return (language, raw text) segments; None marks prose, not code.

    Keep the original code line endings, including the newline before a closing
    fence. An unclosed fence consumes the rest of the response.
    """
    segments: list[tuple[str | None, str]] = []
    lines = text.splitlines(keepends=True)
    index = 0
    prose_start = 0
    while index < len(lines):
        fence = _FENCE.match(lines[index].rstrip("\r\n"))
        if fence is None or (fence[1][0] == "`" and "`" in fence[2]):
            index += 1
            continue
        if index > prose_start:
            segments.append((None, "".join(lines[prose_start:index])))
        marker, language = fence[1], fence[2].strip()
        index += 1
        code_start = index
        closing = re.compile(r"^[ \t]*" + re.escape(marker[0]) + "{" + str(len(marker)) + r",}[ \t]*$")
        while index < len(lines) and not closing.match(lines[index].rstrip("\r\n")):
            index += 1
        segments.append((language, "".join(lines[code_start:index])))
        if index < len(lines):
            index += 1
        prose_start = index
    if prose_start < len(lines):
        segments.append((None, "".join(lines[prose_start:])))
    return segments


def extract_code_blocks(text: str) -> list[str]:
    return [raw for language, raw in parse_fenced_code(text) if language is not None]


def _paragraph(text: str, tokens: dict[str, str]) -> str:
    return (
        f'<p style="margin:0 0 10px 0; line-height:150%; color:{tokens["text"]};">'
        f"{_inline(text, tokens).replace(chr(10), '<br>')}</p>"
    )


def render_markdown(
    text: str,
    tokens: dict[str, str],
    code_action: Callable[[int, str], str] | None = None,
) -> str:
    parts: list[str] = []
    code_index = 0
    for language, raw in parse_fenced_code(text):
        if language is None:
            parts.append(_render_prose(raw, tokens))
            continue
        action = code_action(code_index, raw) if code_action is not None else ""
        code_index += 1
        code = html.escape(raw.replace("\r\n", "\n").replace("\r", "\n"))
        parts.append(
            f'<table width="100%" cellspacing="0" cellpadding="10" '
            f'style="margin:0 0 12px 0; background-color:{tokens["code_bg"]};">'
            f'<tr><td>{action}<pre style="margin:0; font-family:Consolas,monospace; '
            f'font-size:9pt; color:{tokens["code_text"]};">{code}</pre></td></tr></table>'
        )
    return "".join(parts) or (
        f'<p style="margin:0; color:{tokens["text_muted"]};">&nbsp;</p>'
    )


def _render_prose(text: str, tokens: dict[str, str]) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    parts: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    list_tag = ""

    def flush_paragraph() -> None:
        if paragraph:
            parts.append(_paragraph("\n".join(paragraph), tokens))
            paragraph.clear()

    def flush_list() -> None:
        nonlocal list_tag
        if list_items:
            items = "".join(f'<li style="margin:0 0 4px 0;">{item}</li>' for item in list_items)
            parts.append(
                f'<{list_tag} style="margin:0 0 10px 0; color:{tokens["text"]};">{items}</{list_tag}>'
            )
            list_items.clear()
        list_tag = ""

    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            flush_paragraph()
            flush_list()
            index += 1
            continue

        if _RULE.match(line):
            flush_paragraph()
            flush_list()
            parts.append(
                f'<hr style="border:none; border-top:1px solid {tokens["border"]}; margin:14px 0;">'
            )
            index += 1
            continue

        heading = _HEADING.match(line)
        if heading:
            flush_paragraph()
            flush_list()
            level = min(len(heading.group(1)) + 2, 5)
            content = _inline(heading.group(2), tokens)
            size = {3: "15px", 4: "13px", 5: "12px"}.get(level, "12px")
            parts.append(
                f'<h{level} style="margin:14px 0 8px 0; font-size:{size}; '
                f'font-weight:600; color:{tokens["text"]};">{content}</h{level}>'
            )
            index += 1
            continue

        ordered = _ORDERED.match(line)
        unordered = _UNORDERED.match(line)
        if ordered or unordered:
            flush_paragraph()
            tag = "ol" if ordered else "ul"
            if list_tag and list_tag != tag:
                flush_list()
            list_tag = tag
            item = (ordered or unordered).group(1)
            list_items.append(_inline(item, tokens))
            index += 1
            continue

        if line.lstrip().startswith(">"):
            flush_paragraph()
            flush_list()
            quote_lines: list[str] = []
            while index < len(lines) and lines[index].lstrip().startswith(">"):
                quote_lines.append(lines[index].lstrip()[1:].lstrip())
                index += 1
            parts.append(
                f'<table width="100%" cellspacing="0" cellpadding="8" '
                f'style="margin:0 0 12px 0; border-left:2px solid {tokens["border_strong"]};">'
                f'<tr><td>{_paragraph(chr(10).join(quote_lines), tokens)}</td></tr></table>'
            )
            continue

        flush_list()
        paragraph.append(line)
        index += 1

    flush_paragraph()
    flush_list()
    return "".join(parts) or (
        f'<p style="margin:0; color:{tokens["text_muted"]};">&nbsp;</p>'
    )
