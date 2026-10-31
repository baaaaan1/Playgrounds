from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter
from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

_SUGGESTIONS = (
    "Jelaskan cara kerja transformer secara sederhana",
    "Buat skrip Python untuk merapikan nama file",
    "Ringkas teks ini menjadi 5 poin penting",
)


class _Mark(QWidget):
    def __init__(self, tokens: dict[str, str], parent=None) -> None:
        super().__init__(parent)
        self._tokens = dict(tokens)
        self.setFixedSize(60, 60)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        gradient = QLinearGradient(QPointF(0, 0), QPointF(60, 60))
        gradient.setColorAt(0.0, QColor(self._tokens["accent"]))
        gradient.setColorAt(1.0, QColor(self._tokens["accent_hover"]))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawRoundedRect(QRectF(0, 0, 60, 60), 16, 16)

        font = QFont(self.font())
        font.setPointSizeF(22)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor(self._tokens["accent_text"]))
        painter.drawText(QRectF(0, 0, 60, 60), Qt.AlignmentFlag.AlignCenter, "P")
        painter.end()

    def set_tokens(self, tokens: dict[str, str]) -> None:
        self._tokens = dict(tokens)
        self.update()


class EmptyState(QWidget):
    suggestion_chosen = pyqtSignal(str)

    def __init__(self, tokens: dict[str, str], parent=None) -> None:
        super().__init__(parent)
        self._mark = _Mark(tokens)
        title = QLabel("Mau eksplorasi apa hari ini?")
        title.setObjectName("EmptyTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("Pilih provider, ketik pesan, dan mulai percakapan.")
        subtitle.setObjectName("EmptySubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(10)
        layout.addStretch(1)
        layout.addWidget(self._mark, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(8)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(18)

        for text in _SUGGESTIONS:
            button = QPushButton(text)
            button.setObjectName("Suggestion")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMaximumWidth(460)
            button.clicked.connect(lambda _checked=False, t=text: self.suggestion_chosen.emit(t))
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)

        layout.addStretch(2)

    def set_tokens(self, tokens: dict[str, str]) -> None:
        self._mark.set_tokens(tokens)
