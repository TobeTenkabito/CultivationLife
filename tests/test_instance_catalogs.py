import ast
import importlib
import json
from pathlib import Path
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from cultivation_life.content_paths import default_content_root
from cultivation_life.definition_data import definition
from cultivation_life.errors import ContentError
from cultivation_life.trait_repertoires import load_repertoires


def test_shipped_instance_catalogs_match_their_production_readers():
    root = default_content_root()
    package = Path(__file__).resolve().parents[1] / "cultivation_life"
    catalog_root = root / "definitions"
    used = set()
    for source in package.rglob("*.py"):
        text = source.read_text(encoding="utf-8-sig")
        if "definition_data import definition" not in text:
            continue
        nodes = list(ast.walk(ast.parse(text)))
        aliases = {alias.asname or alias.name for node in nodes if isinstance(node, ast.ImportFrom)
                   and node.module == "definition_data" for alias in node.names if alias.name == "definition"}
        calls = [node for node in nodes if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                 and node.func.id in aliases]
        if not calls:
            continue
        relative = source.relative_to(package)
        path = catalog_root / relative.with_suffix(".json")
        module = importlib.import_module("cultivation_life." + ".".join(relative.with_suffix("").parts))
        keys = set()
        for call in calls:
            key = ast.literal_eval(call.args[1])
            constructors = [getattr(module, arg.id) for arg in call.args[2:]]
            definition(module.__name__, key, *constructors)
            keys.add(key)
        assert keys == json.loads(path.read_text(encoding="utf-8"))["definitions"].keys(), relative
        used.add(path)
    assert used == set(catalog_root.rglob("*.json"))


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


def test_guardian_combats_keep_scene_identity_and_wounds_out_of_the_catalog():
    from cultivation_life.engine.composition.heavens_guardians import fight_guardian

    targets = []
    def combat(game, target, lethal, rng):
        targets.append(target)
        member = target['members'][0]
        assert member['wounds'] == 1
        assert target['target_power'] == member['power'] == 85
        assert target['artificial_conditions'] == []
        target['artificial_conditions'].append('试阵')
        game.last_combat_report = {'enemy_hp_ratio': .25}
        return 'victory', '退敌'

    engine = SimpleNamespace(_combat=combat)
    game = SimpleNamespace(last_combat_report=None)
    for kind, identity, chamber in [('mirror', 'mirror-7-guardian-1', 2), ('ruins', 'ruins-8-guardian', None)]:
        assert fight_guardian(engine, game, kind, identity, 100, 1, None, chamber=chamber) == ('victory', '退敌', 3)
    assert [(t['members'][0]['npc_id'], t['target_name']) for t in targets] == [
        ('mirror-7-guardian-1', '第 2 处守镜机关'), ('ruins-8-guardian', '回潮守阵机关')]


def test_invalid_trial_rosters_fail_validation_even_when_difficulty_overrides_the_ratio():
    from copy import deepcopy
    from cultivation_life.content_registry import CONTENT_DOCUMENTS, WORLD_SYSTEMS
    from cultivation_life.system.combat.trial_difficulty import validate_asura_encounters, validate_upper_stages

    config = deepcopy(WORLD_SYSTEMS['asura_manifestation'])
    config['trial_encounters']['opponents']['10'][1]['ratio'] = 0
    with pytest.raises(ValueError, match='ratios'):
        validate_asura_encounters(config)
    stages = deepcopy(CONTENT_DOCUMENTS['monster_true_forms.json']['breakthrough_stages'])
    del stages['10']['self_lineage_opponents']
    with pytest.raises(ValueError, match='阵容'):
        validate_upper_stages(stages, monster=True)
