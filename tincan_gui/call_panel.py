"""Phone call UI widgets: incoming dialog, in-call panel, DTMF keypad, audio error.

No D-Bus wiring — all classes emit signals only. Callers in main.py connect
signals to the actual D-Bus client methods.
"""
from __future__ import annotations

import dataclasses

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tincan_gui.avatar import AvatarWidget


@dataclasses.dataclass
class CallEntry:
    """Snapshot of a single call's display state for MultiCallPanel."""

    call_id: str
    name: str
    avatar_pixmap: QPixmap | None
    state: str  # "active" | "held" | "waiting"
    elapsed: int = 0  # seconds; used to seed the active-call timer on first show

_DTMF_KEYS = [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"], ["*", "0", "#"]]

_STATE_PILL: dict[str, tuple[str, str]] = {
    "active": ("● ACTIVE", "#0d9488"),
    "held": ("⏸ HELD", "#d97706"),
    "waiting": ("⏳ WAITING", "#6366f1"),
}
_BORDER_COLOR: dict[str, str] = {
    "active": "#0d9488",
    "held": "#d97706",
    "waiting": "#6366f1",
}


class IncomingCallDialog(QDialog):
    """Semi-modal dialog shown when an HFP call arrives (tincan-fx79v)."""

    answered = Signal()
    declined = Signal()

    def __init__(
        self,
        caller_name: str,
        caller_number: str,
        avatar_pixmap: QPixmap | None,
        parent: QWidget,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.WindowTitleHint)
        self.setWindowTitle("Incoming Call")
        self.setStyleSheet("background: #18181b; color: #f4f4f5;")
        self.setFixedSize(340, 290)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 24, 16, 16)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        avatar = AvatarWidget(caller_name, size=68)
        if avatar_pixmap:
            avatar.set_photo_pixmap(avatar_pixmap)
        layout.addWidget(avatar, alignment=Qt.AlignmentFlag.AlignHCenter)

        name_lbl = QLabel(caller_name or caller_number)
        name_lbl.setObjectName("callerName")
        name_lbl.setStyleSheet("color: #f4f4f5; font-size: 20px; font-weight: 500;")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name_lbl)

        if caller_name:
            num_lbl = QLabel(caller_number)
            num_lbl.setStyleSheet("color: #9ca3af; font-size: 13px;")
            num_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(num_lbl)

        status_lbl = QLabel("Incoming call via HFP…")
        status_lbl.setStyleSheet("color: #6b7280; font-size: 11px;")
        status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(status_lbl)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self._decline_btn = QPushButton("✕  Decline")
        self._decline_btn.setFixedHeight(44)
        self._decline_btn.setStyleSheet(
            "QPushButton { background: #dc2626; color: #ffffff; border: none;"
            " font-size: 14px; border-radius: 4px; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; outline-offset: 2px; }"
        )
        self._decline_btn.clicked.connect(self._on_decline)

        self._answer_btn = QPushButton("✓  Answer")
        self._answer_btn.setFixedHeight(44)
        self._answer_btn.setStyleSheet(
            "QPushButton { background: #16a34a; color: #ffffff; border: none;"
            " font-size: 14px; border-radius: 4px; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; outline-offset: 2px; }"
        )
        self._answer_btn.setDefault(True)
        self._answer_btn.clicked.connect(self._on_answer)

        btn_row.addWidget(self._decline_btn)
        btn_row.addWidget(self._answer_btn)
        layout.addLayout(btn_row)

        self.move(
            parent.geometry().center() - self.rect().center()
        )

    def _on_decline(self) -> None:
        self.declined.emit()
        self.reject()

    def _on_answer(self) -> None:
        self.answered.emit()
        self.accept()

    def disable_answer(self, reason: str) -> None:
        """Disable the Answer button (e.g. call_setup_ready=False) with tooltip."""
        self._answer_btn.setEnabled(False)
        self._answer_btn.setToolTip(reason)
        self._answer_btn.setAccessibleDescription(reason)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._on_decline()
        else:
            super().keyPressEvent(event)


