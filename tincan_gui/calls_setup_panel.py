"""tincan_gui/calls_setup_panel.py — Calls prerequisites setup dialog (tincan-lqj89.2)."""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAccessible, QAccessibleEvent, QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from tincan_gui.pairing_wizard import _DetectBadge

_RTL8761B_VID_PID = "0b05:1bf6"

_STEP_B_CONF_PATH = "~/.config/wireplumber/wireplumber.conf.d/50-bluez-ofono.conf"
_STEP_B_CONF_CONTENT = (
    "wireplumber.settings = {\n"
    '  bluez5.hfphsp-backend = "ofono"\n'
    "}"
)
_STEP_B_RESTART_CMD = "systemctl --user restart wireplumber"

_STEP_A_INSTALL_CMD = "sudo dnf install ofono && sudo systemctl enable --now ofono"

_STEP_C_INSTALL_CMD = "cd packaging/selinux && sudo ./install.sh"
_STEP_C_REINSTALL_CMD = "sudo dnf reinstall tincan"

_STEP_D_UDEV_CMD = "sudo udevadm control --reload\nsudo udevadm trigger"


def _emit_accessible_event(widget: QWidget) -> None:
    event = QAccessibleEvent(widget, QAccessible.Event.DescriptionChanged)
    QAccessible.updateAccessibility(event)


def _code_block(text: str, parent: Optional[QWidget] = None) -> QLabel:
    label = QLabel(text, parent)
    label.setStyleSheet(
        "background-color: #1c1c1f; border: 1px solid #3f3f46; border-radius: 4px; "
        "font-family: Monospace; font-size: 10px; padding: 8px;"
    )
    label.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse
        | Qt.TextInteractionFlag.TextSelectableByKeyboard
    )
    label.setWordWrap(True)
    return label


class _CallsStepRow(QFrame):
    """Prerequisite step row: badge + name, status icon, optional instruction + code blocks."""

    def __init__(
        self,
        name: str,
        *,
        header_note: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            "QFrame { background-color: #27272a; border: 1px solid #3f3f46; border-radius: 6px; }"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(6)

        # Header: badge + step name
        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        hdr.addWidget(_DetectBadge("AUTO"))
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            "color: #f4f4f5; font-size: 13px; font-weight: bold; border: none;"
        )
        hdr.addWidget(name_lbl)
        hdr.addStretch()
        outer.addLayout(hdr)

        if header_note:
            note_lbl = QLabel(header_note)
            note_lbl.setStyleSheet(
                "color: #d97706; font-size: 11px; border: none;"
            )
            note_lbl.setWordWrap(True)
            outer.addWidget(note_lbl)

        # Status label
        self._status_label = QLabel("⟳ Checking…")
        self._status_label.setStyleSheet("color: #a1a1aa; font-size: 13px; border: none;")
        outer.addWidget(self._status_label)

        # Detail area: shown on failure or neutral states
        self._detail = QWidget()
        self._detail_layout = QVBoxLayout(self._detail)
        self._detail_layout.setContentsMargins(0, 4, 0, 0)
        self._detail_layout.setSpacing(6)
        self._detail.setVisible(False)
        outer.addWidget(self._detail)

        # Extra instruction injected at update time (e.g. Step A's WP warning)
        self._extra_label: Optional[QLabel] = None

    # ------------------------------------------------------------------
    # Builder helpers — called once at construction to pre-fill detail area
    # ------------------------------------------------------------------

    def _add_instruction(self, text: str) -> None:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #9ca3af; font-size: 11px; border: none;")
        lbl.setWordWrap(True)
        self._detail_layout.addWidget(lbl)

    def _add_code(self, code: str) -> None:
        self._detail_layout.addWidget(_code_block(code))

    def _add_extra_slot(self) -> None:
        """Reserve a labelled slot for runtime-injected text (e.g. cross-step warnings)."""
        self._extra_label = QLabel("")
        self._extra_label.setStyleSheet("color: #d97706; font-size: 11px; border: none;")
        self._extra_label.setWordWrap(True)
        self._extra_label.setVisible(False)
        self._detail_layout.insertWidget(0, self._extra_label)

    # ------------------------------------------------------------------
    # Runtime state methods
    # ------------------------------------------------------------------

    def set_checking(self) -> None:
        self._status_label.setText("⟳ Checking…")
        self._status_label.setStyleSheet("color: #a1a1aa; font-size: 13px; border: none;")
        self._detail.setVisible(False)
        if self._extra_label:
            self._extra_label.setVisible(False)
        _emit_accessible_event(self)

    def set_neutral(self, text: str, *, color: str = "#6b7280") -> None:
        self._status_label.setText(text)
        self._status_label.setStyleSheet(
            f"color: {color}; font-size: 13px; border: none;"
        )
        self._detail.setVisible(False)
        if self._extra_label:
            self._extra_label.setVisible(False)
        _emit_accessible_event(self)

    def set_result(self, ok: bool, instruction: str = "") -> None:
        if ok:
            self._status_label.setText("✓ Done")
            self._status_label.setStyleSheet(
                "color: #16a34a; font-size: 13px; border: none;"
            )
            self._detail.setVisible(False)
            if self._extra_label:
                self._extra_label.setVisible(False)
        else:
            self._status_label.setText("✗ Action required")
            self._status_label.setStyleSheet(
                "color: #dc2626; font-size: 13px; border: none;"
            )
            if self._extra_label and instruction:
                self._extra_label.setText(instruction)
                self._extra_label.setVisible(True)
            self._detail.setVisible(True)
        _emit_accessible_event(self)


