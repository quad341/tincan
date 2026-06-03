"""Root pytest conftest: force headless Qt so test runs never pop windows on the display."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
