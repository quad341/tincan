"""Contact avatar widget: 40×40 circle — PBAP photo or deterministic initials fallback."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QLabel, QWidget

_AVATAR_SIZE = 40
_PALETTE = [
    "#0ea5e9", "#8b5cf6", "#ec4899", "#f59e0b",
    "#10b981", "#ef4444", "#6366f1", "#14b8a6",
]


def _initials(name: str) -> str:
    parts = name.strip().split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return name[:2].upper() if name else "?"


def _color_for_name(name: str) -> str:
    return _PALETTE[sum(ord(c) for c in name) % len(_PALETTE)]


def _make_initials_pixmap(name: str, size: int) -> QPixmap:
    color = _color_for_name(name)
    px = QPixmap(size, size)
    px.fill(Qt.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(0, 0, size, size)
    font = QFont()
    font.setPixelSize(int(size * 0.38))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#ffffff"))
    painter.drawText(px.rect(), Qt.AlignCenter, _initials(name))
    painter.end()
    return px


def _make_photo_pixmap(data: bytes, size: int) -> QPixmap:
    px = QPixmap()
    px.loadFromData(data)
    if px.isNull():
        return QPixmap()
    # Crop to square then scale, then clip to circle
    side = min(px.width(), px.height())
    px = px.copy(
        (px.width() - side) // 2,
        (px.height() - side) // 2,
        side, side,
    )
    px = px.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    # Clip to circle via DestinationIn: draw photo, then intersect with ellipse alpha
    result = QPixmap(size, size)
    result.fill(Qt.transparent)
    p = QPainter(result)
    p.setRenderHint(QPainter.Antialiasing)
    p.drawPixmap(0, 0, px)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    p.setBrush(Qt.black)
    p.setPen(Qt.NoPen)
    p.drawEllipse(0, 0, size, size)
    p.end()
    return result


class AvatarWidget(QLabel):
    """40×40 circular avatar — PBAP photo or initials fallback."""

    def __init__(self, name: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._name = name
        self.setFixedSize(_AVATAR_SIZE, _AVATAR_SIZE)
        self._show_initials()

    def _show_initials(self) -> None:
        px = _make_initials_pixmap(self._name, _AVATAR_SIZE)
        self.setPixmap(px)
        self.setAccessibleName(f"Contact photo for {self._name}")

    def set_photo(self, data: bytes) -> None:
        """Display PBAP photo (raw JPEG/PNG bytes). Falls back to initials on decode error."""
        px = _make_photo_pixmap(data, _AVATAR_SIZE)
        if px.isNull():
            self._show_initials()
        else:
            self.setPixmap(px)