class InCallPanel(QWidget):
    """In-call control bar (88px) that replaces the compose bar (tincan-fx79v)."""

    hang_up_requested = Signal()
    keypad_toggled = Signal(bool)

    def __init__(
        self,
        caller_name: str,
        avatar_pixmap: QPixmap | None,
        parent: QWidget,
        elapsed_offset: int = 0,
    ) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: #18181b; border-top: 2px solid #0d9488;")
        self.setFixedHeight(88)
        self._elapsed = elapsed_offset
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(8)

        avatar = AvatarWidget(caller_name, size=44)
        if avatar_pixmap:
            avatar.set_photo_pixmap(avatar_pixmap)
        row.addWidget(avatar)

        info_col = QVBoxLayout()
        info_col.setSpacing(0)
        name_lbl = QLabel(f"On call with {caller_name}")
        name_lbl.setStyleSheet("color: #f4f4f5; font-size: 13px;")
        info_col.addWidget(name_lbl)
        self._timer_lbl = QLabel("0:00:00")
        self._timer_lbl.setStyleSheet("color: #86efac; font-size: 20px; font-weight: 500;")
        self._timer_lbl.setAccessibleName("Call duration")
        info_col.addWidget(self._timer_lbl)
        row.addLayout(info_col)
        row.addStretch()

        self._keypad_btn = QPushButton("⌨ Keypad")
        self._keypad_btn.setFixedSize(104, 38)
        self._keypad_btn.setStyleSheet(
            "QPushButton { background: #27272a; color: #9ca3af; border: 1px solid #3f3f46;"
            " font-size: 12px; border-radius: 4px; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; }"
        )
        self._keypad_btn.setCheckable(True)
        self._keypad_btn.toggled.connect(self.keypad_toggled)
        row.addWidget(self._keypad_btn)

        hang_btn = QPushButton("✕ Hang Up")
        hang_btn.setFixedSize(108, 38)
        hang_btn.setStyleSheet(
            "QPushButton { background: #dc2626; color: #ffffff; border: none;"
            " font-size: 13px; border-radius: 4px; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; }"
        )
        hang_btn.clicked.connect(self.hang_up_requested)
        row.addWidget(hang_btn)

    def _tick(self) -> None:
        self._elapsed += 1
        h, rem = divmod(self._elapsed, 3600)
        m, s = divmod(rem, 60)
        self._timer_lbl.setText(f"{h}:{m:02d}:{s:02d}")

    @property
    def elapsed(self) -> int:
        return self._elapsed

    def set_keypad_checked(self, state: bool) -> None:
        self._keypad_btn.setChecked(state)


class DTMFKeypad(QWidget):
    """4×3 DTMF key grid with tone display (tincan-fx79v stretch goal)."""

    tone_pressed = Signal(str)
    close_requested = Signal()   # emitted on Escape; callers should hide or page-switch

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: #18181b; border: 2px solid #3f3f46;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        self._display = QLineEdit()
        self._display.setReadOnly(True)
        self._display.setStyleSheet(
            "background: #27272a; color: #f4f4f5; border: 1px solid #3f3f46;"
            " font-size: 16px; padding: 4px 8px;"
        )
        self._display.setAccessibleName("DTMF input")
        layout.addWidget(self._display)

        grid = QGridLayout()
        grid.setSpacing(8)
        for row, keys in enumerate(_DTMF_KEYS):
            for col, key in enumerate(keys):
                btn = QPushButton(key)
                btn.setFixedSize(60, 44)
                btn.setStyleSheet(
                    "QPushButton { background: #27272a; color: #f4f4f5;"
                    " border: 1px solid #3f3f46; font-size: 18px; border-radius: 4px; }"
                    " QPushButton:hover { background: #3f3f46; }"
                    " QPushButton:focus { outline: 2px dashed #3b82f6; }"
                )
                btn.setAccessibleName(f"DTMF {key}")
                btn.clicked.connect(lambda _, k=key: self._on_key(k))
                grid.addWidget(btn, row, col)
        layout.addLayout(grid)

    def _on_key(self, key: str) -> None:
        self._display.setText(self._display.text() + key)
        self.tone_pressed.emit(key)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close_requested.emit()
        else:
            super().keyPressEvent(event)


