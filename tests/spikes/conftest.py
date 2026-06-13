"""conftest.py — add spikes/ to sys.path so test files can do `import iris_spike`."""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "spikes"))
