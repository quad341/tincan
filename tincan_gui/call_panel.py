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
            avatar.set_photo(avatar_pixmap)
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

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._on_decline()
        else:
            super().keyPressEvent(event)


class InCallPanel(QWidget):
    """In-call control bar (88px) that replaces the compose bar (tincan-fx79v)."""

    hold_toggled = Signal(bool)   # True = held, False = resumed
    hang_up_requested = Signal()
    keypad_toggled = Signal(bool)

    def __init__(
        self,
        caller_name: str,
        avatar_pixmap: QPixmap | None,
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: #18181b; border-top: 2px solid #0d9488;")
        self.setFixedHeight(88)
        self._held = False
        self._elapsed = 0
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(8)

        avatar = AvatarWidget(caller_name, size=44)
        if avatar_pixmap:
            avatar.set_photo(avatar_pixmap)
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

        self._hold_btn = QPushButton("⏸ Hold")
        self._hold_btn.setFixedSize(100, 38)
        self._hold_btn.setStyleSheet(self._hold_style(False))
        self._hold_btn.setCheckable(True)
        self._hold_btn.toggled.connect(self._on_hold_toggled)
        row.addWidget(self._hold_btn)

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

    @staticmethod
    def _hold_style(held: bool) -> str:
        bg = "#d97706" if not held else "#3f3f46"
        text = "#ffffff" if not held else "#9ca3af"
        return (
            f"QPushButton {{ background: {bg}; color: {text}; border: none;"
            " font-size: 13px; border-radius: 4px; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; }"
        )

    def _on_hold_toggled(self, held: bool) -> None:
        self._held = held
        self._hold_btn.setText("▶ Resume" if held else "⏸ Hold")
        self._hold_btn.setStyleSheet(self._hold_style(held))
        self.hold_toggled.emit(held)
        if held:
            self._timer.stop()
        else:
            self._timer.start()

    def _tick(self) -> None:
        self._elapsed += 1
        h, rem = divmod(self._elapsed, 3600)
        m, s = divmod(rem, 60)
        self._timer_lbl.setText(f"{h}:{m:02d}:{s:02d}")


class DTMFKeypad(QWidget):
    """4×3 DTMF key grid with tone display (tincan-fx79v stretch goal)."""

    tone_pressed = Signal(str)

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
            self.hide()
        else:
            super().keyPressEvent(event)


class AudioErrorPanel(QWidget):
    """88px panel shown when HFP audio SCO channel fails (tincan-fx79v)."""

    retry_requested = Signal()
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

        retry_btn = QPushButton("↻ Retry Audio")
        retry_btn.setFixedSize(100, 30)
        retry_btn.setAccessibleName("Retry HFP audio connection")
        retry_btn.setStyleSheet(
            "QPushButton { background: #27272a; color: #9ca3af; border: 1px solid #3f3f46;"
            " font-size: 11px; border-radius: 4px; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; }"
        )
        retry_btn.clicked.connect(self.retry_requested)
        row.addWidget(retry_btn)

        hang_btn = QPushButton("✕ Hang Up")
        hang_btn.setFixedSize(108, 30)
        hang_btn.setStyleSheet(
            "QPushButton { background: #dc2626; color: #ffffff; border: none;"
            " font-size: 11px; border-radius: 4px; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; }"
        )
        hang_btn.clicked.connect(self.hang_up_requested)
        row.addWidget(hang_btn)
