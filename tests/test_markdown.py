from __future__ import annotations

from app.ui.markdown import render_markdown

TOKENS = {
    "text": "#ffffff",
    "text_muted": "#888888",
    "accent": "#7c9cff",
    "code_bg": "#101010",
    "code_text": "#cccccc",
    "border": "#222222",
    "border_strong": "#333333",
}


def test_plain_paragraph() -> None:
    html = render_markdown("Halo dunia", TOKENS)
    assert "Halo dunia" in html
    assert "<p" in html


def test_escapes_html() -> None:
    html = render_markdown("<script>alert(1)</script>", TOKENS)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_bold_and_inline_code() -> None:
    html = render_markdown("**tebal** dan `kode`", TOKENS)
    assert "<b>tebal</b>" in html
    assert "kode" in html
    assert "Consolas" in html


def test_fenced_code_block() -> None:
    html = render_markdown("```python\nprint('hi')\n```", TOKENS)
    assert "<pre" in html
    assert "print" in html
    assert "hi" in html


def test_unordered_list() -> None:
    html = render_markdown("- satu\n- dua", TOKENS)
    assert "<ul" in html
    assert html.count("<li") == 2


def test_link() -> None:
    html = render_markdown("[situs](https://example.com)", TOKENS)
    assert 'href="https://example.com"' in html


def test_heading() -> None:
    html = render_markdown("## Judul", TOKENS)
    assert "<h4" in html
    assert "Judul" in html
