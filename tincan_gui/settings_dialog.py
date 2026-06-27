"""Settings dialog — Desktop notifications toggle and placeholder Appearance section."""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication, QModelIndex, QSize, Qt, QThread, Signal, Slot
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from tincan_gui._settings import app_settings, bool_value
from tincan_gui.daemon_launcher import spawn_daemon
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


_active_loaders: list = []


class _AdapterLoader(QThread):
    """Background thread that calls client.get_adapters() and emits results.

    Added to _active_loaders on start, removed on finish, so Qt never tries
    to delete a still-running thread (which aborts).
    """

    loaded: Signal = Signal(list)

    def __init__(self, client: object) -> None:
        super().__init__()
        self._client = client

    def start(self, priority=QThread.Priority.InheritPriority) -> None:
        _active_loaders.append(self)
        self.finished.connect(self._remove_self)
        super().start(priority)

    @Slot()
    def _remove_self(self) -> None:
        try:
            _active_loaders.remove(self)
        except ValueError:
            pass

    def run(self) -> None:
        try:
            adapters = self._client.get_adapters()
        except Exception:
            adapters = []
        self.loaded.emit(adapters)


class _DeviceLoader(QThread):
    """Background thread that discovers oFono HFP modems for the device picker."""

    loaded: Signal = Signal(list)

    def start(self, priority=QThread.Priority.InheritPriority) -> None:
        _active_loaders.append(self)
        self.finished.connect(self._remove_self)
        super().start(priority)

    @Slot()
    def _remove_self(self) -> None:
        try:
            _active_loaders.remove(self)
        except ValueError:
            pass

    def run(self) -> None:
        import re as _re  # noqa: PLC0415

        devices: list[dict] = []
        try:
            import dbus  # noqa: PLC0415

            bus = dbus.SystemBus()
            obj = bus.get_object("org.ofono", "/")
            iface = dbus.Interface(obj, "org.ofono.Manager")
            for path, props in iface.GetModems():
                props = dict(props)
                if str(props.get("Type", "")) != "hfp":
                    continue
                m = _re.search(r"/dev_([0-9A-Fa-f_]{17})$", str(path))
                if not m:
                    continue
                mac = m.group(1).replace("_", ":")
                name = str(props.get("Name", "") or "")
                devices.append({"mac": mac, "name": name})
        except Exception:  # noqa: BLE001
            pass
        self.loaded.emit(devices)


