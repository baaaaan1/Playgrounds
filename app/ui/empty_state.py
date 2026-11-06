from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import icons


class _Mark(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(64, 64)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        icons.app_icon().paint(painter, self.rect())
        painter.end()


class EmptyState(QScrollArea):
    suggestion_chosen = pyqtSignal(str)

    def __init__(self, tokens: dict[str, str], parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("EmptyState")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("EmptyContent")
        self.setWidget(content)
        self._mark = _Mark()
        title = QLabel(self.tr("What would you like to explore today?"))
        title.setObjectName("EmptyTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)
        subtitle = QLabel(self.tr("Choose a connection, type a message, and start a chat."))
        subtitle.setObjectName("EmptySubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)
        layout.addStretch(1)
        layout.addWidget(self._mark, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(8)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(18)

        for text in (
            self.tr("Explain how transformers work in simple terms"),
            self.tr("Write a Python script to tidy up file names"),
            self.tr("Summarize this text in 5 key points"),
        ):
            button = QPushButton()
            button.setObjectName("Suggestion")
            button.setAccessibleName(text)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMaximumWidth(460)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            label = QLabel(text)
            label.setWordWrap(True)
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            button_layout = QVBoxLayout(button)
            button_layout.setContentsMargins(14, 10, 14, 10)
            button_layout.addWidget(label)
            button.clicked.connect(lambda _checked=False, t=text: self.suggestion_chosen.emit(t))
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.addStretch()
            row.addWidget(button, 1)
            row.addStretch()
            layout.addLayout(row)

        layout.addStretch(2)

    def set_tokens(self, tokens: dict[str, str]) -> None:
        self._mark.update()
