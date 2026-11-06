from pathlib import Path

import pytest
from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from app.ui import icons, theme
from app.ui.empty_state import EmptyState


@pytest.mark.parametrize("size", [16, 24, 64, 256])
@pytest.mark.parametrize("scale", [1.0, 1.5, 2.0, 3.0])
def test_app_icon_matches_supplied_svg_at_multiple_scales(qt_app, size, scale) -> None:
    source = Path(__file__).resolve().parents[1] / "build" / "icon.svg"
    renderer = QSvgRenderer(source.read_bytes())
    assert renderer.isValid()
    expected = QPixmap(round(size * scale), round(size * scale))
    expected.fill(Qt.GlobalColor.transparent)
    painter = QPainter(expected)
    renderer.render(painter, QRectF(expected.rect()))
    painter.end()

    actual = icons.app_icon().pixmap(QSize(size, size), scale)
    assert actual.size() == expected.size()
    assert actual.devicePixelRatioF() == scale
    assert actual.toImage() == expected.toImage()


def test_empty_state_uses_full_color_brand_at_balanced_size(qt_app) -> None:
    state = EmptyState(theme.tokens_for("dark"))
    assert state._mark.size() == QSize(64, 64)
    before = state._mark.grab().toImage()
    assert before.pixelColor(32, 32).name() == "#ff896a"
    assert before.pixelColor(32, 4).name() == "#17191e"
    state.set_tokens(theme.tokens_for("light"))
    assert state._mark.grab().toImage() == before
    state.close()


@pytest.mark.parametrize("name,asset", [
    ("edit", "edit-outline"),
    ("regenerate", "refresh"),
    ("copy", "content-copy-outline"),
])
@pytest.mark.parametrize("theme_name", ["dark", "light"])
@pytest.mark.parametrize("scale", [1, 2, 3])
def test_chat_icons_use_material_symbols_at_16px(qt_app, name, asset, theme_name, scale) -> None:
    source = Path(__file__).resolve().parents[1] / f"app/resources/material-symbols/{asset}.svg"
    svg = source.read_bytes()
    assert icons._svg(name) == svg
    color = theme.tokens_for(theme_name)["text_muted"]
    renderer = QSvgRenderer(svg.replace(b"currentColor", color.encode("ascii")))
    assert renderer.isValid()
    assert renderer.viewBoxF() == QRectF(0, 0, 24, 24)
    expected = QPixmap(16 * scale, 16 * scale)
    expected.fill(Qt.GlobalColor.transparent)
    painter = QPainter(expected)
    renderer.render(painter, QRectF(expected.rect()))
    painter.end()
    actual = icons.icon(name, color, 16).pixmap(QSize(16, 16), scale)
    assert actual.size() == expected.size()
    assert actual.devicePixelRatioF() == scale
    image = actual.toImage()
    assert image == expected.toImage()
    assert any(image.pixelColor(x, y).alpha()
               for x in range(image.width()) for y in range(image.height()))


def test_material_symbols_apache_license_is_bundled() -> None:
    source = Path(__file__).resolve().parents[1] / "app/resources/material-symbols/LICENSE.txt"
    text = source.read_text(encoding="utf-8")
    assert "Material Symbols by Google" in text
    assert "Apache License" in text
    assert "Version 2.0, January 2004" in text
    assert "4. Redistribution." in text
    assert "9. Accepting Warranty or Additional Liability." in text
    assert "END OF TERMS AND CONDITIONS" in text
