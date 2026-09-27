import copy
import random
from pathlib import Path
from unittest.mock import patch

import pytest

from cultivation_life.content_registry import TECHNIQUE_CATALOG, WORLD_SYSTEMS
from cultivation_life.engine import GameEngine
from cultivation_life.models import SectNpc, SectState, Player
from cultivation_life.rules import ensure_technique_set, public_player, technique_scale, raw_external_hp_bonus
from cultivation_life.system.faction_geography import faction_site, can_enter_faction, war_site

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def setup(tmp_path):
    engine = GameEngine(ROOT, tmp_path / "saves")
    gid = engine.create_game("山门验收", "supreme_metal", "dao", 1411)["id"]
    return engine, engine.store.load(gid)


def test_all_existing_factions_have_safe_stable_persisted_sites(setup):
    engine, game = setup
    for sect in game.sects.values():
        first = faction_site(sect)
        assert not first.get("min_realm_index", 0)
        restored = SectState.from_dict(sect.to_dict())
        assert faction_site(restored)["id"] == first["id"]


def test_restricted_foundation_keeps_address_and_filters_recruits(setup):
    engine, game = setup
    site = next(row for row in engine.maps.worlds["human"]["locations"] if row.get("min_realm_index", 0) > 1)
    game.player.realm_index = site["min_realm_index"]
    game.player.faction_id = None
    game.player.location_id = site["id"]
    engine.store.save(game)
    engine.create_faction(game.id, "绝壁剑宗")
    saved = engine.store.load(game.id)
    sect = saved.sects[saved.player.faction_id]
    assert sect.location_id == site["id"]
    assert all(can_enter_faction(sect, npc) for npc in sect.npcs)
    with patch.object(engine, "_recruit_realm_index", return_value=1):
        before = len(sect.npcs)
        assert engine._recruit_sect_npc(sect, saved.player.age, random.Random(1)) is None
        assert len(sect.npcs) == before
    sect.founded_by_player = False
    assert faction_site(sect)["id"] == site["id"], "Succession must not relocate the mountain"


def test_map_war_encounter_has_one_full_quiet_unit_and_stops_at_peace(setup):
    engine, game = setup
    factions = [f for f in game.sects.values() if f.world == "human" and not f.extinct]
    first, second = factions[:2]
    war = engine._start_war(game, "sect", first.id, second.id)
    site = war_site(engine.maps, war)
    assert not site.get("min_realm_index", 0)
    game.player.location_id = site["id"]
    rng = random.Random(1410)
    with patch.object(rng, "random", return_value=0):
        assert engine._maybe_map_war_encounter(game, rng)
        assert game.pending_event["runtime"]["player_defending"]
        assert game.pending_event["runtime"]["faction_id"] in {first.id, second.id}
        engine.store.save(game)
        game = engine.store.load(game.id)
        war = next(row for row in game.wars if row['id'] == war['id'])
        game.pending_event = None
        assert not engine._maybe_map_war_encounter(game, rng)
        game.diplomacy_unit += 1
        assert not engine._maybe_map_war_encounter(game, rng)
        game.diplomacy_unit += 1
        assert engine._maybe_map_war_encounter(game, rng)
        game.pending_event = None
        game.diplomacy_unit += 2
        war["status"] = "peace_ready"
        assert not engine._maybe_map_war_encounter(game, rng)


def test_taiyuan_base_and_saved_level_migrate_together():
    art = copy.deepcopy(TECHNIQUE_CATALOG["TECH_COMMON_GUI"])
    assert art.combat_bonus == 5000
    art.combat_bonus, art.level, art.growth_preference = 800, 7, "balanced"
    player = Player("传承", "supreme_metal", known_techniques=[art])
    ensure_technique_set(player)
    assert art.combat_bonus == 5000 and art.level == 7
    assert art.stat_multiplier("combat_bonus") > 2 * (art.stat_multiplier("opportunity_bonus") - 1) + 1
    shown = public_player(player)["known_techniques"][0]
    assert shown["combat_bonus"] == pytest.approx(art.combat_bonus * technique_scale(art, "combat_bonus"))
    assert shown["growth_name"] == "战斗"


@pytest.mark.parametrize("category,specialty", [("body", "body_breakthrough_bonus"),
    ("divine_sense", "divine_sense_bonus"), ("transformation", "transformation_capacity")])
def test_specialty_growth_has_independent_curve(category, specialty):
    art = copy.deepcopy(next(t for t in TECHNIQUE_CATALOG.values() if t.category == category))
    art.level = 6
    assert art.stat_multiplier(specialty) > art.level_multiplier > art.stat_multiplier("combat_bonus")


def test_support_bias_changes_real_hp_not_only_display():
    art = copy.deepcopy(next(t for t in TECHNIQUE_CATALOG.values() if t.growth_preference == "support"))
    player = Player("辅修", "supreme_metal", support_technique=art, realm_index=3)
    base = raw_external_hp_bonus(player)
    art.level = 4
    assert raw_external_hp_bonus(player) / base == pytest.approx(art.stat_multiplier("hp_bonus"))
    assert art.stat_multiplier("hp_bonus") > art.stat_multiplier("combat_bonus")
