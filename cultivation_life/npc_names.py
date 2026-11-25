"""Shared Chinese personal names for generated cultivators."""
from .definition_data import definition as _content_definition

SURNAMES = _content_definition(__name__, "SURNAMES")
GIVEN_NAMES = _content_definition(__name__, "GIVEN_NAMES")


def person_name(rng, used=()):
    occupied = set(used)
    for _ in range(64):
        name = rng.choice(SURNAMES) + rng.choice(GIVEN_NAMES)
        if name not in occupied:
            return name
    # Bounded deterministic fallback, without visible serial numbers.
    for surname in SURNAMES:
        for given in GIVEN_NAMES:
            if surname + given not in occupied:
                return surname + given
    raise ValueError("当前人物姓名池已用尽")
