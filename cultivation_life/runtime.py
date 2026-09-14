from __future__ import annotations

import ast
import random
import sys
from datetime import datetime, timezone
from pathlib import Path


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def persistence_root(app_root: Path | None = None) -> Path:
    """Return the one persistent root used by saves and local preferences.

    A PyInstaller artifact built into this repository's ``dist`` directory is
    only a staging copy.  It must share the repository-level ``data`` folder
    with the normal root launcher instead of silently creating a second save
    library under ``dist/data``.  A genuinely distributed executable keeps
    using its own directory because the development markers are absent.
    """
    root = (
        Path(app_root).resolve()
        if app_root is not None
        else Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent.parent
    )
    parent = root.parent
    if (
        root.name.casefold() == "dist"
        and (parent / "launcher.py").is_file()
        and (parent / "content").is_dir()
        and (parent / "build" / "launcher.spec").is_file()
    ):
        return parent
    return root


def encode_rng(rng: random.Random) -> str:
    return repr(rng.getstate())


def decode_rng(seed: int, state: str) -> random.Random:
    rng = random.Random(seed)
    if state:
        rng.setstate(ast.literal_eval(state))
    return rng
