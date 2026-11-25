"""The named body mechanisms used by compact combat snapshots."""
from functools import lru_cache

from .content_io import read_json
from .content_paths import default_content_root


@lru_cache(maxsize=1)
def base_light_names():
    document = read_json(default_content_root() / "doctrines.json")
    return {row["id"]: row["name"] for row in document["cultivation"]["divine_lights"]}
