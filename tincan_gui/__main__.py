import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from tincan_gui.main import main
from tincan_gui.theme import DARK_STYLESHEET, FOCUS_STYLESHEET, is_dark_theme

_ASSETS = Path(__file__).parent / "assets"

app = QApplication(sys.argv)
app.setWindowIcon(QIcon(str(_ASSETS / "tincan-icon.png")))
if is_dark_theme():
    app.setStyleSheet(DARK_STYLESHEET)
else:
    app.setStyleSheet(FOCUS_STYLESHEET)
main()
