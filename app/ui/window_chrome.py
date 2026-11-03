from __future__ import annotations

import sys

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt
from PyQt6.QtGui import QMouseEvent, QResizeEvent
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QSizePolicy, QToolButton, QWidget

from . import icons


def _resizable_edges(window: QWidget, edges: Qt.Edge) -> Qt.Edge:
    if window.isMaximized() or window.isFullScreen():
        return Qt.Edge(0)
    if window.minimumWidth() >= window.maximumWidth():
        edges &= ~(Qt.Edge.LeftEdge | Qt.Edge.RightEdge)
    if window.minimumHeight() >= window.maximumHeight():
        edges &= ~(Qt.Edge.TopEdge | Qt.Edge.BottomEdge)
    return edges


class _ResizeEdge(QWidget):
    def __init__(self, window: QWidget, edges: Qt.Edge) -> None:
        super().__init__(window)
        self.edges = edges
        self._origin: QPoint | None = None
        self._geometry = QRect()
        self.setObjectName("WindowResizeEdge")
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        if edges in (Qt.Edge.LeftEdge, Qt.Edge.RightEdge):
            cursor = Qt.CursorShape.SizeHorCursor
        elif edges in (Qt.Edge.TopEdge, Qt.Edge.BottomEdge):
            cursor = Qt.CursorShape.SizeVerCursor
        elif edges in (Qt.Edge.TopEdge | Qt.Edge.LeftEdge, Qt.Edge.BottomEdge | Qt.Edge.RightEdge):
            cursor = Qt.CursorShape.SizeFDiagCursor
        else:
            cursor = Qt.CursorShape.SizeBDiagCursor
        self.setCursor(cursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        edges = _resizable_edges(self.window(), self.edges)
        if event.button() != Qt.MouseButton.LeftButton or not edges:
            return super().mousePressEvent(event)
        handle = self.window().windowHandle()
        if handle is None or not handle.startSystemResize(edges):
            self._origin = event.globalPosition().toPoint()
            self._geometry = self.window().geometry()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._origin is None:
            return super().mouseMoveEvent(event)
        window = self.window()
        delta = event.globalPosition().toPoint() - self._origin
        rect = QRect(self._geometry)
        edges = _resizable_edges(window, self.edges)
        if edges & Qt.Edge.LeftEdge:
            width = max(window.minimumWidth(), min(window.maximumWidth(), rect.width() - delta.x()))
            rect.setLeft(rect.right() - width + 1)
        elif edges & Qt.Edge.RightEdge:
            rect.setWidth(max(window.minimumWidth(), min(window.maximumWidth(), rect.width() + delta.x())))
        if edges & Qt.Edge.TopEdge:
            height = max(window.minimumHeight(), min(window.maximumHeight(), rect.height() - delta.y()))
            rect.setTop(rect.bottom() - height + 1)
        elif edges & Qt.Edge.BottomEdge:
            rect.setHeight(max(window.minimumHeight(), min(window.maximumHeight(), rect.height() + delta.y())))
        window.setGeometry(rect)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._origin = None
        super().mouseReleaseEvent(event)


class _ResizeFrame(QObject):
    def __init__(self, window: QWidget, border: int) -> None:
        super().__init__(window)
        self.border = border
        top, bottom, left, right = (
            Qt.Edge.TopEdge, Qt.Edge.BottomEdge, Qt.Edge.LeftEdge, Qt.Edge.RightEdge
        )
        self.handles = [
            _ResizeEdge(window, edges)
            for edges in (top, bottom, left, right, top | left, top | right, bottom | left, bottom | right)
        ]
        window.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() in (
            QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.WindowStateChange,
            QEvent.Type.LayoutRequest,
        ):
            self.update_handles()
        return False

    def update_handles(self) -> None:
        window = self.parent()
        b = self.border
        w, h = window.width(), window.height()
        rects = (
            (b, 0, max(0, w - 2 * b), b),
            (b, h - b, max(0, w - 2 * b), b),
            (0, b, b, max(0, h - 2 * b)),
            (w - b, b, b, max(0, h - 2 * b)),
            (0, 0, b, b), (w - b, 0, b, b),
            (0, h - b, b, b), (w - b, h - b, b, b),
        )
        for handle, rect in zip(self.handles, rects, strict=True):
            handle.setGeometry(*rect)
            handle.setVisible(bool(_resizable_edges(window, handle.edges)))
            handle.raise_()


class FramelessWindowMixin:
    """Place before QMainWindow/QDialog in the MRO; call setup before show()."""

    def setup_frameless_window(self, resize_border: int = 6) -> None:
        if hasattr(self, "_frameless_resize_frame"):
            return
        if resize_border < 1:
            raise ValueError("Resize border must be positive")
        # Preserve Dialog/Window and modality flags rather than replacing them.
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self._frameless_resize_frame = _ResizeFrame(self, resize_border)

    def nativeEvent(self, event_type, message):  # noqa: N802
        if sys.platform == "win32" and hasattr(self, "_frameless_resize_frame"):
            import ctypes
            from ctypes import wintypes

            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0084:  # WM_NCHITTEST uses physical screen coordinates.
                rect = wintypes.RECT()
                # winId() can re-enter window creation from this native callback.
                hwnd = wintypes.HWND(msg.hWnd)
                if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    x = ctypes.c_short(msg.lParam & 0xFFFF).value
                    y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                    border = round(self._frameless_resize_frame.border * self.devicePixelRatioF())
                    edges = Qt.Edge(0)
                    if rect.left <= x < rect.left + border:
                        edges |= Qt.Edge.LeftEdge
                    elif rect.right - border <= x < rect.right:
                        edges |= Qt.Edge.RightEdge
                    if rect.top <= y < rect.top + border:
                        edges |= Qt.Edge.TopEdge
                    elif rect.bottom - border <= y < rect.bottom:
                        edges |= Qt.Edge.BottomEdge
                    edges = _resizable_edges(self, edges)
                    hit = {
                        Qt.Edge.LeftEdge: 10, Qt.Edge.RightEdge: 11,
                        Qt.Edge.TopEdge: 12, Qt.Edge.TopEdge | Qt.Edge.LeftEdge: 13,
                        Qt.Edge.TopEdge | Qt.Edge.RightEdge: 14, Qt.Edge.BottomEdge: 15,
                        Qt.Edge.BottomEdge | Qt.Edge.LeftEdge: 16,
                        Qt.Edge.BottomEdge | Qt.Edge.RightEdge: 17,
                    }.get(edges)
                    if hit is not None:
                        return True, hit
        handled, result = super().nativeEvent(event_type, message)
        # Some PyQt versions expose an unhandled result as None; the Windows
        # virtual callback still requires an integer LRESULT on return.
        return handled, 0 if result is None else result


class _TitleLabel(QLabel):
    def __init__(self, text: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802
        self._full_text = text
        self.setAccessibleName(text)
        self._elide()

    def _elide(self) -> None:
        text = self.fontMetrics().elidedText(
            self._full_text, Qt.TextElideMode.ElideRight, self.contentsRect().width(),
        )
        super().setText(text)
        self.setToolTip(self._full_text if text != self._full_text else "")

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._elide()

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self._elide()


class TitleBar(QWidget):
    """Themed, draggable window caption with optional close-only dialog controls."""

    def __init__(
        self,
        window: QWidget,
        tokens: dict[str, str],
        *,
        title: str | None = None,
        show_minimize: bool = True,
        show_maximize: bool = True,
    ) -> None:
        super().__init__(window)
        self._window = window
        self._tokens = dict(tokens)
        self._can_maximize = show_maximize
        self._drag_origin: QPoint | None = None
        self._drag_offset: QPoint | None = None
        self._close_hovered = False
        self.setObjectName("WindowTitleBar")
        self.setProperty("active", window.isActiveWindow())
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setFixedHeight(42)

        self._brand = QLabel(self)
        self._brand.setObjectName("WindowBrand")
        self._brand.setFixedSize(22, 22)
        self._title = _TitleLabel(window.windowTitle() if title is None else title, self)
        self._title.setObjectName("WindowTitle")
        self._title.setProperty("active", window.isActiveWindow())
        for label in (self._brand, self._title):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        if title is None:
            window.windowTitleChanged.connect(self._title.setText)
        window.windowIconChanged.connect(self._refresh_brand)

        controls = QWidget(self)
        controls.setObjectName("WindowControls")
        panels = QHBoxLayout(controls)
        panels.setContentsMargins(0, 0, 0, 0)
        panels.setSpacing(0)
        self.minimize_button = self._button("WindowMinimize", "Minimize", controls)
        self.maximize_button = self._button("WindowMaximize", "Maximize", controls)
        self.close_button = self._button("WindowClose", "Close", controls)
        self.close_button.installEventFilter(self)
        self.minimize_button.setVisible(show_minimize)
        self.maximize_button.setVisible(show_maximize)
        self.minimize_button.clicked.connect(window.showMinimized)
        self.maximize_button.clicked.connect(self.toggle_maximized)
        self.close_button.clicked.connect(window.close)
        for button in (self.minimize_button, self.maximize_button, self.close_button):
            panels.addWidget(button)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self._brand)
        layout.addWidget(self._title, 1)
        layout.addWidget(controls)
        window.installEventFilter(self)
        self.refresh_theme(tokens)

    def _button(self, name: str, text: str, parent: QWidget) -> QToolButton:
        button = QToolButton(parent)
        button.setObjectName(name)
        button.setProperty("windowControl", True)
        button.setToolTip(text)
        button.setAccessibleName(text)
        button.setFixedSize(46, 42)
        button.setIconSize(QSize(18, 18))
        button.setCursor(Qt.CursorShape.ArrowCursor)
        button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        return button

    def refresh_theme(self, tokens: dict[str, str]) -> None:
        self._tokens = dict(tokens)
        self._refresh_brand()
        self._refresh_controls()

    def _refresh_brand(self) -> None:
        icon = self._window.windowIcon()
        if icon.isNull():
            icon = icons.icon("brand", self._tokens["accent"], 22)
        self._brand.setPixmap(icon.pixmap(QSize(22, 22), self.devicePixelRatioF()))

    def _control_color(self) -> str:
        return self._tokens["text_muted" if self.property("active") else "text_faint"]

    def _refresh_controls(self) -> None:
        self.minimize_button.setIcon(icons.icon("minimize", self._control_color()))
        self._refresh_close()
        self._refresh_maximize()

    def _refresh_close(self) -> None:
        color = "#ffffff" if self._close_hovered else self._control_color()
        self.close_button.setIcon(icons.icon("close", color))

    def _refresh_maximize(self) -> None:
        maximized = self._window.isMaximized()
        action = "Restore" if maximized else "Maximize"
        self.maximize_button.setToolTip(action)
        self.maximize_button.setAccessibleName(action)
        self.maximize_button.setIcon(icons.icon("restore" if maximized else "maximize", self._control_color()))
        # Windows may also flag a monitor-filling frameless maximized window as fullscreen.
        self.maximize_button.setEnabled(
            self._can_maximize and (maximized or not self._window.isFullScreen())
            and self._window.minimumSize() != self._window.maximumSize()
        )

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self.close_button and event.type() in (QEvent.Type.Enter, QEvent.Type.Leave):
            self._close_hovered = event.type() == QEvent.Type.Enter
            self._refresh_close()
        if watched is self._window:
            if event.type() in (QEvent.Type.WindowActivate, QEvent.Type.WindowDeactivate):
                active = event.type() == QEvent.Type.WindowActivate
                for widget in (self, self._title):
                    widget.setProperty("active", active)
                    widget.style().unpolish(widget)
                    widget.style().polish(widget)
                    widget.update()
                if not active:
                    self._drag_origin = self._drag_offset = None
                self._refresh_controls()
            elif event.type() in (
                QEvent.Type.WindowStateChange, QEvent.Type.Show, QEvent.Type.LayoutRequest,
            ):
                self._refresh_maximize()
        return False

    def toggle_maximized(self) -> None:
        self._refresh_maximize()
        if self._can_maximize and self.maximize_button.isEnabled():
            if self._window.isMaximized():
                self._window.showNormal()
            elif not self._window.isFullScreen():
                self._window.showMaximized()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = self._drag_offset = None
            self.toggle_maximized()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or (
            self._window.isFullScreen() and not self._window.isMaximized()
        ):
            return super().mousePressEvent(event)
        self._drag_origin = event.globalPosition().toPoint()
        self._drag_offset = self._drag_origin - self._window.pos()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_offset is None or not event.buttons() & Qt.MouseButton.LeftButton:
            return super().mouseMoveEvent(event)
        position = event.globalPosition().toPoint()
        if self._drag_origin is not None:
            if (position - self._drag_origin).manhattanLength() < QApplication.startDragDistance():
                event.accept()
                return
            self._drag_origin = None
            handle = self._window.windowHandle()
            if handle is not None and handle.startSystemMove():
                self._drag_offset = None
                event.accept()
                return
        if self._window.isMaximized():
            ratio = max(0.0, min(1.0, self._drag_offset.x() / max(1, self._window.width())))
            self._window.showNormal()
            self._drag_offset.setX(round(self._window.width() * ratio))
            self._drag_offset.setY(min(self._drag_offset.y(), self.height() - 1))
        self._window.move(position - self._drag_offset)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = self._drag_offset = None
        super().mouseReleaseEvent(event)
