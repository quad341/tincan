"""Dark theme detection and global stylesheet."""
from __future__ import annotations

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QWidget

FOCUS_STYLESHEET = (
    "QWidget:focus { outline: 2px dashed #3b82f6; outline-offset: 2px; }"
)

DARK_STYLESHEET = (
    FOCUS_STYLESHEET
    + " QMainWindow { background-color: #18181b; }"
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


DIALOG_STYLESHEET = (
    DARK_STYLESHEET
    + " QDialog { background-color: #18181b; color: #f4f4f5; }"
    " QLabel { color: #f4f4f5; }"
    " QPushButton { background-color: #27272a; color: #f4f4f5;"
    " border: 1px solid #3f3f46; border-radius: 4px; padding: 4px 12px; }"
    " QPushButton:hover { background-color: #3f3f46; }"
    " QPushButton:default { background-color: #0d9488; color: #ffffff; border-color: #0d9488; }"
    " QTextEdit { background-color: #18181b; color: #f4f4f5;"
    " border: 1px solid #3f3f46; }"
)


def apply_dark_theme(widget: QWidget) -> None:
    """Apply the dark stylesheet to a dialog or widget.

    Convention: every new QDialog subclass in tincan_gui/ must call
    apply_dark_theme(self) as its first line after super().__init__().
    Import: from tincan_gui.theme import apply_dark_theme
    """
    widget.setStyleSheet(DIALOG_STYLESHEET)


def is_dark_theme() -> bool:
    """Return True if the current system palette indicates a dark theme."""
    app = QApplication.instance()
    if app is None:
        return False
    return app.palette().color(QPalette.ColorRole.Window).lightness() < 128
