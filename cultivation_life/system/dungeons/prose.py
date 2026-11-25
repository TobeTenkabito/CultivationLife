"""Seeded scene vocabulary. Public observations never encode private objectives."""
from ...definition_data import definition as _content_definition
LANDMARKS = _content_definition(__name__, "LANDMARKS")
DETAILS = _content_definition(__name__, "DETAILS")
SENSES = _content_definition(__name__, "SENSES")
EVENTS = _content_definition(__name__, "EVENTS")
STORIES = _content_definition(__name__, "STORIES")
CLUES = _content_definition(__name__, "CLUES")
OBSERVATIONS = {
    'desire': tuple(CLUES[i] for i in (4,9,12,14)),
    'preparation': tuple(CLUES[i] for i in (0,1,2,3,6,10,13,15)),
    'trust': tuple(CLUES[i] for i in (5,7,8,11)),
}


from . import prose_expansion as extra

for key,values in extra.LANDMARKS.items():
    LANDMARKS[key].extend(values)
for key,values in extra.EVENTS.items():
    EVENTS[key]+=values
STORIES+=extra.STORIES
for key,values in extra.OBSERVATIONS.items():
    OBSERVATIONS[key]+=values
CLUES+=sum(extra.OBSERVATIONS.values(),())
THEMED_DETAILS={key:DETAILS+extra.DETAILS[key] for key in LANDMARKS}
THEMED_SENSES={key:SENSES+extra.SENSES[key] for key in LANDMARKS}


def variant(identity,values):
    import hashlib
    return values[int.from_bytes(hashlib.sha256(identity.encode()).digest(),'big')%len(values)]


def scene(rng, location, theme, kind, direction):
    return (f'{location}，{direction}侧的{rng.choice(LANDMARKS[theme])}。'
            +rng.choice(THEMED_DETAILS[theme])+rng.choice(THEMED_SENSES[theme])+rng.choice(EVENTS[kind]))
