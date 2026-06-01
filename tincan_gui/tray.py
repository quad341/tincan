"""System tray icon: connected/disconnected state + unread badge (OQ-UI-6)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QSystemTrayIcon

if TYPE_CHECKING:
    from tincan_gui.main import MainWindow

_ICON_SIZE = 22
_BADGE_SIZE = 9  # diameter of the red unread dot


def _make_base_pixmap(connected: bool) -> QPixmap:
    """Draw a 22×22 'T' lettermark in a circle — blue (connected) or grey."""
    px = QPixmap(_ICON_SIZE, _ICON_SIZE)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    bg = QColor("#1d4ed8") if connected else QColor("#9ca3af")
    p.setBrush(bg)
    p.setPen(Qt.NoPen)
    p.drawEllipse(0, 0, _ICON_SIZE, _ICON_SIZE)
    font = QFont()
    font.setPixelSize(13)
    font.setBold(True)
    p.setFont(font)
    p.setPen(QColor("#ffffff"))
    p.drawText(px.rect(), Qt.AlignCenter, "T")
    p.end()
    return px


def _make_icon(connected: bool, unread: int) -> QIcon:
    """Compose base icon + optional red badge for unread count."""
    px = _make_base_pixmap(connected)
    if unread > 0:
        p = QPainter(px)
        p.setRenderHint(QPainter.Antialiasing)
        # Badge circle in top-right corner
        bx = _ICON_SIZE - _BADGE_SIZE
        p.setBrush(QColor("#ef4444"))
        p.setPen(Qt.NoPen)
        p.drawEllipse(bx, 0, _BADGE_SIZE, _BADGE_SIZE)
        # Badge digit (capped at 9+)
        label = str(unread) if unread < 10 else "9+"
        font = QFont()
        font.setPixelSize(6)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor("#ffffff"))
        from PySide6.QtCore import QRect
        p.drawText(QRect(bx, 0, _BADGE_SIZE, _BADGE_SIZE), Qt.AlignCenter, label)
        p.end()
    return QIcon(px)


class TrayIcon(QSystemTrayIcon):
    """System tray icon for tincan (OQ-UI-6).

    Tracks connection state and unread message count; increments only when the
    main window is not the active window (no badge spam while user is watching).
    """

    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self._window = window
        self._connected = False
        self._unread = 0
        self._update()
        self.activated.connect(self._on_activated)
        if self.isSystemTrayAvailable():
            self.show()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_connected(self, connected: bool) -> None:
        self._connected = connected
        self._unread = 0  # reset badge on any connection state change
        self._update()

    def increment_unread(self) -> None:
        """Increment badge — only when main window is not the active window."""
        if not self._window.isActiveWindow():
            self._unread += 1
            self._update()

    def reset_unread(self) -> None:
        if self._unread != 0:
            self._unread = 0
            self._update()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _update(self) -> None:
        self.setIcon(_make_icon(self._connected, self._unread))
        if self._unread > 0:
            tip = f"tincan — {self._unread} unread"
        elif self._connected:
            tip = "tincan — connected"
        else:
            tip = "tincan — disconnected"
        self.setToolTip(tip)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:  # left-click
            self._window.show()
            self._window.raise_()
            self._window.activateWindow()
            self.reset_unread()