class AudioErrorPanel(QWidget):
    """88px panel shown when HFP audio SCO channel fails (tincan-fx79v)."""

    hang_up_requested = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: #18181b; border-top: 2px solid #d97706;")
        self.setFixedHeight(88)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(12)

        warn = QLabel("⚠")
        warn.setStyleSheet("color: #d97706; font-size: 32px; border: none;")
        warn.setAccessibleName("")
        row.addWidget(warn)

        msg_col = QVBoxLayout()
        title = QLabel("Audio unavailable")
        title.setStyleSheet("color: #f4f4f5; font-size: 14px; font-weight: 500;")
        msg_col.addWidget(title)
        body = QLabel("HFP audio path could not be established. Call is still connected.")
        body.setStyleSheet("color: #9ca3af; font-size: 11px;")
        msg_col.addWidget(body)
        row.addLayout(msg_col)
        row.addStretch()

        hang_btn = QPushButton("✕ Hang Up")
        hang_btn.setFixedSize(108, 30)
        hang_btn.setStyleSheet(
            "QPushButton { background: #dc2626; color: #ffffff; border: none;"
            " font-size: 11px; border-radius: 4px; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; }"
        )
        hang_btn.clicked.connect(self.hang_up_requested)
        row.addWidget(hang_btn)


def _fmt_elapsed(secs: int) -> str:
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}"


