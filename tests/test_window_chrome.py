from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, QSize, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout, QWidget

from app.ui import icons, theme
from app.ui.window_chrome import FramelessWindowMixin, TitleBar


class ChromeWindow(FramelessWindowMixin, QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Chrome test")
        self.setMinimumSize(240, 160)
        self.resize(480, 320)
        self.setup_frameless_window()
        self.bar = TitleBar(self, theme.tokens_for("dark"))
        QVBoxLayout(self).addWidget(self.bar)


def test_window_controls_maximize_restore_minimize_close(qt_app) -> None:
    window = ChromeWindow()
    window.show()
    qt_app.processEvents()
    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
    window.bar.maximize_button.click()
    qt_app.processEvents()
    assert window.isMaximized()
    assert window.bar.maximize_button.toolTip() == "Restore"
    window.bar.maximize_button.click()
    qt_app.processEvents()
    assert not window.isMaximized()
    assert window.bar.maximize_button.toolTip() == "Maximize"
    window.bar.minimize_button.click()
    qt_app.processEvents()
    assert window.isMinimized()
    window.showNormal()
    window.bar.close_button.click()
    assert not window.isVisible()


def test_dialog_close_button_rejects_without_saving(qt_app) -> None:
    class Dialog(FramelessWindowMixin, QDialog):
        pass

    dialog = Dialog()
    dialog.setup_frameless_window()
    bar = TitleBar(dialog, theme.tokens_for("light"), show_minimize=False, show_maximize=False)
    QVBoxLayout(dialog).addWidget(bar)
    dialog.show()
    qt_app.processEvents()
    assert bar.minimize_button.isHidden()
    assert bar.maximize_button.isHidden()
    QTest.mouseDClick(bar, Qt.MouseButton.LeftButton)
    assert not dialog.isMaximized()
    bar.close_button.click()
    assert dialog.result() == QDialog.DialogCode.Rejected


def test_material_line_icons_render_offline_at_multiple_scales(qt_app) -> None:
    for name in icons._NAMES:
        for scale in (1.0, 2.0):
            pixmap = icons.icon(name, "#7c9cff", 24).pixmap(QSize(24, 24), scale)
            image = pixmap.toImage()
            assert not image.isNull(), name
            visible = sum(image.pixelColor(x, y).alpha() > 0 for x in range(image.width()) for y in range(image.height()))
            assert visible > 10, (name, scale)
        assert b"animate" not in icons._svg(name), name


def test_title_and_theme_refresh(qt_app) -> None:
    window = ChromeWindow()
    window.show()
    qt_app.processEvents()
    window.setWindowTitle("Updated title")
    assert window.bar._title.text() == "Updated title"
    window.bar.refresh_theme(theme.tokens_for("light"))
    assert not window.bar.close_button.icon().isNull()
    window.close()


def test_long_title_is_plain_text_and_elided_without_displacing_controls(qt_app) -> None:
    window = ChromeWindow()
    title = "<b>Window title</b> " * 40
    window.setWindowTitle(title)
    window.show()
    qt_app.processEvents()
    label = window.bar._title
    assert label.textFormat() == Qt.TextFormat.PlainText
    assert label.text() != title
    assert label.toolTip() == title
    assert label.accessibleName() == title
    assert window.width() == 480
    assert window.bar.rect().contains(window.bar.close_button.mapTo(window.bar, QPoint(23, 21)))
    window.setWindowTitle("Short title")
    assert label.text() == "Short title"
    assert not label.toolTip()
    window.close()


def test_title_bar_tracks_window_icon_and_activation(qt_app) -> None:
    window = ChromeWindow()
    icon = icons.icon("plus", "#ff0000", 22)
    window.setWindowIcon(icon)
    expected = icon.pixmap(QSize(22, 22), window.bar.devicePixelRatioF())
    assert window.bar._brand.pixmap().toImage() == expected.toImage()
    for event_type, active in (
        (QEvent.Type.WindowActivate, True), (QEvent.Type.WindowDeactivate, False),
    ):
        QApplication.sendEvent(window, QEvent(event_type))
        assert window.bar.property("active") is active
        assert window.bar._title.property("active") is active
    window.close()


def _drag_to(bar: TitleBar, position: QPoint) -> None:
    event = QMouseEvent(
        QEvent.Type.MouseMove, QPointF(position), QPointF(bar.mapToGlobal(position)),
        Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(bar, event)


@pytest.mark.parametrize("action", ["button", "double_click", "drag"])
def test_maximized_fullscreen_state_can_restore(qt_app, monkeypatch, action) -> None:
    window = ChromeWindow()
    window.show()
    qt_app.processEvents()
    normal_geometry = window.geometry()
    # Windows can report both flags when a frameless window fills the monitor.
    window.setWindowState(Qt.WindowState.WindowMaximized | Qt.WindowState.WindowFullScreen)
    qt_app.processEvents()
    assert window.isMaximized() and window.isFullScreen()
    assert window.bar.maximize_button.isEnabled()
    assert window.bar.maximize_button.toolTip() == "Restore"

    position = QPoint(80, 20)
    if action == "button":
        QTest.mouseClick(window.bar.maximize_button, Qt.MouseButton.LeftButton)
    elif action == "double_click":
        QTest.mouseDClick(window.bar, Qt.MouseButton.LeftButton, pos=position)
    else:
        monkeypatch.setattr(window.windowHandle(), "startSystemMove", lambda: False)
        QTest.mousePress(window.bar, Qt.MouseButton.LeftButton, pos=position)
        _drag_to(window.bar, position + QPoint(QApplication.startDragDistance() + 20, 12))
        QTest.mouseRelease(window.bar, Qt.MouseButton.LeftButton)

    qt_app.processEvents()
    assert not window.isMaximized()
    assert not window.isFullScreen()
    assert window.size() == normal_geometry.size()
    if action != "drag":
        assert window.geometry() == normal_geometry
    assert window.bar.maximize_button.toolTip() == "Maximize"
    assert all(not handle.isHidden() for handle in window._frameless_resize_frame.handles)
    window.close()


def test_drag_waits_for_threshold_before_starting_native_move(qt_app, monkeypatch) -> None:
    window = ChromeWindow()
    window.show()
    qt_app.processEvents()
    calls = []

    def start_move():
        calls.append(True)
        return True

    monkeypatch.setattr(window.windowHandle(), "startSystemMove", start_move)
    position = QPoint(80, 20)
    QTest.mousePress(window.bar, Qt.MouseButton.LeftButton, pos=position)
    _drag_to(window.bar, position + QPoint(1, 0))
    assert not calls
    _drag_to(window.bar, position + QPoint(QApplication.startDragDistance() + 1, 0))
    assert calls == [True]
    assert window.bar._drag_offset is None
    QTest.mouseRelease(window.bar, Qt.MouseButton.LeftButton)
    window.close()


def test_fallback_drag_and_double_click_restore(qt_app, monkeypatch) -> None:
    window = ChromeWindow()
    window.show()
    qt_app.processEvents()
    monkeypatch.setattr(window.windowHandle(), "startSystemMove", lambda: False)
    position = QPoint(80, 20)
    original = window.pos()
    delta = QPoint(QApplication.startDragDistance() + 20, 12)
    QTest.mousePress(window.bar, Qt.MouseButton.LeftButton, pos=position)
    _drag_to(window.bar, position + delta)
    assert window.pos() == original + delta
    QTest.mouseRelease(window.bar, Qt.MouseButton.LeftButton)
    assert window.bar._drag_offset is None
    QTest.mouseDClick(window.bar, Qt.MouseButton.LeftButton, pos=position)
    qt_app.processEvents()
    assert window.isMaximized()
    QTest.mousePress(window.bar, Qt.MouseButton.LeftButton, pos=position)
    _drag_to(window.bar, position + delta)
    assert not window.isMaximized()
    QTest.mouseRelease(window.bar, Qt.MouseButton.LeftButton)
    QTest.mouseDClick(window.bar, Qt.MouseButton.LeftButton, pos=position)
    assert window.isMaximized()
    QTest.mouseDClick(window.bar, Qt.MouseButton.LeftButton, pos=position)
    assert not window.isMaximized()
    window.close()


def test_fullscreen_disables_drag_maximize_and_resize(qt_app) -> None:
    window = ChromeWindow()
    window.showFullScreen()
    qt_app.processEvents()
    assert not window.bar.maximize_button.isEnabled()
    assert all(handle.isHidden() for handle in window._frameless_resize_frame.handles)
    QTest.mousePress(window.bar, Qt.MouseButton.LeftButton, pos=QPoint(80, 20))
    assert window.bar._drag_offset is None
    QTest.mouseRelease(window.bar, Qt.MouseButton.LeftButton)
    window.bar.toggle_maximized()
    assert window.isFullScreen()
    window.showNormal()
    qt_app.processEvents()
    assert window.bar.maximize_button.isEnabled()
    window.close()


def test_fixed_size_window_disables_maximize_and_resize(qt_app) -> None:
    window = ChromeWindow()
    frame = window._frameless_resize_frame
    window.setup_frameless_window()
    assert window._frameless_resize_frame is frame
    window.setFixedSize(window.size())
    window.show()
    qt_app.processEvents()
    assert not window.bar.maximize_button.isEnabled()
    assert all(handle.isHidden() for handle in frame.handles)
    window.close()
