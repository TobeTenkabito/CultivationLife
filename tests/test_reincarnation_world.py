import copy
import random
from pathlib import Path
from unittest.mock import patch
import pytest

from test_buddhist_dharma import setup
from cultivation_life.content_registry import ContentRegistry, CONTENT_DOCUMENTS, WORLD_SYSTEMS
from cultivation_life.rules import max_hp, max_mp, opportunity_required
from cultivation_life.system.faction_geography import faction_site
from cultivation_life.system.path_modifiers import modifier


ROOT = Path(__file__).resolve().parents[1]


def test_base_world_catalog_complete_without_any_dlc(tmp_path):
    content = ContentRegistry.load(ROOT / "content", tmp_path / "no-dlc")
    assert content.world_systems["world_profiles"]["reincarnation"]["enabled"]
    region = content.loaded_documents["maps.json"]["worlds"]["reincarnation"]
    assert len(region["locations"]) == 28
    locations = {row["id"]: row for row in region["locations"]}
    seen = {region["default"]}
    for _ in range(len(locations)):
        for route in region["routes"]:
            if route["from"] in seen or route["to"] in seen:
                seen.update([route["from"], route["to"]])
    assert seen == set(locations)
    factions = [row for row in content.faction_definitions.values() if row["world"] == "reincarnation"]
    assert len(factions) == 4
    assert content.faction_definitions['reincarnation_hall']['kind']=='institution'
    for row in factions:
        assert not locations[row["location_id"]].get("min_realm_index", 0)
    goods = [row for row in content.market_goods if row["world"] == "reincarnation"]
    assert len(goods) >= 20
    assert not any(row["content_id"].startswith("guixu_") for row in goods)
    assert any(row["kind"] == "technique" for row in goods)
    assert any(row["content_id"] == "reincarnation_lotus_seed" for row in goods)
    for file in ["formations.json", "crafting.json"]:
        assert {row["tier"] for row in content.loaded_documents[file]["materials"] if row["world"] == "reincarnation"} == set(range(1, 13))


@pytest.mark.parametrize("path", ["dao", "ghost"])
def test_base_hell_ascension_available_with_dharma_disabled(setup, path):
    engine, game, _ = setup
    game.player.path = path
    game.player.world = "hell"; game.player.location_id = engine.maps.default_location("hell")
    game.player.realm_index = 8; game.player.layer = 9
    game.player.opportunity = opportunity_required(game.player)
    game.player.hp = max_hp(game.player); game.player.mp = max_mp(game.player)
    engine.store.save(game)
    with patch.dict(CONTENT_DOCUMENTS["buddhist_way.json"]["settings"], enabled=False):
        view = engine.begin_celestial_ascension(game.id)
        saved = engine._load(game.id)
        assert saved.active_trial["destination"] == "reincarnation"
        assert all(e.startswith("EVT_REINCARNATION_ASCENSION_") for e in saved.active_trial["event_ids"])
        saved.active_trial["step_index"] = 8
        result, _ = engine._resolve_celestial_ascension_step(saved, "ascension_thunder_3", random.Random(1))
        assert result == "trial_completed"
        assert saved.player.world == "reincarnation" and saved.player.path == path
        assert saved.player.realm_index == 9
        assert saved.player.lifespan is None
        engine._ensure_market(saved, random.Random(3))
        assert saved.market_world == "reincarnation" and saved.market_offers
        assert len([s for s in saved.sects.values() if s.world == "reincarnation"]) == 4


def test_old_save_adds_world_factions_and_keeps_existing_deaths(setup):
    engine, game, _ = setup
    old = next(s for s in game.sects.values() if s.world == "human")
    old.npcs[0].alive = False
    dead_id = old.npcs[0].id
    game.sects = {key: row for key, row in game.sects.items() if row.world != "reincarnation"}
    engine.store.save(game)
    migrated = engine._load(game.id)
    new = [s for s in migrated.sects.values() if s.world == "reincarnation"]
    assert len(new) == 4
    assert all(not faction_site(s).get("min_realm_index", 0) for s in new)
    assert not engine._find_npc(migrated, dead_id).alive


def test_local_root_manual_is_usable_in_reincarnation(setup):
    engine, game, _ = setup
    from cultivation_life.rules import add_item
    game.player.realm_index = 9
    game.player.world = "reincarnation"; game.player.location_id = "reincarnation_well"
    add_item(game.player, "reincarnation_root_thunder")
    engine.store.save(game)
    engine.use_item(game.id, "reincarnation_root_thunder")
    assert "thunder" in engine._load(game.id).player.additional_roots
