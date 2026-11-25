"""Authored local inheritances; shared by scenery and the secret-art catalogue."""
from .definition_data import definition as _content_definition

STORIES = _content_definition(__name__, "STORIES")


def acquisition_hint(identity):
    row = STORIES[identity]
    return f'人界 · {row["place"]} · {row["name"]}，探索「{row["title"]}」并领悟传承'


def scenery_seeds():
    return [dict(id=r['building'], name=r['name'], location_id=r['location'], description=r['description'])
            for r in STORIES.values() if 'description' in r]
