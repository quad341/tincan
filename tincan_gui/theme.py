"""Dark theme detection and global stylesheet."""
from __future__ import annotations

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

DARK_STYLESHEET = (
    "QMainWindow { background-color: #18181b; }"
    " QScrollArea, QScrollArea > QWidget, QScrollArea > QWidget > QWidget"
    " { background-color: #18181b; }"
    " QListWidget { background-color: #27272a; color: #f4f4f5; border: none; }"
    " QListWidget::item:selected { background-color: #3f3f46; color: #f4f4f5; }"
    " QListWidget::item:hover:!selected { background-color: #2d2d30; }"
    " QPlainTextEdit { background-color: #18181b; color: #f4f4f5;"
    " border: 1px solid #3f3f46; selection-background-color: #0d9488; }"
    " QLineEdit { background-color: #27272a; color: #f4f4f5;"
    " border: 1px solid #3f3f46; selection-background-color: #0d9488; }"
)


def is_dark_theme() -> bool:
    """Return True if the current system palette indicates a dark theme."""
    app = QApplication.instance()
    if app is None:
        return False
    return app.palette().color(QPalette.ColorRole.Window).lightness() < 128
