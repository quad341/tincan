import os
import sys
from pathlib import Path

from PySide6.QtCore import QLocale, QTranslator
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from tincan_gui.theme import DARK_STYLESHEET, FOCUS_STYLESHEET, is_dark_theme

_ASSETS = Path(__file__).parent / "assets"
_TRANSLATIONS = Path(__file__).parent / "translations"

app = QApplication(sys.argv)
app.setWindowIcon(QIcon(str(_ASSETS / "tincan-icon.png")))
if is_dark_theme():
    app.setStyleSheet(DARK_STYLESHEET)
else:
    app.setStyleSheet(FOCUS_STYLESHEET)


def _reapply_theme(_palette=None) -> None:
    """Re-evaluate dark/light after platform theme plugin updates the palette."""
    app.setStyleSheet(DARK_STYLESHEET if is_dark_theme() else FOCUS_STYLESHEET)


app.paletteChanged.connect(_reapply_theme)

# ---------------------------------------------------------------------------
# i18n: load translation for TINCAN_LOCALE (or system locale); silent fallback
# ---------------------------------------------------------------------------
_translator = QTranslator(app)
_locale = os.environ.get("TINCAN_LOCALE") or QLocale.system().name()
_loaded = _translator.load(f"tincan_{_locale}", str(_TRANSLATIONS))
if not _loaded:
    # Try language-only fallback (e.g. "fr" from "fr_FR")
    _lang = _locale.split("_")[0]
    _loaded = _translator.load(f"tincan_{_lang}", str(_TRANSLATIONS))
if _loaded:
    app.installTranslator(_translator)
# If still not loaded: English source strings are used as-is (silent fallback)

from tincan_gui.main import main  # noqa: E402

main()
