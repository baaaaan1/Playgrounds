from __future__ import annotations

import html
import re

_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?!\*)")
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_UNORDERED = re.compile(r"^\s*[-*+]\s+(.*)$")
_ORDERED = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_FENCE = re.compile(r"^\s*```(\w*)\s*$")
_RULE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")


def _inline(text: str, tokens: dict[str, str]) -> str:
    escaped = html.escape(text, quote=False)
    code_parts: list[str] = []

    def stash(match: re.Match[str]) -> str:
        code_parts.append(match.group(1))
        return f"\x00{len(code_parts) - 1}\x00"

    escaped = _INLINE_CODE.sub(stash, escaped)
    escaped = _LINK.sub(
        lambda m: (
            f'<a href="{m.group(2)}" style="color:{tokens["accent"]};'
            f' text-decoration:none;">{m.group(1)}</a>'
        ),
        escaped,
    )
    escaped = _BOLD.sub(r"<b>\1</b>", escaped)
    escaped = _ITALIC.sub(r"<i>\1</i>", escaped)

    def restore(match: re.Match[str]) -> str:
        code = code_parts[int(match.group(1))]
        return (
            f'<span style="font-family:Consolas,monospace;'
            f' background-color:{tokens["code_bg"]}; color:{tokens["code_text"]};">'
            f"&nbsp;{code}&nbsp;</span>"
        )

    return re.sub(r"\x00(\d+)\x00", restore, escaped)


def _paragraph(text: str, tokens: dict[str, str]) -> str:
    return (
        f'<p style="margin:0 0 10px 0; line-height:150%; color:{tokens["text"]};">'
        f"{_inline(text, tokens).replace(chr(10), '<br>')}</p>"
    )


def render_markdown(text: str, tokens: dict[str, str]) -> str:
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
        fence = _FENCE.match(line)
        if fence:
            flush_paragraph()
            flush_list()
            index += 1
            code_lines: list[str] = []
            while index < len(lines) and not _FENCE.match(lines[index]):
                code_lines.append(lines[index])
                index += 1
            index += 1
            code = html.escape("\n".join(code_lines))
            parts.append(
                f'<table width="100%" cellspacing="0" cellpadding="10" '
                f'style="margin:0 0 12px 0; background-color:{tokens["code_bg"]};">'
                f'<tr><td><pre style="margin:0; font-family:Consolas,monospace; '
                f'font-size:9pt; color:{tokens["code_text"]};">{code}</pre></td></tr></table>'
            )
            continue

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