class CallWaitingDialog(QDialog):
    """Overlay dialog shown when a second call arrives while one is active."""

    hold_and_answer_requested = Signal()
    release_and_answer_requested = Signal()
    declined = Signal()

    def __init__(
        self,
        waiting_name: str,
        waiting_number: str,
        active_name: str,
        active_elapsed: int,
        parent: QWidget,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.WindowTitleHint)
        self.setWindowTitle("Call Waiting")
        self.setStyleSheet("background: #18181b; color: #f4f4f5;")
        self.setFixedSize(360, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        waiting_avatar = AvatarWidget(waiting_name, size=76)
        layout.addWidget(waiting_avatar, alignment=Qt.AlignmentFlag.AlignHCenter)

        waiting_name_lbl = QLabel(waiting_name or waiting_number)
        waiting_name_lbl.setStyleSheet("color: #f4f4f5; font-size: 18px; font-weight: 500;")
        waiting_name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(waiting_name_lbl)

        if waiting_name:
            waiting_num_lbl = QLabel(waiting_number)
            waiting_num_lbl.setStyleSheet("color: #9ca3af; font-size: 12px;")
            waiting_num_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(waiting_num_lbl)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #3f3f46;")
        layout.addWidget(divider)

        active_lbl = QLabel("Currently on call with:")
        active_lbl.setStyleSheet("color: #9ca3af; font-size: 11px;")
        active_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(active_lbl)

        active_row_frame = QFrame()
        active_row_frame.setStyleSheet(
            "QFrame { background: #27272a; border-left: 2px solid #0d9488;"
            " border-radius: 4px; }"
        )
        active_inner = QHBoxLayout(active_row_frame)
        active_inner.setContentsMargins(8, 6, 8, 6)
        active_inner.setSpacing(8)

        active_avatar = AvatarWidget(active_name, size=32)
        active_inner.addWidget(active_avatar)

        active_name_lbl = QLabel(active_name)
        active_name_lbl.setStyleSheet("color: #f4f4f5; font-size: 12px;")
        active_inner.addWidget(active_name_lbl)

        active_inner.addStretch()

        self._active_elapsed = active_elapsed
        self._active_timer_lbl = QLabel(_fmt_elapsed(active_elapsed))
        self._active_timer_lbl.setStyleSheet("color: #86efac; font-size: 12px;")
        self._active_timer_lbl.setAccessibleName("Call duration")
        active_inner.addWidget(self._active_timer_lbl)

        layout.addWidget(active_row_frame)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick_active)
        self._timer.start()

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._hold_btn = QPushButton("⏸  Hold & Answer")
        self._hold_btn.setFixedHeight(40)
        self._hold_btn.setAccessibleName("Hold current call and answer waiting call")
        self._hold_btn.setStyleSheet(
            "QPushButton { background: #16a34a; color: #ffffff; border: none;"
            " font-size: 13px; border-radius: 4px; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; outline-offset: 2px; }"
        )
        self._hold_btn.clicked.connect(self._on_hold_and_answer)
        btn_row.addWidget(self._hold_btn)

        self._release_btn = QPushButton("✕  Release & Answer")
        self._release_btn.setFixedHeight(40)
        self._release_btn.setAccessibleName("End current call and answer waiting call")
        self._release_btn.setStyleSheet(
            "QPushButton { background: #dc2626; color: #ffffff; border: none;"
            " font-size: 13px; border-radius: 4px; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; outline-offset: 2px; }"
        )
        self._release_btn.clicked.connect(self._on_release_and_answer)
        btn_row.addWidget(self._release_btn)
        layout.addLayout(btn_row)

        self._decline_btn = QPushButton("Decline")
        self._decline_btn.setFixedHeight(32)
        self._decline_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #9ca3af;"
            " border: 1px solid #3f3f46; font-size: 12px; border-radius: 4px; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; outline-offset: 2px; }"
        )
        self._decline_btn.clicked.connect(self._on_decline)
        layout.addWidget(self._decline_btn)

        self.setTabOrder(self._hold_btn, self._release_btn)
        self.setTabOrder(self._release_btn, self._decline_btn)

        self.move(parent.geometry().center() - self.rect().center())

    def _tick_active(self) -> None:
        self._active_elapsed += 1
        self._active_timer_lbl.setText(_fmt_elapsed(self._active_elapsed))

    def _on_hold_and_answer(self) -> None:
        self.hold_and_answer_requested.emit()
        self.accept()

    def _on_release_and_answer(self) -> None:
        self.release_and_answer_requested.emit()
        self.accept()

    def _on_decline(self) -> None:
        self.declined.emit()
        self.reject()

    def reject(self) -> None:
        self.declined.emit()
        super().reject()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key.Key_H:
            self._on_hold_and_answer()
        elif key == Qt.Key.Key_R:
            self._on_release_and_answer()
        elif key == Qt.Key.Key_Escape:
            self._on_decline()
        else:
            super().keyPressEvent(event)


