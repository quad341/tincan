"""System tray icon: connected/disconnected state + unread badge (OQ-UI-6)."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from tincan_gui._settings import app_settings

if TYPE_CHECKING:
    from tincan_gui.main import MainWindow

_ICON_SIZE = 22
_BADGE_SIZE = 9  # diameter of the red unread dot
_ASSETS = Path(__file__).parent / "assets"


def _make_base_pixmap(connected: bool) -> QPixmap:
    """Load tincan-icon.png scaled to 22×22; greyscale when disconnected."""
    px = QPixmap(str(_ASSETS / "tincan-icon.png")).scaled(
        _ICON_SIZE, _ICON_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation
    )
    if not connected:
        img = px.toImage().convertToFormat(QImage.Format_Grayscale8)
        px = QPixmap.fromImage(img)
    return px


def _make_icon(connected: bool, unread: int, repair_needed: bool = False) -> QIcon:
    """Compose base icon + optional badges: error glyph (repair) or unread count."""
    px = _make_base_pixmap(connected)
    if repair_needed:
        p = QPainter(px)
        p.setRenderHint(QPainter.Antialiasing)
        bx = _ICON_SIZE - _BADGE_SIZE
        p.setBrush(QColor("#f97316"))
        p.setPen(Qt.NoPen)
        p.drawEllipse(bx, 0, _BADGE_SIZE, _BADGE_SIZE)
        font = QFont()
        font.setPixelSize(7)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor("#ffffff"))
        from PySide6.QtCore import QRect
        p.drawText(QRect(bx, 0, _BADGE_SIZE, _BADGE_SIZE), Qt.AlignCenter, "!")
        p.end()
    elif unread > 0:
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
        self._repair_needed = False
        self._update()
        self._build_menu()
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

    def set_repair_needed(self, needs_repair: bool) -> None:
        """Show/clear the ANCS repair error glyph on the tray icon."""
        self._repair_needed = needs_repair
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

    def sync_notifications_action(self, enabled: bool) -> None:
        """Sync tray notifications toggle when the Settings dialog changes it."""
        self._notif_action.setChecked(enabled)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        menu = QMenu()
        menu.aboutToShow.connect(self._on_menu_about_to_show)

        self._notif_action = QAction("Desktop notifications", menu)
        self._notif_action.setCheckable(True)
        self._notif_action.triggered.connect(self._on_notifications_toggled)
        menu.addAction(self._notif_action)

        menu.addSeparator()

        open_action = QAction("Open tincan", menu)
        open_action.triggered.connect(self._raise_window)
        menu.addAction(open_action)

        settings_action = QAction("Settings...", menu)
        settings_action.triggered.connect(self._window._open_settings)
        menu.addAction(settings_action)

        menu.addSeparator()

        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)

    def _on_menu_about_to_show(self) -> None:
        enabled = app_settings().value("notifications/desktop_enabled", True, type=bool)
        self._notif_action.setChecked(enabled)

    def _on_notifications_toggled(self, checked: bool) -> None:
        app_settings().setValue("notifications/desktop_enabled", checked)

    def _raise_window(self) -> None:
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()
        self.reset_unread()

    def _update(self) -> None:
        self.setIcon(_make_icon(self._connected, self._unread, self._repair_needed))
        if self._repair_needed:
            tip = "Tin Can: iPhone notifications unavailable"
        elif self._unread > 0:
            tip = f"tincan — {self._unread} unread"
        elif self._connected:
            tip = "tincan — connected"
        else:
            tip = "tincan — disconnected"
        self.setToolTip(tip)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:  # left-click
            self._raise_window()
