"""Contact avatar widget: 40×40 circle — PBAP photo or deterministic initials fallback."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QLabel, QWidget

_GROUP_AVATAR_W = 52
_GROUP_AVATAR_H = 52
_GROUP_FRONT_X = 12
_GROUP_FRONT_Y = 12

_AVATAR_SIZE = 40
_PALETTE = [
    "#0369a1", "#7c3aed", "#db2777", "#b45309",
    "#047857", "#dc2626", "#4f46e5", "#0f766e",
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


class GroupAvatarWidget(QWidget):
    """52×52 stacked-circles avatar for group conversations.

    Back circle at (0, 0); front circle at (_GROUP_FRONT_X, _GROUP_FRONT_Y).
    Front circle shows PBAP photo if available; both fall back to initials.
    """

    def __init__(
        self,
        back_name: str,
        front_name: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._back_name = back_name
        self._front_name = front_name
        self._front_photo: bytes | None = None
        self.setFixedSize(_GROUP_AVATAR_W, _GROUP_AVATAR_H)

    def set_front_photo(self, data: bytes) -> None:
        self._front_photo = data
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        back_px = _make_initials_pixmap(self._back_name, _AVATAR_SIZE)
        painter.drawPixmap(0, 0, back_px)
        if self._front_photo:
            front_px = _make_photo_pixmap(self._front_photo, _AVATAR_SIZE)
            if front_px.isNull():
                front_px = _make_initials_pixmap(self._front_name, _AVATAR_SIZE)
        else:
            front_px = _make_initials_pixmap(self._front_name, _AVATAR_SIZE)
        painter.drawPixmap(_GROUP_FRONT_X, _GROUP_FRONT_Y, front_px)
        painter.end()


class AvatarWidget(QLabel):
    """Circular avatar — PBAP photo or initials fallback. Default size is 40×40."""

    def __init__(self, name: str, size: int = _AVATAR_SIZE, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._name = name
        self._size = size
        self.setFixedSize(size, size)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet("border: none; outline: none; background: transparent;")
        self._show_initials()

    def _show_initials(self) -> None:
        px = _make_initials_pixmap(self._name, self._size)
        self.setPixmap(px)
        self.setAccessibleName(self.tr("Contact photo for {}").format(self._name))

    def set_photo(self, data: bytes) -> None:
        """Display PBAP photo (raw JPEG/PNG bytes). Falls back to initials on decode error."""
        px = _make_photo_pixmap(data, self._size)
        if px.isNull():
            self._show_initials()
        else:
            self.setPixmap(px)
        self.setAccessibleName(self.tr("Contact photo for {}").format(self._name))

    def set_photo_pixmap(self, px: QPixmap) -> None:
        """Display a pre-rendered circular pixmap (e.g. from a cached QPixmap)."""
        self.setPixmap(px)
        self.setAccessibleName(self.tr("Contact photo for {}").format(self._name))

    def update_for_name(self, name: str) -> None:
        """Reset to initials for a new contact name."""
        self._name = name
        self._show_initials()
