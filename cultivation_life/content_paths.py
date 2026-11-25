"""Locate editable or bundled base content without initializing the game catalog."""
import os
import sys
from pathlib import Path


def default_content_root() -> Path:
    if os.environ.get("CULTIVATION_APP_ROOT"):
        return Path(os.environ["CULTIVATION_APP_ROOT"]) / "content"
    source_root = Path(__file__).resolve().parent.parent
    if getattr(sys, "frozen", False):
        editable_content = Path(sys.executable).resolve().parent / "content"
        if editable_content.is_dir():
            return editable_content
        source_root = Path(getattr(sys, "_MEIPASS", source_root))
    return source_root / "content"


def default_extension_root() -> Path:
    if os.environ.get("CULTIVATION_APP_ROOT"):
        return Path(os.environ["CULTIVATION_APP_ROOT"])
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent
