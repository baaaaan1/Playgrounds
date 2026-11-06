from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QLabel, QPushButton

from app.ui import theme
from app.ui.empty_state import EmptyState


@pytest.mark.parametrize("width", [320, 460, 900, 1700])
@pytest.mark.parametrize("height", [240, 620])
def test_empty_state_theme_and_suggestion_layout(qt_app, width, height) -> None:
    old_palette, old_qss = qt_app.palette(), qt_app.styleSheet()
    panel = EmptyState(theme.tokens_for("dark"))
    panel.resize(width, height)
    panel.show()
    try:
        for name in ("dark", "light", "dark"):
            tokens = theme.apply(qt_app, name)
            panel.set_tokens(tokens)
            qt_app.processEvents()
            image = panel.viewport().grab().toImage()
            assert image.pixelColor(4, 4).name() == tokens["bg"]
            assert panel.horizontalScrollBar().maximum() == 0
            for object_name, token in (("EmptyTitle", "text"), ("EmptySubtitle", "text_muted")):
                label = panel.findChild(QLabel, object_name)
                assert label.palette().color(QPalette.ColorRole.WindowText).name() == tokens[token]
            buttons = panel.findChildren(QPushButton, "Suggestion")
            assert len(buttons) == 3
            for button in buttons:
                assert button.width() == min(460, panel.viewport().width() - 48)
                label = button.findChild(QLabel)
                assert label.text() == button.accessibleName()
                assert label.width() >= button.width() - 32
                assert label.height() >= label.heightForWidth(label.width())
                assert button.rect().contains(label.geometry())
            panel.ensureWidgetVisible(buttons[-1])
            qt_app.processEvents()
            bottom = buttons[-1].mapTo(panel.viewport(), buttons[-1].rect().bottomLeft())
            assert bottom.y() < panel.viewport().height()
    finally:
        panel.close()
        qt_app.setPalette(old_palette)
        qt_app.setStyleSheet(old_qss)


def test_suggestion_emits_full_prompt_with_mouse_and_keyboard(qt_app) -> None:
    panel = EmptyState(theme.tokens_for("dark"))
    panel.resize(600, 620)
    chosen = []
    panel.suggestion_chosen.connect(chosen.append)
    panel.show()
    qt_app.processEvents()
    try:
        buttons = panel.findChildren(QPushButton, "Suggestion")
        label = buttons[0].findChild(QLabel)
        QTest.mouseClick(buttons[0], Qt.MouseButton.LeftButton, pos=label.geometry().center())
        buttons[1].setFocus()
        QTest.keyClick(buttons[1], Qt.Key.Key_Space)
        assert chosen == [button.accessibleName() for button in buttons[:2]]
    finally:
        panel.close()