class _CallsSuccessCard(QFrame):
    """Green summary card shown when all 4 steps pass."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            "QFrame { background-color: #14532d; border: 1px solid #16a34a; border-radius: 6px; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        lbl = QLabel(
            "✓ Phone calls are set up and ready to use.\n"
            "   Dial buttons are now active in tincan.\n"
            "   Return to the main window to make your first call."
        )
        lbl.setStyleSheet("color: #f0fdf4; font-size: 13px; border: none;")
        lbl.setWordWrap(True)
        layout.addWidget(lbl)
        self._label = lbl

    def showEvent(self, event) -> None:
        super().showEvent(event)
        _emit_accessible_event(self)


def _build_step_b() -> _CallsStepRow:
    row = _CallsStepRow(
        "Step B: WirePlumber oFono backend",
        header_note="⚠ Complete this before enabling oFono (Step A)",
    )
    row._add_instruction(
        "WirePlumber oFono HFP backend is not configured.\n"
        "Do this BEFORE starting oFono:"
    )
    row._add_instruction(f"1. Edit (create if needed):\n   {_STEP_B_CONF_PATH}\n\n   Add:")
    row._add_code(_STEP_B_CONF_CONTENT)
    row._add_instruction("2. Restart WirePlumber:")
    row._add_code(_STEP_B_RESTART_CMD)
    return row


def _build_step_a() -> _CallsStepRow:
    row = _CallsStepRow("Step A: oFono service")
    row._add_extra_slot()
    row._add_instruction("oFono is not installed or not running.\n\nInstall and enable:")
    row._add_code(_STEP_A_INSTALL_CMD)
    return row


def _build_step_c() -> _CallsStepRow:
    row = _CallsStepRow("Step C: SELinux policy module")
    row._add_instruction(
        "The tincan_hfp_sco SELinux policy is not loaded.\n"
        "Without it, call audio is silently blocked under SELinux Enforcing mode.\n\n"
        "Install:"
    )
    row._add_code(_STEP_C_INSTALL_CMD)
    row._add_instruction("Or if you installed from an RPM, reinstall the package:")
    row._add_code(_STEP_C_REINSTALL_CMD)
    return row


def _build_step_d() -> _CallsStepRow:
    row = _CallsStepRow("Step D: USB autosuspend (RTL8761B only)")
    row._add_instruction(
        "USB autosuspend is enabled for the ASUS USB-BT500 adapter.\n"
        "This causes corrupted SCO packet errors during calls. "
        "tincan installs a udev rule to fix this automatically.\n\n"
        "Reload udev rules:"
    )
    row._add_code(_STEP_D_UDEV_CMD)
    row._add_instruction(
        "If the issue persists after reloading udev, disable temporarily:"
    )
    row._add_code(
        "echo on > /sys/bus/usb/devices/"
        "$(cat /sys/class/bluetooth/hci1/device/uevent"
        " | grep DEVPATH | cut -d/ -f2-7)/power/control"
    )
    return row


class CallsSetupPanel(QDialog):
    """4-step guided calls prerequisites dialog (tincan-lqj89.2).

    Opens from SuccessPage and CallSetupRequiredBanner.
    Calls dbus_client.preflight_calls(callback) and renders 4 step rows.
    """

    def __init__(
        self,
        dbus_client,
        *,
        adapter_vid_pid: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.WindowTitleHint)
        self.setWindowTitle("Phone Calls Setup")
        self.setFixedSize(520, 520)
        self.setStyleSheet("background-color: #18181b;")
        self._client = dbus_client
        self._adapter_vid_pid = adapter_vid_pid
        self._build()
        if parent:
            self.move(
                parent.geometry().center() - self.rect().center()
            )
        self._recheck()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(0)

        # Title + subtitle
        title = QLabel("Phone Calls Setup")
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        title.setFont(font)
        title.setStyleSheet("color: #f4f4f5;")
        outer.addWidget(title)

        subtitle = QLabel("Set up these 4 items to enable HFP phone calls.")
        subtitle.setStyleSheet("color: #a1a1aa; font-size: 12px;")
        outer.addSpacing(4)
        outer.addWidget(subtitle)
        outer.addSpacing(12)

        # Re-check button
        self._recheck_btn = QPushButton("↺  Re-check all")
        self._recheck_btn.setStyleSheet(
            "QPushButton { background-color: transparent; color: #0d9488; "
            "border: 1px solid #0d9488; border-radius: 4px; "
            "font-size: 12px; padding: 4px 12px; }"
        )
        self._recheck_btn.setFixedHeight(32)
        self._recheck_btn.setAccessibleName("Re-check all steps")
        self._recheck_btn.clicked.connect(self._recheck)
        outer.addWidget(self._recheck_btn)
        outer.addSpacing(12)

        # Scrollable step area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        step_layout = QVBoxLayout(scroll_content)
        step_layout.setContentsMargins(0, 0, 0, 0)
        step_layout.setSpacing(8)

        # Build rows in visual order: B, A, C, D
        self._step_b = _build_step_b()
        self._step_a = _build_step_a()
        self._step_c = _build_step_c()
        self._step_d = _build_step_d()

        for row in (self._step_b, self._step_a, self._step_c, self._step_d):
            step_layout.addWidget(row)

        self._success_card = _CallsSuccessCard()
        self._success_card.hide()
        step_layout.addWidget(self._success_card)
        step_layout.addStretch()

        scroll.setWidget(scroll_content)
        outer.addWidget(scroll, stretch=1)
        outer.addSpacing(8)

        # Close button (always visible)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(
            "QPushButton { background-color: #3f3f46; color: #a1a1aa; "
            "font-size: 14px; border-radius: 4px; border: none; }"
        )
        close_btn.setFixedHeight(40)
        close_btn.clicked.connect(self.accept)
        outer.addWidget(close_btn)

    def _recheck(self) -> None:
        for row in (self._step_b, self._step_a, self._step_c, self._step_d):
            row.set_checking()
        self._success_card.hide()
        self._client.preflight_calls(self._on_preflight_result)

    def _on_preflight_result(self, result: dict) -> None:
        wp_ok = bool(result.get("wireplumber_ofono_backend", False))
        ofono_ok = bool(result.get("ofono_available", False))
        selinux = result.get("selinux_hfp_module", False)
        usb_ok = bool(result.get("usb_autosuspend_disabled", False))
        vid_pid = str(result.get("adapter_vid_pid", self._adapter_vid_pid))

        # Step B: WirePlumber
        if wp_ok:
            self._step_b.set_result(True)
        else:
            self._step_b.set_result(False)

        # Step A: oFono — inject warning when B not done
        if ofono_ok:
            self._step_a.set_result(True)
        else:
            wp_warning = (
                "⚠ Complete Step B (WirePlumber) before starting oFono, "
                "or oFono will claim the HFP profile slot first."
                if not wp_ok
                else ""
            )
            self._step_a.set_result(False, wp_warning)

        # Step C: SELinux
        if selinux == "permissive":
            self._step_c.set_neutral(
                "ℹ SELinux is in Permissive mode — policy not required, calls should work."
            )
        elif selinux:
            self._step_c.set_result(True)
        else:
            self._step_c.set_result(False)

        # Step D: USB autosuspend (conditional on adapter)
        if vid_pid != _RTL8761B_VID_PID:
            self._step_d.set_neutral(
                "✓ Not applicable — this adapter does not require USB autosuspend management.",
                color="#a1a1aa",
            )
        elif usb_ok:
            self._step_d.set_result(True)
        else:
            self._step_d.set_result(False)

        # Success card: all 4 checks pass
        # Step D passes if not RTL8761B (N/A) or if autosuspend disabled
        step_d_pass = vid_pid != _RTL8761B_VID_PID or usb_ok
        selinux_pass = bool(selinux)
        all_pass = wp_ok and ofono_ok and selinux_pass and step_d_pass
        if all_pass:
            self._success_card.show()
        else:
            self._success_card.hide()
