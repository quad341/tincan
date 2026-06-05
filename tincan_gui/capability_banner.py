"""CapabilityBanner — degradation notification widget with Alert accessible role."""
from __future__ import annotations

from typing import Optional

from PySide6.QtGui import QAccessible
from PySide6.QtWidgets import QAccessibleWidget, QLabel, QVBoxLayout, QWidget


class CapabilityBanner(QWidget):
    """Capability degradation banner — role AlertMessage for immediate AT announcement."""

    def __init__(self, message: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        self._label = QLabel(message)
        self._label.setWordWrap(True)
        layout.addWidget(self._label)
        self.setAccessibleName(message)


def _capability_banner_factory(classname: str, obj) -> Optional[QAccessibleWidget]:
    if isinstance(obj, CapabilityBanner):
        return QAccessibleWidget(obj, QAccessible.Role.AlertMessage)
    return None


QAccessible.installFactory(_capability_banner_factory)
