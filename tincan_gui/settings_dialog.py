"""Settings dialog — Desktop notifications toggle and placeholder Appearance section."""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from tincan_gui._settings import app_settings, bool_value
from tincan_gui.theme import is_dark_theme

if TYPE_CHECKING:
    from tincan_gui.dbus_client import TincandClient

_log = logging.getLogger(__name__)


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


class _AppRowWidget(QWidget):
    """Single per-app row: truncated app label + Allow/Deny button pair."""

    def __init__(
        self,
        app_id: str,
        label_hint: str,
        current_action: str,
        client: TincandClient | None,
        dark: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._app_id = app_id
        self._client = client
        self._dark = dark

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        display = app_id if len(app_id) <= 40 else app_id[:40] + "…"
        if label_hint:
            display = f"{display} ({label_hint})"
        lbl = QLabel(display)
        if len(app_id) > 40:
            lbl.setToolTip(app_id)
        lbl_font = QFont()
        lbl_font.setPointSize(11)
        lbl.setFont(lbl_font)
        lbl.setStyleSheet("color: #f4f4f5;" if dark else "color: #111827;")
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        # Ignored policy: label doesn't contribute to minimumSizeHint() so buttons
        # are never pushed off-screen by a long app ID string.
        lbl.setMinimumWidth(0)
        lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        layout.addWidget(lbl, 1)  # stretch=1: fills available space, can shrink to 0

        self._allow_btn = QPushButton("Allow")
        self._allow_btn.setCheckable(True)
        self._allow_btn.setAccessibleName(f"Allow {app_id}")

        self._deny_btn = QPushButton("Deny")
        self._deny_btn.setCheckable(True)
        self._deny_btn.setAccessibleName(f"Deny {app_id}")

        self._allow_btn.setChecked(current_action != "deny")
        self._deny_btn.setChecked(current_action == "deny")
        self._apply_button_styles()

        self._allow_btn.clicked.connect(self._on_allow_clicked)
        self._deny_btn.clicked.connect(self._on_deny_clicked)

        layout.addWidget(self._allow_btn)
        layout.addWidget(self._deny_btn)

    def _apply_button_styles(self) -> None:
        inactive = "color: #b4b4be;"
        if self._allow_btn.isChecked():
            self._allow_btn.setStyleSheet("background: #6366f1; color: #ffffff;")
        else:
            self._allow_btn.setStyleSheet(inactive)
        if self._deny_btn.isChecked():
            self._deny_btn.setStyleSheet("background: #7f1d1d; color: #fca5a5;")
        else:
            self._deny_btn.setStyleSheet(inactive)

    @Slot()
    def _on_allow_clicked(self) -> None:
        prev_deny = self._deny_btn.isChecked()
        self._allow_btn.setChecked(True)
        self._deny_btn.setChecked(False)
        self._apply_button_styles()
        if self._client:
            try:
                self._client.set_app_filter(self._app_id, "allow")
            except Exception:
                _log.warning("set_app_filter allow failed for %s — reverting", self._app_id)
                self._allow_btn.setChecked(False)
                self._deny_btn.setChecked(prev_deny)
                self._apply_button_styles()

    @Slot()
    def _on_deny_clicked(self) -> None:
        prev_allow = self._allow_btn.isChecked()
        self._deny_btn.setChecked(True)
        self._allow_btn.setChecked(False)
        self._apply_button_styles()
        if self._client:
            try:
                self._client.set_app_filter(self._app_id, "deny")
            except Exception:
                _log.warning("set_app_filter deny failed for %s — reverting", self._app_id)
                self._deny_btn.setChecked(False)
                self._allow_btn.setChecked(prev_allow)
                self._apply_button_styles()

    @property
    def allow_button(self) -> QPushButton:
        return self._allow_btn

    @property
    def deny_button(self) -> QPushButton:
        return self._deny_btn


class SettingsDialog(QDialog):
    """Settings dialog: Desktop notifications toggle + ghost Appearance section.

    Persists to QSettings key notifications/desktop_enabled (bool).
    Emits notifications_toggled(bool) when the checkbox changes.
    """

    notifications_toggled = Signal(bool)

    def __init__(
        self,
        parent: QWidget | None = None,
        client: TincandClient | None = None,
    ) -> None:
        super().__init__(parent)
        self._client = client
        self._dark = is_dark_theme()
        self._row_widgets: list[_AppRowWidget] = []

        self.setWindowTitle("Settings")
        self.setMinimumSize(400, 300)
        self.setModal(True)

        # Close button accessible name (screen readers)
        if close_btn := self.findChild(QWidget, "qt_dialog_buttonbox_button_close"):
            close_btn.setAccessibleName(self.tr("Close"))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(8)

        # ── NOTIFICATIONS section ──────────────────────────────────────────
        notif_hdr, notif_sep = _section_header("Notifications")
        layout.addWidget(notif_hdr)
        layout.addWidget(notif_sep)

        cb_font = QFont()
        cb_font.setPointSize(11)

        self._desktop_cb = QCheckBox(self.tr("Desktop notifications"))
        self._desktop_cb.setAccessibleName(self.tr("Desktop notifications"))
        self._desktop_cb.setFont(cb_font)
        self._desktop_cb.setStyleSheet(
            "color: #f4f4f5;" if self._dark else "color: #111827;"
        )

        settings = app_settings()
        enabled = bool_value(settings, "notifications/desktop_enabled", True)
        self._desktop_cb.setChecked(enabled)
        layout.addWidget(self._desktop_cb)

        sublabel = QLabel("Show a notification for each new incoming message")
        sl_font = QFont()
        sl_font.setPointSize(11)
        sublabel.setFont(sl_font)
        sublabel.setStyleSheet(
            "color: #a1a1aa;" if self._dark else "color: #6b7280;"
        )
        sublabel.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout.addWidget(sublabel)

        layout.addSpacing(20)

        # ── APP NOTIFICATIONS section ──────────────────────────────────────
        app_notif_hdr, app_notif_sep = _section_header("App Notifications")
        layout.addWidget(app_notif_hdr)
        layout.addWidget(app_notif_sep)

        self._mirror_cb = QCheckBox(self.tr("Mirror iPhone app notifications"))
        self._mirror_cb.setAccessibleName(self.tr("Mirror iPhone app notifications"))
        self._mirror_cb.setFont(cb_font)
        self._mirror_cb.setStyleSheet(
            "color: #f4f4f5;" if self._dark else "color: #111827;"
        )
        if client:
            nf = client.get_notification_filter()
            self._mirror_cb.setChecked(bool(nf.get("enabled", True)))
            self._filter_apps: dict = nf.get("apps", {})
        else:
            self._mirror_cb.setChecked(True)
            self._filter_apps = {}
        layout.addWidget(self._mirror_cb)

        # Per-app list (scroll area, min 120 / max 280 px)
        self._list_widget = QListWidget()
        self._list_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list_widget.setSpacing(2)
        self._list_widget.setSelectionMode(QListWidget.SelectionMode.NoSelection)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._list_widget)
        scroll.setMinimumHeight(120)
        scroll.setMaximumHeight(280)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self._empty_label = QLabel(
            "No app notifications received yet"
            " — notifications will appear here as they arrive."
        )
        self._empty_label.setWordWrap(True)
        self._empty_label.setStyleSheet("color: #a1a1aa;")
        empty_font = QFont()
        empty_font.setPointSize(11)
        self._empty_label.setFont(empty_font)
        self._empty_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        # Container for the list area (scroll + empty state)
        self._list_area = QWidget()
        list_area_layout = QVBoxLayout(self._list_area)
        list_area_layout.setContentsMargins(0, 0, 0, 0)
        list_area_layout.setSpacing(4)
        list_area_layout.addWidget(scroll)
        list_area_layout.addWidget(self._empty_label)

        self._opacity_effect = QGraphicsOpacityEffect()
        self._list_area.setGraphicsEffect(self._opacity_effect)

        layout.addWidget(self._list_area)

        # Populate list from daemon
        self._populate_app_list()

        # Apply initial opacity based on mirror CB state
        self._on_mirror_toggled(self._mirror_cb.isChecked())

        layout.addSpacing(20)

        # ── BEHAVIOR section ───────────────────────────────────────────────
        beh_hdr, beh_sep = _section_header("Behavior")
        layout.addWidget(beh_hdr)
        layout.addWidget(beh_sep)

        self._close_to_tray_cb = QCheckBox("Close window to tray")
        self._close_to_tray_cb.setAccessibleName("Close window to tray")
        self._close_to_tray_cb.setFont(cb_font)
        self._close_to_tray_cb.setStyleSheet(
            "color: #f4f4f5;" if self._dark else "color: #111827;"
        )
        close_to_tray_enabled = bool_value(settings, "behavior/close_to_tray", True)
        self._close_to_tray_cb.setChecked(close_to_tray_enabled)
        layout.addWidget(self._close_to_tray_cb)

        ctt_sublabel = QLabel(
            "When checked, closing the window hides tincan to the tray. "
            "Uncheck to quit on close."
        )
        ctt_sublabel.setWordWrap(True)
        ctt_sublabel.setFont(sl_font)
        ctt_sublabel.setStyleSheet(
            "color: #a1a1aa;" if self._dark else "color: #6b7280;"
        )
        ctt_sublabel.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout.addWidget(ctt_sublabel)

        layout.addSpacing(20)

        # ── BLUETOOTH section ──────────────────────────────────────────────
        bt_hdr, bt_sep = _section_header("Bluetooth")
        layout.addWidget(bt_hdr)
        layout.addWidget(bt_sep)

        bt_label = QLabel("ANCS Adapter")
        bt_label.setFont(cb_font)
        bt_label.setStyleSheet("color: #a1a1aa;" if self._dark else "color: #6b7280;")
        bt_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout.addWidget(bt_label)

        import os as _os  # noqa: PLC0415
        adapter_val = _os.environ.get("TINCAN_ANCS_ADAPTER", "")
        self._adapter_field = QLabel(adapter_val if adapter_val else "/org/bluez/hci0")
        self._adapter_field.setFont(cb_font)
        if adapter_val:
            self._adapter_field.setStyleSheet(
                "color: #f4f4f5;" if self._dark else "color: #111827;"
            )
        else:
            adapter_font = QFont()
            adapter_font.setPointSize(11)
            adapter_font.setItalic(True)
            self._adapter_field.setFont(adapter_font)
            self._adapter_field.setStyleSheet(
                "color: #a1a1aa;" if self._dark else "color: #6b7280;"
            )
        self._adapter_field.setToolTip(
            "Set TINCAN_ANCS_ADAPTER=<path> in your systemd unit or launcher script."
        )
        self._adapter_field.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout.addWidget(self._adapter_field)

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

        # ── DEVELOPER section (only when TINCAN_DEBUG=1) ──────────────────
        if os.environ.get("TINCAN_DEBUG"):
            layout.addSpacing(20)
            dev_hdr, dev_sep = _section_header("Developer")
            layout.addWidget(dev_hdr)
            layout.addWidget(dev_sep)

            from tincan_gui.debug_log import get_recent_logs  # noqa: PLC0415
            hint = QLabel(
                "Recent warnings/errors (WARNING+). "
                "Unhandled exceptions also show as popups."
            )
            hint.setWordWrap(True)
            hint.setStyleSheet("color: #a1a1aa;" if self._dark else "color: #6b7280;")
            hint_font = QFont()
            hint_font.setPointSize(10)
            hint.setFont(hint_font)
            layout.addWidget(hint)

            self._log_view = QPlainTextEdit()
            self._log_view.setReadOnly(True)
            self._log_view.setPlainText(get_recent_logs())
            log_font = QFont("Monospace")
            log_font.setPointSize(9)
            self._log_view.setFont(log_font)
            self._log_view.setMinimumHeight(120)
            self._log_view.setMaximumHeight(200)
            if self._dark:
                self._log_view.setStyleSheet(
                    "background: #18181b; color: #a1a1aa; border: 1px solid #3f3f46;"
                )
            else:
                self._log_view.setStyleSheet(
                    "background: #f9fafb; color: #374151; border: 1px solid #e5e7eb;"
                )
            layout.addWidget(self._log_view)
        else:
            self._log_view = None

        layout.addStretch()

        # ── Button box (provides the window close button) ──────────────────
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn:
            close_btn.setAccessibleName(self.tr("Close"))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Wire checkboxes → persist / daemon
        self._desktop_cb.toggled.connect(self._on_notif_toggled)
        self._mirror_cb.toggled.connect(self._on_mirror_toggled)
        self._close_to_tray_cb.toggled.connect(self._on_close_to_tray_toggled)

        # Live refresh via AppNotificationReceived
        if client:
            client.app_notification_received.connect(self._on_app_notification_received)

        # Tab order: desktop CB → mirror CB → row Allow/Deny pairs → close-to-tray CB
        self._rebuild_tab_order()

    # ------------------------------------------------------------------
    # App list population / refresh
    # ------------------------------------------------------------------

    def _populate_app_list(self) -> None:
        seen: list[dict] = self._client.get_seen_apps() if self._client else []
        self._list_widget.clear()
        self._row_widgets = []
        for app in seen:
            app_id = str(app.get("app_id", ""))
            label_hint = str(app.get("label_hint", ""))
            if not app_id:
                continue
            action = self._filter_apps.get(app_id, "allow")
            row = _AppRowWidget(app_id, label_hint, action, self._client, self._dark)
            item = QListWidgetItem()
            item.setSizeHint(QSize(1, row.sizeHint().height()))  # width=1: let view use viewport width
            self._list_widget.addItem(item)
            self._list_widget.setItemWidget(item, row)
            self._row_widgets.append(row)

        has_apps = bool(seen)
        self._list_widget.setVisible(has_apps)
        self._empty_label.setVisible(not has_apps)

    def _refresh_app_list(self) -> None:
        """Re-read seen apps from daemon and repopulate without resetting scroll."""
        if not self._client:
            return
        scroll_bar = self._list_widget.verticalScrollBar()
        pos = scroll_bar.value() if scroll_bar else 0
        nf = self._client.get_notification_filter()
        self._filter_apps = nf.get("apps", {})
        self._populate_app_list()
        if scroll_bar:
            scroll_bar.setValue(pos)
        self._rebuild_tab_order()

    def _rebuild_tab_order(self) -> None:
        prev: QWidget = self._mirror_cb
        for row in self._row_widgets:
            QWidget.setTabOrder(prev, row.allow_button)
            QWidget.setTabOrder(row.allow_button, row.deny_button)
            prev = row.deny_button
        QWidget.setTabOrder(prev, self._close_to_tray_cb)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_notif_toggled(self, checked: bool) -> None:
        s = app_settings()
        s.setValue("notifications/desktop_enabled", checked)
        s.sync()  # flush immediately so the notifier's next read sees the change
        self.notifications_toggled.emit(checked)

    @Slot(bool)
    def _on_mirror_toggled(self, checked: bool) -> None:
        self._opacity_effect.setOpacity(1.0 if checked else 0.5)
        if self._client:
            self._client.set_notifications_enabled(checked)

    def _on_close_to_tray_toggled(self, checked: bool) -> None:
        s = app_settings()
        s.setValue("behavior/close_to_tray", checked)
        s.sync()

    @Slot(dict)
    def _on_app_notification_received(self, _payload: dict) -> None:
        self._refresh_app_list()

    # ------------------------------------------------------------------
    # Properties / helpers used by tests
    # ------------------------------------------------------------------

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
