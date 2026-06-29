"""ANCSStatusDot — 12 px ANCS status indicator widget (tincan-kzgk7.4)."""
from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QAccessible, QAccessibleEvent, QColor, QPainter
from PySide6.QtWidgets import QApplication, QWidget


class ANCSStatusDot(QWidget):
    """12 px ANCS status indicator — green (active), amber pulsing (healing), hidden otherwise.

    State table (ancs_status string from daemon):
      "active"   → green static, visible
      "healing"  → amber pulsing, visible
      anything else ("armed", "fallback", "disabled") → hidden

    WCAG 2.1 AA: accessible name updated on each transition; non-text contrast ≥ 3:1.
    Prefers-reduced-motion: static amber (no pulse) when system reduced-motion is on.
    Not interactive — excluded from tab order.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(12, 12)
        self.setFocusPolicy(Qt.NoFocus)
        self._color = QColor(0, 0, 0, 0)
        self._alpha: float = 1.0
        self._anim: QPropertyAnimation | None = None
        self.hide()

    # ------------------------------------------------------------------
    # Animatable property (Q_PROPERTY for QPropertyAnimation)
    # ------------------------------------------------------------------

    def _get_dot_alpha(self) -> float:
        return self._alpha

    def _set_dot_alpha(self, value: float) -> None:
        self._alpha = value
        self.update()

    dot_alpha = Property(float, _get_dot_alpha, _set_dot_alpha)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_state(self, ancs_status: str) -> None:
        """Update dot visibility and color based on ancs_status string from daemon."""
        self._stop_pulse()
        if ancs_status == "active":
            self._color = QColor("#22c55e")
            self._alpha = 1.0
            self.setToolTip("Bluetooth notifications")
            self.setAccessibleName("Notifications active")
            self.setAccessibleDescription("Bluetooth notifications are active")
            self.show()
            self._fire_accessible_event()
        elif ancs_status == "healing":
            # HEALING: pulsing amber (#d97706 meets non-text contrast ≥ 3:1 on white)
            self._color = QColor("#d97706")
            self._alpha = 1.0
            self.setToolTip("Reconnecting...")
            self.setAccessibleName("Reconnecting, please wait")
            self.setAccessibleDescription("Bluetooth notifications are reconnecting")
            self.show()
            self._fire_accessible_event()
            if not self._reduced_motion():
                self._start_pulse()
        else:
            # armed, fallback, disabled, or unknown: hide
            self.hide()

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = QColor(self._color)
        color.setAlphaF(self._alpha)
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, 12, 12)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _start_pulse(self) -> None:
        self._anim = QPropertyAnimation(self, b"dot_alpha")
        self._anim.setDuration(1200)
        self._anim.setKeyValueAt(0.0, 1.0)
        self._anim.setKeyValueAt(0.5, 0.3)
        self._anim.setKeyValueAt(1.0, 1.0)
        self._anim.setEasingCurve(QEasingCurve.InOutSine)
        self._anim.setLoopCount(-1)
        self._anim.start()

    def _stop_pulse(self) -> None:
        if self._anim is not None:
            self._anim.stop()
            self._anim = None
        self._alpha = 1.0

    @staticmethod
    def _reduced_motion() -> bool:
        hints = QApplication.styleHints()
        return bool(hints.reducedAnimations()) if hasattr(hints, "reducedAnimations") else False

    def _fire_accessible_event(self) -> None:
        event = QAccessibleEvent(self, QAccessible.Event.NameChanged)
        QAccessible.updateAccessibility(event)
