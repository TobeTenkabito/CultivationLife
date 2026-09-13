from __future__ import annotations

import ast
import random
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def encode_rng(rng: random.Random) -> str:
    return repr(rng.getstate())


def decode_rng(seed: int, state: str) -> random.Random:
    rng = random.Random(seed)
    if state:
        rng.setstate(ast.literal_eval(state))
    return rng