class MultiCallPanel(InCallPanel):
    """Extends InCallPanel to handle 1–2 simultaneous HFP calls (tincan-nd6pt).

    Height: 88px with 1 call, 132px with 2 calls (two 54px rows + 24px strip).
    """

    # Override signals — hang_up gains call_id; swap/end-all/waiting-action are new
    hang_up_requested = Signal(str)  # call_id
    swap_requested = Signal()
    end_all_requested = Signal()
    hold_and_answer_requested = Signal()
    release_and_answer_requested = Signal()
    decline_waiting_requested = Signal()
    # keypad_toggled(bool) inherited from InCallPanel

    def __init__(self, parent: QWidget) -> None:
        # Bypass InCallPanel.__init__ — layout is completely different
        QWidget.__init__(self, parent)
        self.setStyleSheet("background: #18181b; border-top: 2px solid #0d9488;")
        self.setFixedHeight(88)

        self._entries: list[CallEntry] = []
        self._active_timer: QTimer | None = None
        self._active_elapsed: int = 0
        self._timer_lbl: QLabel | None = None
        self._keypad_btn: QPushButton | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._rows_widget = QWidget(self)
        self._rows_layout = QVBoxLayout(self._rows_widget)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(0)
        outer.addWidget(self._rows_widget)

        self._strip = QWidget(self)
        self._strip.setFixedHeight(24)
        self._strip.setStyleSheet("background: #1c1c1f; border-top: 1px solid #3f3f46;")
        strip_layout = QHBoxLayout(self._strip)
        strip_layout.setContentsMargins(12, 1, 12, 1)
        strip_layout.setSpacing(8)

        self._swap_btn = QPushButton("⇄ Swap Calls")
        self._swap_btn.setFixedSize(110, 20)
        self._swap_btn.setStyleSheet(
            "QPushButton { background: #27272a; color: #9ca3af; border: 1px solid #3f3f46;"
            " font-size: 10px; border-radius: 3px; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; }"
        )
        self._swap_btn.clicked.connect(self.swap_requested)
        self._swap_btn.hide()
        strip_layout.addWidget(self._swap_btn)

        strip_layout.addStretch()

        self._end_all_btn = QPushButton("End All Calls")
        self._end_all_btn.setFixedSize(90, 20)
        self._end_all_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #9ca3af;"
            " border: 1px solid #3f3f46; font-size: 10px; border-radius: 3px; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; }"
        )
        self._end_all_btn.clicked.connect(self.end_all_requested)
        self._end_all_btn.hide()
        strip_layout.addWidget(self._end_all_btn)

        self._strip.hide()
        outer.addWidget(self._strip)

    def update_calls(self, entries: list[CallEntry]) -> None:
        """Refresh the panel to reflect the current call states."""
        if self._active_timer is not None:
            self._active_timer.stop()
            self._active_timer = None
        self._timer_lbl = None
        self._keypad_btn = None

        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._entries = list(entries)
        n = len(entries)
        row_height = 88 if n <= 1 else 54

        for entry in entries:
            self._rows_layout.addWidget(self._make_row(entry, row_height))

        has_held = any(e.state == "held" for e in entries)
        has_active = any(e.state == "active" for e in entries)
        self._swap_btn.setVisible(has_held and has_active)
        self._end_all_btn.setVisible(n >= 2)

        if n >= 2:
            self._strip.show()
            self.setFixedHeight(132)
        else:
            self._strip.hide()
            self.setFixedHeight(88)

        active_list = [e for e in entries if e.state == "active"]
        if active_list:
            self._active_elapsed = active_list[0].elapsed
            self._active_timer = QTimer(self)
            self._active_timer.setInterval(1000)
            self._active_timer.timeout.connect(self._tick_active)
            self._active_timer.start()

    def _make_row(self, entry: CallEntry, height: int) -> QWidget:
        border = _BORDER_COLOR.get(entry.state, "#3f3f46")
        row = QWidget(self._rows_widget)
        row.setFixedHeight(height)
        row.setStyleSheet(
            f"QWidget {{ background: #18181b; border-left: 4px solid {border}; }}"
        )
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 0, 12, 0)
        layout.setSpacing(8)

        avatar = AvatarWidget(entry.name, size=44)
        if entry.avatar_pixmap:
            avatar.set_photo_pixmap(entry.avatar_pixmap)
        layout.addWidget(avatar)

        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        name_lbl = QLabel(entry.name)
        name_lbl.setStyleSheet("color: #f4f4f5; font-size: 12px;")
        info_col.addWidget(name_lbl)
        pill_text, pill_color = _STATE_PILL.get(entry.state, ("UNKNOWN", "#3f3f46"))
        pill = QLabel(pill_text)
        pill.setStyleSheet(
            f"color: #ffffff; background: {pill_color}; font-size: 9px;"
            " padding: 1px 4px; border-radius: 3px;"
        )
        pill.setAccessibleName(f"Call state: {entry.state.upper()}")
        info_col.addWidget(pill, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addLayout(info_col)

        if entry.state == "active":
            layout.addStretch()
            timer_lbl = QLabel(_fmt_elapsed(entry.elapsed))
            timer_lbl.setStyleSheet("color: #86efac; font-size: 14px;")
            timer_lbl.setAccessibleName("Call duration")
            layout.addWidget(timer_lbl)
            self._timer_lbl = timer_lbl

            keypad_btn = QPushButton("⌨ Keypad")
            keypad_btn.setFixedSize(104, 38)
            keypad_btn.setStyleSheet(
                "QPushButton { background: #27272a; color: #9ca3af; border: 1px solid #3f3f46;"
                " font-size: 12px; border-radius: 4px; }"
                " QPushButton:focus { outline: 2px dashed #3b82f6; }"
            )
            keypad_btn.setCheckable(True)
            keypad_btn.toggled.connect(self.keypad_toggled)
            layout.addWidget(keypad_btn)
            self._keypad_btn = keypad_btn

            hang_btn = QPushButton("✕ Hang Up")
            hang_btn.setFixedSize(100, 32)
            hang_btn.setStyleSheet(
                "QPushButton { background: #dc2626; color: #ffffff; border: none;"
                " font-size: 12px; border-radius: 4px; }"
                " QPushButton:focus { outline: 2px dashed #3b82f6; }"
            )
            cid = entry.call_id
            hang_btn.clicked.connect(lambda _c=False, _id=cid: self.hang_up_requested.emit(_id))
            layout.addWidget(hang_btn)

        elif entry.state == "held":
            layout.addStretch()
            hang_btn = QPushButton("✕ Hang Up")
            hang_btn.setFixedSize(100, 32)
            hang_btn.setStyleSheet(
                "QPushButton { background: #dc2626; color: #ffffff; border: none;"
                " font-size: 12px; border-radius: 4px; }"
                " QPushButton:focus { outline: 2px dashed #3b82f6; }"
            )
            cid = entry.call_id
            hang_btn.clicked.connect(lambda _c=False, _id=cid: self.hang_up_requested.emit(_id))
            layout.addWidget(hang_btn)

        elif entry.state == "waiting":
            layout.addStretch()
            hold_btn = QPushButton("⏸ Hold & Answer")
            hold_btn.setFixedSize(130, 32)
            hold_btn.setStyleSheet(
                "QPushButton { background: #16a34a; color: #ffffff; border: none;"
                " font-size: 11px; border-radius: 4px; }"
                " QPushButton:focus { outline: 2px dashed #3b82f6; }"
            )
            hold_btn.clicked.connect(self.hold_and_answer_requested)
            layout.addWidget(hold_btn)

            release_btn = QPushButton("✕ Release & Answer")
            release_btn.setFixedSize(138, 32)
            release_btn.setStyleSheet(
                "QPushButton { background: #dc2626; color: #ffffff; border: none;"
                " font-size: 11px; border-radius: 4px; }"
                " QPushButton:focus { outline: 2px dashed #3b82f6; }"
            )
            release_btn.clicked.connect(self.release_and_answer_requested)
            layout.addWidget(release_btn)

            decline_btn = QPushButton("Decline")
            decline_btn.setFixedSize(88, 32)
            decline_btn.setStyleSheet(
                "QPushButton { background: transparent; color: #9ca3af;"
                " border: 1px solid #3f3f46; font-size: 11px; border-radius: 4px; }"
                " QPushButton:focus { outline: 2px dashed #3b82f6; }"
            )
            decline_btn.clicked.connect(self.decline_waiting_requested)
            layout.addWidget(decline_btn)

        return row

    def _tick_active(self) -> None:
        self._active_elapsed += 1
        if self._timer_lbl is not None:
            self._timer_lbl.setText(_fmt_elapsed(self._active_elapsed))

    @property
    def elapsed(self) -> int:
        return self._active_elapsed

    def set_keypad_checked(self, state: bool) -> None:
        if self._keypad_btn is not None:
            self._keypad_btn.setChecked(state)
