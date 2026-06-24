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

_DTMF_KEYS = [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"], ["*", "0", "#"]]


class IncomingCallDialog(QDialog):
    """Semi-modal dialog shown when an HFP call arrives or is waiting (tincan-fx79v, tincan-o7yjg).

    Pass has_active_call=True to show Call Waiting mode: the dialog gains a
    mini active-call row and replaces Answer with Hold&Answer / Release&Answer.
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
        self._has_active_call = has_active_call
        self.setStyleSheet("background: #18181b; color: #f4f4f5;")

        if has_active_call:
            self.setWindowTitle("Call Waiting")
            self.setFixedSize(340, 420)
        else:
            self.setWindowTitle("Incoming Call")
            self.setFixedSize(340, 290)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 24, 16, 16)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        if has_active_call:
            self._build_active_mini_row(
                layout, active_call_name, active_call_elapsed, active_call_pixmap
            )

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

        status_lbl = QLabel(
            "Waiting call via HFP…" if has_active_call else "Incoming call via HFP…"
        )
        status_lbl.setStyleSheet("color: #6b7280; font-size: 11px;")
        status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(status_lbl)

        layout.addStretch()

        if has_active_call:
            self._build_call_waiting_buttons(layout)
        else:
            self._build_incoming_buttons(layout)

        self.move(
            parent.geometry().center() - self.rect().center()
        )

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def _build_active_mini_row(
        self,
        layout: QVBoxLayout,
        active_name: str,
        elapsed: int,
        pixmap: QPixmap | None,
    ) -> None:
        row = QHBoxLayout()
        row.setSpacing(8)

        mini_avatar = AvatarWidget(active_name, size=24)
        if pixmap:
            mini_avatar.set_photo_pixmap(pixmap)
        row.addWidget(mini_avatar)

        info = QVBoxLayout()
        info.setSpacing(0)
        name_lbl = QLabel(active_name or "Active call")
        name_lbl.setStyleSheet("color: #9ca3af; font-size: 11px;")
        info.addWidget(name_lbl)
        h, rem = divmod(elapsed, 3600)
        m, s = divmod(rem, 60)
        timer_lbl = QLabel(f"{h}:{m:02d}:{s:02d}")
        timer_lbl.setStyleSheet("color: #6b7280; font-size: 10px;")
        info.addWidget(timer_lbl)
        row.addLayout(info)
        row.addStretch()

        sep_label = QLabel("— on hold —")
        sep_label.setStyleSheet("color: #3f3f46; font-size: 10px;")
        row.addWidget(sep_label)

        container = QWidget()
        container.setStyleSheet(
            "background: #27272a; border-radius: 4px; border: 1px solid #3f3f46;"
        )
        container.setLayout(row)
        container.setContentsMargins(8, 6, 8, 6)
        layout.addWidget(container)
        layout.addSpacing(8)

    def _build_incoming_buttons(self, layout: QVBoxLayout) -> None:
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

    def _build_call_waiting_buttons(self, layout: QVBoxLayout) -> None:
        action_row = QHBoxLayout()
        action_row.setSpacing(12)

        self._hold_btn = QPushButton("⏸  Hold & Answer")
        self._hold_btn.setFixedSize(162, 44)
        self._hold_btn.setStyleSheet(
            "QPushButton { background: #16a34a; color: #ffffff; border: none;"
            " font-size: 13px; border-radius: 4px; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; outline-offset: 2px; }"
        )
        self._hold_btn.setDefault(False)
        self._hold_btn.setAutoDefault(False)
        self._hold_btn.clicked.connect(self._on_hold_and_answer)

        self._release_btn = QPushButton("✕  Release & Answer")
        self._release_btn.setFixedSize(162, 44)
        self._release_btn.setStyleSheet(
            "QPushButton { background: #dc2626; color: #ffffff; border: none;"
            " font-size: 13px; border-radius: 4px; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; outline-offset: 2px; }"
        )
        self._release_btn.setDefault(False)
        self._release_btn.setAutoDefault(False)
        self._release_btn.clicked.connect(self._on_release_and_answer)

        action_row.addWidget(self._hold_btn)
        action_row.addWidget(self._release_btn)
        layout.addLayout(action_row)
        layout.addSpacing(8)

        self._decline_btn = QPushButton("✕  Decline")
        self._decline_btn.setFixedHeight(44)
        self._decline_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #9ca3af; border: 1px solid #3f3f46;"
            " font-size: 14px; border-radius: 4px; }"
            " QPushButton:hover { background: #27272a; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; outline-offset: 2px; }"
        )
        self._decline_btn.setDefault(False)
        self._decline_btn.setAutoDefault(False)
        self._decline_btn.clicked.connect(self._on_decline)
        layout.addWidget(self._decline_btn)

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    def _on_decline(self) -> None:
        self.reject()

    def reject(self) -> None:
        self.declined.emit()
        super().reject()

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
        if self._has_active_call:
            self._hold_btn.setEnabled(False)
            self._hold_btn.setToolTip(reason)
            self._release_btn.setEnabled(False)
            self._release_btn.setToolTip(reason)
        else:
            self._answer_btn.setEnabled(False)
            self._answer_btn.setToolTip(reason)
            self._answer_btn.setAccessibleDescription(reason)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._on_decline()
        elif self._has_active_call and key == Qt.Key.Key_H:
            self._on_hold_and_answer()
        elif self._has_active_call and key == Qt.Key.Key_R:
            self._on_release_and_answer()
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
