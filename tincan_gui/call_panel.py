"""Phone call UI widgets: incoming dialog, in-call panel, DTMF keypad, audio error.

No D-Bus wiring — all classes emit signals only. Callers in main.py connect
signals to the actual D-Bus client methods.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tincan_gui.avatar import AvatarWidget

_STATE_BORDER = {"active": "#0d9488", "held": "#d97706", "waiting": "#6366f1"}
_STATE_BADGE = {
    "active": ("▶ Active", "#0d9488"),
    "held": ("⏸ Held", "#d97706"),
    "waiting": ("☎ Waiting", "#6366f1"),
}

_DTMF_KEYS = [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"], ["*", "0", "#"]]


class IncomingCallDialog(QDialog):
    """Semi-modal dialog shown when an HFP call arrives (tincan-fx79v).

    Pass has_active_call=True to show the Call Waiting variant (tincan-o7yjg).
    """

    answered = Signal()
    declined = Signal()
    hold_and_answer_requested = Signal()
    release_and_answer_requested = Signal()

    def __init__(
        self,
        caller_name: str,
        caller_number: str,
        avatar_pixmap: QPixmap | None,
        parent: QWidget,
        has_active_call: bool = False,
        active_call_name: str = "",
        active_call_elapsed: int = 0,
        active_call_pixmap: QPixmap | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.WindowTitleHint)
        self._call_waiting = has_active_call
        if not has_active_call:
            self._init_incoming(caller_name, caller_number, avatar_pixmap)
        else:
            self._init_call_waiting(
                caller_name, caller_number, avatar_pixmap,
                active_call_name, active_call_elapsed, active_call_pixmap,
            )
        self.move(parent.geometry().center() - self.rect().center())

    def _init_incoming(
        self,
        caller_name: str,
        caller_number: str,
        avatar_pixmap: QPixmap | None,
    ) -> None:
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

    def _init_call_waiting(
        self,
        caller_name: str,
        caller_number: str,
        avatar_pixmap: QPixmap | None,
        active_call_name: str,
        active_call_elapsed: int,
        active_call_pixmap: QPixmap | None,
    ) -> None:
        self.setWindowTitle("Call Waiting")
        self.setStyleSheet("background: #18181b; color: #f4f4f5;")
        self.setFixedSize(340, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 24, 16, 16)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # waiting caller
        avatar = AvatarWidget(caller_name, size=68)
        if avatar_pixmap:
            avatar.set_photo_pixmap(avatar_pixmap)
        layout.addWidget(avatar, alignment=Qt.AlignmentFlag.AlignHCenter)

        name_lbl = QLabel(caller_name or caller_number)
        name_lbl.setStyleSheet("color: #f4f4f5; font-size: 20px; font-weight: 500;")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name_lbl)

        if caller_name:
            num_lbl = QLabel(caller_number)
            num_lbl.setStyleSheet("color: #9ca3af; font-size: 13px;")
            num_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(num_lbl)

        status_lbl = QLabel("Calling…")
        status_lbl.setStyleSheet("color: #6b7280; font-size: 11px;")
        status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(status_lbl)

        # active call mini-row
        mini = QWidget()
        mini.setStyleSheet(
            "QWidget { background: #27272a; border-left: 4px solid #0d9488;"
            " border-radius: 3px; }"
        )
        mini_layout = QHBoxLayout(mini)
        mini_layout.setContentsMargins(8, 4, 8, 4)
        mini_layout.setSpacing(6)

        mini_avatar = AvatarWidget(active_call_name, size=24)
        if active_call_pixmap:
            mini_avatar.set_photo_pixmap(active_call_pixmap)
        mini_layout.addWidget(mini_avatar)

        active_name_lbl = QLabel(active_call_name)
        active_name_lbl.setStyleSheet("color: #f4f4f5; font-size: 11px;")
        mini_layout.addWidget(active_name_lbl)

        self._active_timer_lbl = QLabel()
        self._active_timer_lbl.setStyleSheet("color: #86efac; font-size: 10px;")
        self._active_timer_lbl.setAccessibleName("Active call duration")
        mini_layout.addWidget(self._active_timer_lbl)
        mini_layout.addStretch()

        self._active_elapsed = active_call_elapsed
        self._update_active_timer()
        self._active_timer = QTimer(self)
        self._active_timer.setInterval(1000)
        self._active_timer.timeout.connect(self._tick_active_timer)
        self._active_timer.start()

        layout.addWidget(mini)
        layout.addStretch()

        # Hold & Answer + Release & Answer
        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        self._hold_btn = QPushButton("Hold && Answer")
        self._hold_btn.setFixedSize(162, 44)
        self._hold_btn.setDefault(False)
        self._hold_btn.setAutoDefault(False)
        self._hold_btn.setStyleSheet(
            "QPushButton { background: #16a34a; color: #ffffff; border: none;"
            " font-size: 13px; border-radius: 4px; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; outline-offset: 2px; }"
        )
        self._hold_btn.setAccessibleName("Hold active call and answer waiting call")
        self._hold_btn.clicked.connect(self._on_hold_and_answer)
        action_row.addWidget(self._hold_btn)

        self._release_btn = QPushButton("Release && Answer")
        self._release_btn.setFixedSize(162, 44)
        self._release_btn.setDefault(False)
        self._release_btn.setAutoDefault(False)
        self._release_btn.setStyleSheet(
            "QPushButton { background: #dc2626; color: #ffffff; border: none;"
            " font-size: 13px; border-radius: 4px; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; outline-offset: 2px; }"
        )
        self._release_btn.setAccessibleName("Release active call and answer waiting call")
        self._release_btn.clicked.connect(self._on_release_and_answer)
        action_row.addWidget(self._release_btn)

        layout.addLayout(action_row)

        # full-width Decline (ghost)
        self._decline_btn = QPushButton("✕  Decline")
        self._decline_btn.setFixedHeight(44)
        self._decline_btn.setAutoDefault(False)
        self._decline_btn.setStyleSheet(
            "QPushButton { background: #27272a; color: #9ca3af; border: 1px solid #3f3f46;"
            " font-size: 14px; border-radius: 4px; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; outline-offset: 2px; }"
        )
        self._decline_btn.clicked.connect(self._on_decline)
        layout.addWidget(self._decline_btn)

    def _update_active_timer(self) -> None:
        h, rem = divmod(self._active_elapsed, 3600)
        m, s = divmod(rem, 60)
        self._active_timer_lbl.setText(f"{h}:{m:02d}:{s:02d}")

    def _tick_active_timer(self) -> None:
        self._active_elapsed += 1
        self._update_active_timer()

    def _on_decline(self) -> None:
        self.declined.emit()
        self.reject()

    def _on_answer(self) -> None:
        self.answered.emit()
        self.accept()

    def _on_hold_and_answer(self) -> None:
        self.hold_and_answer_requested.emit()
        self.accept()

    def _on_release_and_answer(self) -> None:
        self.release_and_answer_requested.emit()
        self.accept()

    def disable_answer(self, reason: str) -> None:
        """Disable the Answer button (e.g. call_setup_ready=False) with tooltip."""
        self._answer_btn.setEnabled(False)
        self._answer_btn.setToolTip(reason)
        self._answer_btn.setAccessibleDescription(reason)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._on_decline()
        elif self._call_waiting and key == Qt.Key.Key_H:
            self._on_hold_and_answer()
        elif self._call_waiting and key == Qt.Key.Key_R:
            self._on_release_and_answer()
        else:
            super().keyPressEvent(event)


class _CallRow(QWidget):
    """54px row representing one call in multi-call mode (tincan-w59ao)."""

    hang_up_requested = Signal(str)  # call_id

    def __init__(self, call_id: str, label: str, state: str, parent: QWidget) -> None:
        super().__init__(parent)
        self._call_id = call_id
        self._elapsed = 0
        self.setFixedHeight(54)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 8, 0)
        row.setSpacing(8)

        avatar = AvatarWidget(label, size=44)
        row.addWidget(avatar)

        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        name_lbl = QLabel(label)
        name_lbl.setStyleSheet("color: #f4f4f5; font-size: 13px;")
        info_col.addWidget(name_lbl)
        self._badge = QLabel()
        self._badge.setFixedHeight(18)
        info_col.addWidget(self._badge)
        row.addLayout(info_col)

        self._timer_lbl = QLabel()
        self._timer_lbl.setStyleSheet("color: #86efac; font-size: 12px;")
        self._timer_lbl.hide()
        row.addWidget(self._timer_lbl)
        row.addStretch()

        hang_btn = QPushButton("✕ Hang Up")
        hang_btn.setFixedSize(108, 32)
        hang_btn.setStyleSheet(
            "QPushButton { background: #dc2626; color: #ffffff; border: none;"
            " font-size: 11px; border-radius: 4px; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; }"
        )
        hang_btn.clicked.connect(lambda: self.hang_up_requested.emit(self._call_id))
        row.addWidget(hang_btn)

        self._row_timer = QTimer(self)
        self._row_timer.setInterval(1000)
        self._row_timer.timeout.connect(self._tick)

        self.set_state(state)

    def set_state(self, state: str) -> None:
        self._state = state
        color = _STATE_BORDER.get(state, "#3f3f46")
        self.setStyleSheet(f"background: #18181b; border-left: 4px solid {color};")
        text, bg = _STATE_BADGE.get(state, (state, "#3f3f46"))
        self._badge.setText(text)
        self._badge.setStyleSheet(
            f"font-size: 11px; color: white; background: {bg};"
            " border-radius: 4px; padding: 1px 6px;"
        )
        self._badge.setAccessibleName(f"Call state: {state}")
        if state == "active":
            self._timer_lbl.show()
            self._row_timer.start()
        else:
            self._row_timer.stop()
            self._timer_lbl.hide()

    @property
    def state(self) -> str:
        return self._state

    def _tick(self) -> None:
        prev = self._elapsed
        self._elapsed += 1
        h, rem = divmod(self._elapsed, 3600)
        m, s = divmod(rem, 60)
        self._timer_lbl.setText(f"{h}:{m:02d}:{s:02d}")
        if self._elapsed // 60 != prev // 60:
            self._timer_lbl.setAccessibleName(f"Call duration {h}:{m:02d}")


class _MultiCallControls(QWidget):
    """28px strip of multi-call control buttons (tincan-w59ao)."""

    swap_requested = Signal()
    end_all_requested = Signal()
    hold_and_answer_requested = Signal()
    release_and_answer_requested = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setStyleSheet("background: #18181b; border-top: 1px solid #3f3f46;")

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(8)

        self._swap_btn = QPushButton("⇄ Swap Calls")
        self._swap_btn.setFixedSize(110, 28)
        self._swap_btn.setStyleSheet(
            "QPushButton { background: #27272a; color: #f4f4f5; border: 1px solid #3f3f46;"
            " font-size: 11px; border-radius: 4px; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; }"
        )
        self._swap_btn.clicked.connect(self.swap_requested)
        row.addWidget(self._swap_btn)

        self._end_all_btn = QPushButton("End All Calls")
        self._end_all_btn.setFixedSize(96, 22)
        self._end_all_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #9ca3af; border: 1px solid #3f3f46;"
            " font-size: 10px; border-radius: 3px; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; }"
        )
        self._end_all_btn.clicked.connect(self.end_all_requested)
        row.addWidget(self._end_all_btn)

        self._hold_btn = QPushButton("Hold & Answer")
        self._hold_btn.setFixedSize(128, 28)
        self._hold_btn.setStyleSheet(
            "QPushButton { background: #16a34a; color: #ffffff; border: none;"
            " font-size: 11px; border-radius: 4px; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; }"
        )
        self._hold_btn.clicked.connect(self.hold_and_answer_requested)
        row.addWidget(self._hold_btn)

        self._release_btn = QPushButton("Release & Answer")
        self._release_btn.setFixedSize(138, 28)
        self._release_btn.setStyleSheet(
            "QPushButton { background: #dc2626; color: #ffffff; border: none;"
            " font-size: 11px; border-radius: 4px; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; }"
        )
        self._release_btn.clicked.connect(self.release_and_answer_requested)
        row.addWidget(self._release_btn)
        row.addStretch()

    def update_mode(self, states: set) -> None:
        swap_mode = "active" in states and "held" in states and "waiting" not in states
        answer_mode = "active" in states and "waiting" in states
        self._swap_btn.setVisible(swap_mode)
        self._end_all_btn.setVisible(swap_mode)
        self._hold_btn.setVisible(answer_mode)
        self._release_btn.setVisible(answer_mode)


class InCallPanel(QWidget):
    """In-call control bar (88px) that replaces the compose bar (tincan-fx79v)."""

    hang_up_requested = Signal()
    keypad_toggled = Signal(bool)
    swap_calls_requested = Signal()
    end_all_calls_requested = Signal()
    hold_and_answer_requested = Signal()
    release_and_answer_requested = Signal()
    hang_up_call_requested = Signal(str)  # call_id

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
        self._calls: dict[str, _CallRow] = {}
        self._elapsed = elapsed_offset
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # single-call container (existing layout, shown when ≤1 calls)
        self._single_widget = QWidget(self)
        self._single_widget.setFixedHeight(88)
        row = QHBoxLayout(self._single_widget)
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
        outer.addWidget(self._single_widget)

        # multi-call container (hidden until 2+ calls)
        self._multi_widget = QWidget(self)
        multi_vbox = QVBoxLayout(self._multi_widget)
        multi_vbox.setContentsMargins(0, 7, 0, 7)
        multi_vbox.setSpacing(0)
        self._call_rows_layout = QVBoxLayout()
        self._call_rows_layout.setSpacing(0)
        multi_vbox.addLayout(self._call_rows_layout)
        self._multi_ctrl = _MultiCallControls(self._multi_widget)
        self._multi_ctrl.swap_requested.connect(self.swap_calls_requested)
        self._multi_ctrl.end_all_requested.connect(self.end_all_calls_requested)
        self._multi_ctrl.hold_and_answer_requested.connect(self.hold_and_answer_requested)
        self._multi_ctrl.release_and_answer_requested.connect(self.release_and_answer_requested)
        multi_vbox.addWidget(self._multi_ctrl)
        outer.addWidget(self._multi_widget)
        self._multi_widget.hide()

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

    def add_call(self, call_id: str, number: str, direction: str, state: str) -> None:
        if call_id in self._calls:
            self._calls[call_id].set_state(state)
            self._refresh_multi_controls()
            return
        call_row = _CallRow(call_id, number, state, self)
        call_row.hang_up_requested.connect(self.hang_up_call_requested)
        self._calls[call_id] = call_row
        self._call_rows_layout.addWidget(call_row)
        self._refresh_layout()

    def update_call_state(self, call_id: str, new_state: str) -> None:
        cs = self._calls.get(call_id)
        if cs is not None:
            cs.set_state(new_state)
            self._refresh_multi_controls()

    def remove_call(self, call_id: str) -> None:
        call_row = self._calls.pop(call_id, None)
        if call_row is not None:
            self._call_rows_layout.removeWidget(call_row)
            call_row.deleteLater()
        self._refresh_layout()

    def _refresh_layout(self) -> None:
        multi = len(self._calls) >= 2
        self._single_widget.setVisible(not multi)
        self._multi_widget.setVisible(multi)
        self.setFixedHeight(150 if multi else 88)
        if multi:
            self._refresh_multi_controls()

    def _refresh_multi_controls(self) -> None:
        states = {r.state for r in self._calls.values()}
        self._multi_ctrl.update_mode(states)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if len(self._calls) >= 2:
            states = {r.state for r in self._calls.values()}
            if event.key() == Qt.Key.Key_H and "waiting" in states and "active" in states:
                self.hold_and_answer_requested.emit()
                return
            if event.key() == Qt.Key.Key_R and "waiting" in states and "active" in states:
                self.release_and_answer_requested.emit()
                return
        super().keyPressEvent(event)


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
