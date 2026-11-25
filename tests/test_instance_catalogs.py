import json
from dataclasses import dataclass

import pytest

from cultivation_life.content_paths import default_content_root
from cultivation_life.definition_data import definition
from cultivation_life.errors import ContentError
from cultivation_life.trait_repertoires import load_repertoires


def test_instance_catalog_preserves_typed_keys_and_independent_records(tmp_path, monkeypatch):
    @dataclass
    class Reward:
        materials: list

    directory = tmp_path / "definitions"
    directory.mkdir()
    rows = {"$pairs": [[{"$tuple": [1, 2]}, {"$record": "Reward", "materials": ["jade"]}]]}
    (directory / "example.json").write_text(json.dumps({
        "schema_version": 1, "definitions": {"rewards": rows, "invalid": {"$pairs": [[1, "a"], [1, "b"]]}},
    }), encoding="utf-8")
    monkeypatch.setattr("cultivation_life.definition_data.default_content_root", lambda: tmp_path)
    reward = definition("example", "rewards", Reward)[1, 2]
    reward.materials.clear()
    assert definition("example", "rewards", Reward)[1, 2].materials == ["jade"]
    with pytest.raises(ContentError, match="duplicate catalog key"):
        definition("example", "invalid")
    with pytest.raises(ContentError, match="Reward"):
        definition("example", "rewards")


def test_trait_record_can_change_grades_and_share_multiple_sources(tmp_path):
    source = default_content_root() / "trait_repertoires.json"
    row = json.loads(source.read_text(encoding="utf-8"))["traits"][0]
    row.update(level=4, rarity="蓝", innate=False, books=["first", "second"], artifacts=["blade", "seal"])
    path = tmp_path / "traits.json"
    path.write_text(json.dumps({"schema_version": 1, "traits": [row]}), encoding="utf-8")
    entry = load_repertoires(path)["蓝"][row["id"]]
    assert (entry.level, entry.innate, entry.books, entry.artifacts) == (4, False, ("first", "second"), ("blade", "seal"))
    path.write_text(json.dumps({"schema_version": 1, "traits": [row, dict(row, id="other")]}), encoding="utf-8")
    with pytest.raises(ContentError, match="duplicate mastery source"):
        load_repertoires(path)