class _AdapterItemDelegate(QStyledItemDelegate):
    """Rich two-line delegate for the BT adapter QComboBox (AC 4).

    Line 1: alias 12pt #f4f4f5 — Line 2: MAC address 10pt #a1a1aa.
    sizeHint height 50px gives enough room for both lines.
    """

    _ALIAS_ROLE = Qt.ItemDataRole.UserRole + 1
    _ADDR_ROLE = Qt.ItemDataRole.UserRole + 2

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(option.rect.width() if option.rect.width() > 0 else 200, 50)

    def paint(self, painter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        painter.save()
        try:
            if option.state & QStyle.StateFlag.State_Selected:
                painter.fillRect(option.rect, option.palette.highlight())
            else:
                painter.fillRect(option.rect, option.palette.window())

            alias = index.data(self._ALIAS_ROLE) or index.data(Qt.ItemDataRole.DisplayRole) or ""
            address = index.data(self._ADDR_ROLE) or ""
            r = option.rect
            x, w = r.x() + 8, r.width() - 16

            f1 = QFont()
            f1.setPointSize(12)
            painter.setFont(f1)
            painter.setPen(QColor("#f4f4f5"))
            flags = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            painter.drawText(x, r.y() + 4, w, 22, flags, alias)

            f2 = QFont()
            f2.setPointSize(10)
            painter.setFont(f2)
            painter.setPen(QColor("#a1a1aa"))
            painter.drawText(x, r.y() + 26, w, 20, flags, address)
        finally:
            painter.restore()


class _AdapterRestartBanner(QFrame):
    """Banner prompting user to restart the daemon after an adapter change (tincan-gu24r)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            "_AdapterRestartBanner { background: #431407; border: 1px solid #f97316; }"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(2)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        primary = QLabel("⚠ Adapter saved — a daemon restart is required.")
        pf = QFont()
        pf.setPointSize(12)
        primary.setFont(pf)
        primary.setStyleSheet("color: #fed7aa;")
        primary.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        top_row.addWidget(primary, stretch=1)

        self._restart_btn = QPushButton("Restart Now")
        self._restart_btn.setFixedSize(110, 28)
        self._restart_btn.setStyleSheet(
            "QPushButton { color: #ffffff; background: #f97316;"
            " border: 1px solid #fb923c; border-radius: 4px; }"
            "QPushButton:hover { background: #ea6c0a; }"
        )
        top_row.addWidget(self._restart_btn)

        self._later_btn = QPushButton("Later")
        self._later_btn.setFixedSize(68, 28)
        self._later_btn.setStyleSheet(
            "QPushButton { color: #fed7aa; background: #431407;"
            " border: 1px solid #78350f; border-radius: 4px; }"
            "QPushButton:hover { background: #5c1d0a; }"
        )
        top_row.addWidget(self._later_btn)
        outer.addLayout(top_row)

        secondary = QLabel("Your device will need to reconnect after restart.")
        sf = QFont()
        sf.setPointSize(11)
        secondary.setFont(sf)
        secondary.setStyleSheet("color: #92400e;")
        secondary.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        outer.addWidget(secondary)


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
        self._adapters_list: list[dict] = []

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
            try:
                nf = client.get_notification_filter()
                self._mirror_cb.setChecked(bool(nf.get("enabled", True)))
                self._filter_apps: dict = nf.get("apps", {})
            except Exception:
                self._mirror_cb.setChecked(True)
                self._filter_apps = {}
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

        self._bt_section = QWidget()
        bt_layout = QVBoxLayout(self._bt_section)
        bt_layout.setContentsMargins(0, 0, 0, 0)
        bt_layout.setSpacing(4)

        if self._client:
            # Full interactive picker (only when a daemon client is available)
            bt_label_row = QHBoxLayout()
            bt_adapter_label = QLabel("Bluetooth Adapter")
            bt_adapter_label.setFont(cb_font)
            bt_adapter_label.setStyleSheet("color: #a1a1aa;" if self._dark else "color: #6b7280;")
            bt_adapter_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            bt_label_row.addWidget(bt_adapter_label)
            bt_label_row.addStretch()
            self._refresh_btn = QPushButton("↺ Refresh")
            rf = QFont()
            rf.setPointSize(11)
            self._refresh_btn.setFont(rf)
            self._refresh_btn.setStyleSheet(
                "QPushButton { color: #6366f1; background: transparent; border: none; }"
                "QPushButton:hover { text-decoration: underline; }"
            )
            bt_label_row.addWidget(self._refresh_btn)
            bt_layout.addLayout(bt_label_row)

            # Unavailable frame (shown when get_adapters() returns [])
            self._adapter_unavailable_frame = QFrame()
            self._adapter_unavailable_frame.setStyleSheet(
                "QFrame { background: #1c1c1f; border: 1px solid #27272a; }"
            )
            self._adapter_unavailable_frame.setMinimumHeight(56)
            unavail_layout = QHBoxLayout(self._adapter_unavailable_frame)
            unavail_layout.setContentsMargins(12, 8, 12, 8)
            self._adapter_unavailable_label = QLabel("⚠ Bluetooth service unavailable")
            uf = QFont()
            uf.setPointSize(11)
            self._adapter_unavailable_label.setFont(uf)
            self._adapter_unavailable_label.setStyleSheet("color: #52525b;")
            self._adapter_unavailable_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.NoTextInteraction
            )
            unavail_layout.addWidget(self._adapter_unavailable_label)
            self._adapter_unavailable_frame.hide()
            bt_layout.addWidget(self._adapter_unavailable_frame)

            # Adapter combo (populated async after show)
            self._adapter_combo = QComboBox()
            self._adapter_combo.setPlaceholderText("Loading adapters…")
            self._adapter_combo.setEnabled(False)
            self._adapter_combo.setAccessibleName("Bluetooth Adapter")
            bt_layout.addWidget(self._adapter_combo)

            # Capability badges (shown after load)
            self._adapter_badge_row = QLabel()
            bf2 = QFont()
            bf2.setPointSize(10)
            self._adapter_badge_row.setFont(bf2)
            self._adapter_badge_row.setStyleSheet("color: #a1a1aa;")
            self._adapter_badge_row.hide()
            bt_layout.addWidget(self._adapter_badge_row)

            # Powered-off badge (AC 15: shown when selected adapter is powered off)
            self._adapter_powered_off_badge = QLabel("⏻ Powered off")
            pof = QFont()
            pof.setPointSize(10)
            self._adapter_powered_off_badge.setFont(pof)
            self._adapter_powered_off_badge.setStyleSheet(
                "QLabel { background: #422006; border: 1px solid #d97706;"
                " color: #fbbf24; padding: 2px 6px; border-radius: 4px; }"
            )
            self._adapter_powered_off_badge.setToolTip("This adapter is powered off")
            self._adapter_powered_off_badge.hide()
            bt_layout.addWidget(self._adapter_powered_off_badge)

            # Apply rich two-line delegate (AC 4)
            self._adapter_combo.setItemDelegate(_AdapterItemDelegate(self._adapter_combo))

            # Restart banner (shown after adapter selection change)
            self._adapter_restart_banner = _AdapterRestartBanner()
            self._adapter_restart_banner.hide()
            bt_layout.addWidget(self._adapter_restart_banner)

            # AC6: adapter-mismatch annotation (shown when adapter_warning is set)
            self._adapter_mismatch_annotation = QLabel()
            _ann_font = QFont()
            _ann_font.setPointSize(10)
            self._adapter_mismatch_annotation.setFont(_ann_font)
            self._adapter_mismatch_annotation.setStyleSheet("color: #f59f00;")
            self._adapter_mismatch_annotation.setAccessibleName("wrong adapter detected")
            self._adapter_mismatch_annotation.setTextInteractionFlags(
                Qt.TextInteractionFlag.NoTextInteraction
            )
            self._adapter_mismatch_annotation.hide()
            bt_layout.addWidget(self._adapter_mismatch_annotation)

            # Wire BT picker
            self._adapter_combo.currentIndexChanged.connect(self._on_adapter_changed)
            self._refresh_btn.clicked.connect(self._refresh_adapters)
            self._adapter_restart_banner._later_btn.clicked.connect(
                self._adapter_restart_banner.hide
            )
            self._adapter_restart_banner._restart_btn.clicked.connect(self._on_adapter_restart_now)

            # Async adapter load
            self._loader_thread = _AdapterLoader(self._client)
            self._loader_thread.loaded.connect(self._populate_adapter_combo)
            self._loader_thread.start()
            if self._loader_thread.wait(150):
                QCoreApplication.processEvents()

            # ── Bluetooth Device row ──────────────────────────────────
            bt_layout.addSpacing(4)
            bt_dev_label = QLabel("Bluetooth Device")
            bt_dev_label.setFont(cb_font)
            bt_dev_label.setStyleSheet("color: #a1a1aa;" if self._dark else "color: #6b7280;")
            bt_dev_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            bt_layout.addWidget(bt_dev_label)
            self._device_combo = QComboBox()
            self._device_combo.setPlaceholderText("Loading devices…")
            self._device_combo.setEnabled(False)
            self._device_combo.setAccessibleName("Bluetooth device")
            bt_layout.addWidget(self._device_combo)
            self._device_combo.currentIndexChanged.connect(self._on_device_changed)
            self._device_loader = _DeviceLoader()
            self._device_loader.loaded.connect(self._populate_device_combo)
            self._device_loader.start()
            if self._device_loader.wait(150):
                QCoreApplication.processEvents()

            # AC6: annotate adapter row when adapter_warning is set in daemon status
            try:
                _st = self._client.get_status()
                _warn = str(_st.get("adapter_warning", ""))
            except Exception:
                _warn = ""
            self._refresh_adapter_mismatch_annotation(_warn)
        else:
            # Read-only fallback when no daemon client (legacy / no-D-Bus mode)
            import os as _os  # noqa: PLC0415
            bt_label = QLabel("ANCS Adapter")
            bt_label.setFont(cb_font)
            bt_label.setStyleSheet("color: #a1a1aa;" if self._dark else "color: #6b7280;")
            bt_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            bt_layout.addWidget(bt_label)
            adapter_val = _os.environ.get("TINCAN_ANCS_ADAPTER", "")
            adapter_label = QLabel(adapter_val if adapter_val else "/org/bluez/hci0")
            adapter_label.setFont(cb_font)
            adapter_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            adapter_label.setStyleSheet("color: #a1a1aa;" if self._dark else "color: #6b7280;")
            bt_layout.addWidget(adapter_label)

        layout.addWidget(self._bt_section)
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
            try:
                client.app_notification_received.connect(self._on_app_notification_received)
            except Exception:
                pass

        # Tab order: desktop CB → mirror CB → row Allow/Deny pairs → close-to-tray CB
        self._rebuild_tab_order()

    # ------------------------------------------------------------------
    # App list population / refresh
    # ------------------------------------------------------------------

    def _populate_app_list(self) -> None:
        seen: list[dict] = []
        if self._client:
            try:
                seen = self._client.get_seen_apps()
            except Exception:
                pass
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
            item.setSizeHint(QSize(1, row.sizeHint().height()))  # width=1: viewport width
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
        if hasattr(self, "_adapter_combo"):
            QWidget.setTabOrder(self._close_to_tray_cb, self._refresh_btn)
            QWidget.setTabOrder(self._refresh_btn, self._adapter_combo)
            if hasattr(self, "_device_combo"):
                QWidget.setTabOrder(self._adapter_combo, self._device_combo)

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
            try:
                self._client.set_notifications_enabled(checked)
            except Exception:
                pass

    def _on_close_to_tray_toggled(self, checked: bool) -> None:
        s = app_settings()
        s.setValue("behavior/close_to_tray", checked)
        s.sync()

    @Slot(dict)
    def _on_app_notification_received(self, _payload: dict) -> None:
        self._refresh_app_list()

    # ------------------------------------------------------------------
    # Adapter picker: load, populate, update badges
    # ------------------------------------------------------------------

    def _load_adapters_sync(self) -> None:
        if not self._client:
            return
        try:
            adapters = self._client.get_adapters()
        except Exception:
            adapters = []
        self._populate_adapter_combo(adapters)

    def _populate_adapter_combo(self, adapters: list[dict]) -> None:
        self._adapters_list = adapters

        self._adapter_combo.blockSignals(True)
        self._adapter_combo.clear()

        if not adapters:
            self._adapter_combo.hide()
            self._adapter_badge_row.hide()
            self._adapter_unavailable_frame.show()
            self._refresh_btn.hide()  # AC 13: no Refresh link in BlueZ-unavailable state
            self._bt_section.setEnabled(False)
            self._adapter_combo.blockSignals(False)
            return

        self._adapter_unavailable_frame.hide()
        self._refresh_btn.show()
        self._adapter_combo.show()

        saved_path = None
        try:
            saved_path = app_settings().value("bluetooth/adapter_path", default=None)
        except Exception:
            pass

        selected_idx = 0
        for i, a in enumerate(adapters):
            path = str(a.get("path", ""))
            alias = str(a.get("alias", ""))
            address = str(a.get("address", ""))
            label = f"{alias} ({address})" if alias else path
            self._adapter_combo.addItem(label, path)
            # Store alias and address as separate roles for the rich delegate (AC 4)
            self._adapter_combo.setItemData(i, alias, Qt.ItemDataRole.UserRole + 1)
            self._adapter_combo.setItemData(i, address, Qt.ItemDataRole.UserRole + 2)
            # Per-item accessible text (AC 8)
            hfp = a.get("hfp_sco_capable")
            hfp_text = "capable" if (hfp is True or hfp == "yes") else (
                "incapable" if (hfp is False or hfp == "no") else "unknown"
            )
            le = a.get("le_capable")
            le_text = "capable" if (le is True or le == "yes") else "incapable"
            hci = path.split("/")[-1] if path else ""
            a11y_text = (
                f"{hci} — {alias}, HFP call audio {hfp_text}, LE advertising {le_text}"
            )
            self._adapter_combo.setItemData(i, a11y_text, Qt.ItemDataRole.AccessibleTextRole)
            if a.get("is_selected") or (saved_path and path == saved_path):
                selected_idx = i

        self._adapter_combo.setCurrentIndex(selected_idx)
        self._adapter_combo.blockSignals(False)

        single = len(adapters) == 1
        if not single:
            self._adapter_combo.setEnabled(True)
            self._adapter_badge_row.setGraphicsEffect(None)
        else:
            self._adapter_combo.setEnabled(False)
            self._adapter_combo.setAccessibleDescription("Only one adapter available")
            # AC 14: badge row at 60% opacity for single-adapter case
            effect = QGraphicsOpacityEffect()
            effect.setOpacity(0.6)
            self._adapter_badge_row.setGraphicsEffect(effect)

        selected = adapters[selected_idx] if adapters else None
        self._update_adapter_badges(selected)

    def _update_adapter_badges(self, adapter: dict | None) -> None:
        if adapter is None:
            self._adapter_badge_row.hide()
            self._adapter_powered_off_badge.hide()
            return

        hfp = adapter.get("hfp_sco_capable")
        if hfp is True or hfp == "yes":
            hfp_glyph = "✓"
        elif hfp is False or hfp == "no":
            hfp_glyph = "✗"
        else:
            hfp_glyph = "?"

        le = adapter.get("le_capable")
        le_glyph = "✓" if (le is True or le == "yes") else "✗"

        self._adapter_badge_row.setText(
            f"{hfp_glyph} HFP call audio    {le_glyph} LE advertising"
        )
        self._adapter_badge_row.show()

        # AC 15: powered-off badge
        if adapter.get("powered") is False:
            self._adapter_powered_off_badge.show()
        else:
            self._adapter_powered_off_badge.hide()

    @Slot(int)
    def _on_adapter_changed(self, index: int) -> None:
        if index < 0 or not self._adapters_list:
            return
        path = self._adapter_combo.itemData(index, Qt.ItemDataRole.UserRole)
        if not path:
            return
        try:
            s = app_settings()
            s.setValue("bluetooth/adapter_path", path)
            s.sync()
        except Exception:
            pass
        self._adapter_restart_banner.show()
        self._adapter_restart_banner._restart_btn.setFocus()
        if index < len(self._adapters_list):
            self._update_adapter_badges(self._adapters_list[index])

    def _populate_device_combo(self, devices: list[dict]) -> None:
        self._device_combo.blockSignals(True)
        self._device_combo.clear()
        self._device_combo.addItem("Auto-discover (recommended)", "")
        self._device_combo.setItemData(
            0, "Auto-discover Bluetooth device (recommended)", Qt.ItemDataRole.AccessibleTextRole
        )
        for i, d in enumerate(devices, 1):
            mac = d.get("mac", "")
            name = d.get("name", "")
            label = f"{mac} ({name})" if name else mac
            self._device_combo.addItem(label, mac)
        saved_mac = ""
        try:
            from tincand.config import DaemonSettings  # noqa: PLC0415

            saved_mac = str(DaemonSettings().value("bluetooth/device_address", "") or "")
        except Exception:  # noqa: BLE001
            pass
        selected_idx = 0
        if saved_mac:
            for i in range(self._device_combo.count()):
                if self._device_combo.itemData(i, Qt.ItemDataRole.UserRole) == saved_mac:
                    selected_idx = i
                    break
            else:
                self._device_combo.addItem(saved_mac, saved_mac)
                selected_idx = self._device_combo.count() - 1
        self._device_combo.setCurrentIndex(selected_idx)
        self._device_combo.setEnabled(True)
        self._device_combo.blockSignals(False)

    @Slot(int)
    def _on_device_changed(self, index: int) -> None:
        if index < 0:
            return
        mac = self._device_combo.itemData(index, Qt.ItemDataRole.UserRole) or ""
        try:
            from tincand.config import DaemonSettings  # noqa: PLC0415

            s = DaemonSettings()
            s.setValue("bluetooth/device_address", mac)
            s.sync()
        except Exception:  # noqa: BLE001
            pass

    def _refresh_adapter_mismatch_annotation(self, warning: str) -> None:
        """AC6: show/hide ⚠ annotation on the Adapter row when adapter_warning is set."""
        if not hasattr(self, "_adapter_mismatch_annotation"):
            return
        if not warning:
            self._adapter_mismatch_annotation.hide()
            return
        import re  # noqa: PLC0415
        m = re.search(r"\(([^)]+)\) for call audio", warning)
        wanted = m.group(1) if m else "see warning above"
        self._adapter_mismatch_annotation.setText(f"⚠ (wanted: {wanted})")
        self._adapter_mismatch_annotation.show()

    def _refresh_adapters(self) -> None:
        self._adapter_combo.setEnabled(False)
        self._adapter_combo.setPlaceholderText("Loading adapters…")
        if self._client:
            self._loader_thread = _AdapterLoader(self._client)
            self._loader_thread.loaded.connect(self._populate_adapter_combo)
            self._loader_thread.start()

    def _on_adapter_restart_now(self) -> None:
        backend = ""
        device = ""
        try:
            status = self._client.get_status() if self._client else {}
            backend = status.get("backend", "")
            device = status.get("device_address", "")
        except Exception:
            pass
        self._sigterm_daemon()
        spawn_daemon(backend, device)
        self.close()

    def _sigterm_daemon(self) -> None:
        import signal as _signal  # noqa: PLC0415
        try:
            import dbus as _dbus  # noqa: PLC0415
            _bus = _dbus.SessionBus()
            pid = int(
                _dbus.Interface(
                    _bus.get_object("org.freedesktop.DBus", "/org/freedesktop/DBus"),
                    "org.freedesktop.DBus",
                ).GetConnectionUnixProcessID("im.tincan.Daemon")
            )
            os.kill(pid, _signal.SIGTERM)
        except Exception:
            pass

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
