"""Deterministic streams shared by doctrine generation and effect enrichment."""
import random


def rng_for(seed: int, version: int, stream: str) -> random.Random:
    return random.Random(f"{seed}:celestial-doctrine:v{version}:{stream}")

