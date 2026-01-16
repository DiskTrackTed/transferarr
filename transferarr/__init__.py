# This file marks the directory as a Python package.

from pathlib import Path

# Read version from VERSION file at package root
_version_file = Path(__file__).parent.parent / "VERSION"
if _version_file.exists():
    __version__ = _version_file.read_text().strip()
else:
    __version__ = "0.0.0-unknown"
