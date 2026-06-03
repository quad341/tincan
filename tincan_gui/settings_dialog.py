"""Settings dialog — Desktop notifications toggle and placeholder Appearance section."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from tincan_gui._settings import app_settings
from tincan_gui.theme import is_dark_theme


def _section_header(text: str) -> tuple[QLabel, QFrame]:
    """Return a (header QLabel, separator QFrame) pair styled per design spec."""
    label = QLabel(text.upper())
    font = QFont()
    font.setPointSize(10)
    label.setFont(font)
    label.setStyleSheet("color: #9ca3af;")
    label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

    _dark = is_dark_theme()
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setFixedHeight(1)
    sep.setStyleSheet(
        "background-color: #3f3f46; border: none;" if _dark
        else "background-color: #e5e7eb; border: none;"
    )

    return label, sep


class SettingsDialog(QDialog):
    """Settings dialog: Desktop notifications toggle + ghost Appearance section.

    Persists to QSettings key notifications/desktop_enabled (bool).
    Emits notifications_toggled(bool) when the checkbox changes.
    """

    notifications_toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(400, 300)
        self.setModal(True)

        # Close button accessible name (screen readers)
        if close_btn := self.findChild(QWidget, "qt_dialog_buttonbox_button_close"):
            close_btn.setAccessibleName("Close")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(8)

        # ── NOTIFICATIONS section ──────────────────────────────────────────
        notif_hdr, notif_sep = _section_header("Notifications")
        layout.addWidget(notif_hdr)
        layout.addWidget(notif_sep)

        _dark = is_dark_theme()
        self._desktop_cb = QCheckBox("Desktop notifications")
        self._desktop_cb.setAccessibleName("Desktop notifications")
        cb_font = QFont()
        cb_font.setPointSize(11)
        self._desktop_cb.setFont(cb_font)
        self._desktop_cb.setStyleSheet(
            "color: #f4f4f5;" if _dark else "color: #111827;"
        )

        settings = app_settings()
        enabled = settings.value("notifications/desktop_enabled", True, type=bool)
        self._desktop_cb.setChecked(enabled)
        layout.addWidget(self._desktop_cb)

        sublabel = QLabel("Show a notification for each new incoming message")
        sl_font = QFont()
        sl_font.setPointSize(11)
        sublabel.setFont(sl_font)
        sublabel.setStyleSheet(
            "color: #a1a1aa;" if _dark else "color: #6b7280;"
        )
        sublabel.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout.addWidget(sublabel)

        layout.addSpacing(20)

        # ── APPEARANCE section (ghost/placeholder) ─────────────────────────
        app_hdr, app_sep = _section_header("Appearance")
        app_hdr.setStyleSheet("color: #d1d5db;")
        layout.addWidget(app_hdr)
        layout.addWidget(app_sep)

        ghost_label = QLabel("Theme options coming soon")
        ghost_label.setStyleSheet("color: #d1d5db;")
        ghost_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout.addWidget(ghost_label)

        layout.addStretch()

        # ── Button box (provides the window close button) ──────────────────
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn:
            close_btn.setAccessibleName("Close")
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Wire checkbox → persist + emit signal
        self._desktop_cb.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked: bool) -> None:
        s = app_settings()
        s.setValue("notifications/desktop_enabled", checked)
        s.sync()  # flush immediately so the notifier's next read sees the change
        self.notifications_toggled.emit(checked)

    def checkbox_label_color(self) -> str:
        """Return the hex color applied to the checkbox label (used by a11y tests)."""
        style = self._desktop_cb.styleSheet()
        for part in style.split(";"):
            if "color" in part:
                return part.split(":")[1].strip()
        return "#111827"

    @property
    def desktop_notifications_enabled(self) -> bool:
        return self._desktop_cb.isChecked()
