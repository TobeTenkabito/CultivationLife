"""Load per-domain authored definitions, preserving collection and record contracts."""
from copy import deepcopy
from functools import lru_cache

from .content_io import read_json
from .content_paths import default_content_root
from .errors import ContentError


@lru_cache(maxsize=None)
def _document(path):
    doc = read_json(path)
    if (type(doc.get("schema_version")) is not int or doc["schema_version"] != 1
            or not isinstance(doc.get("definitions"), dict)):
        raise ContentError(f"{path}: invalid definition catalog")
    return doc["definitions"]


def _restore(value, records):
    if isinstance(value, list):
        return [_restore(v, records) for v in value]
    if not isinstance(value, dict):
        return value
    tags = [key for key in value if key.startswith("$")]
    if not tags:
        return {k: _restore(v, records) for k, v in value.items()}
    if tags == ["$record"]:
        constructor = records[value["$record"]]
        return constructor(**{k: _restore(v, records) for k, v in value.items() if k != "$record"})
    tag = tags[0]
    items = value[tag]
    if len(value) != 1 or not isinstance(items, list):
        raise ValueError(f"invalid collection descriptor {tag}")
    if tag == "$range" and len(items) == 3 and all(type(i) is int for i in items):
        return range(*items)
    if tag == "$pairs":
        pairs = {}
        for pair in items:
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError("expected a key/value pair")
            key = _restore(pair[0], records)
            if key in pairs:
                raise ValueError(f"duplicate catalog key {key!r}")
            pairs[key] = _restore(pair[1], records)
        return pairs
    if tag in ("$tuple", "$set", "$frozenset"):
        values = [_restore(v, records) for v in items]
        if tag == "$tuple":
            return tuple(values)
        result = set(values)
        if len(result) != len(values):
            raise ValueError(f"duplicate entry in {tag}")
        return frozenset(result) if tag == "$frozenset" else result
    raise ValueError(f"unknown or invalid catalog descriptor {tag}")


@lru_cache(maxsize=None)
def _entry(module, key, record_types):
    path = default_content_root() / "definitions" / (module.removeprefix("cultivation_life.").replace(".", "/") + ".json")
    try:
        return _restore(_document(path)[key], {cls.__name__: cls for cls in record_types})
    except (KeyError, TypeError, ValueError) as exc:
        raise ContentError(f"{path} [{key}]: {exc}") from exc


def definition(module, key, *record_types):
    # Callers may extend a base registry or mutate the fresh row returned by a factory.
    return deepcopy(_entry(module, key, record_types))
