"""Content helpers for the version-three combat rule vocabulary."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Signature:
    description: str
    rules: tuple = ()
