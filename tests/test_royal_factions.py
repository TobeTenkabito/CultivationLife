import copy
from pathlib import Path

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.models import SectNpc
from cultivation_life.system import asura, asura_court, asura_factions
from cultivation_life.system.upper_institutions import account


@pytest.fixture
def throne(tmp_path):
    engine = GameEngine(Path(__file__).resolve().parents[1], tmp_path)
    made = engine.create_game(
        "王权", "supreme_metal", "demonic", 1581, preset_id="asura_upper"
    )
    engine.upper_institution_action(made["id"], "join")
    game = engine._load(made["id"])
    state = account(game)
    asura_court.change_rank(game, state, 5)
    state.update(treasury=10000000, unit=100)
    state["court"]["protected_until"] = 0
    game.pending_event = game.active_trial = None
    engine.store.save(game)
    return engine, game, state


def test_factions_optional_and_public_queries_pure(throne, monkeypatch):
    engine, game, state = throne
    before = copy.deepcopy(game.to_dict())
    for _ in range(3):
        view = asura_court.public(game, state)
        assert len(view["factions"]["rows"]) == 3
        assert len(view["policy_categories"]) == 3
    assert before == game.to_dict()
    monkeypatch.setattr(asura, "enabled", lambda: False)
    assert asura_court.public(game, state)["factions"] is None
    with pytest.raises(ValueError, match="DLC"):
        asura_factions.act(game, state, "royal_tribute", "material:spirit_stone", {})
    asura_factions.tick(game, state, {})
    assert before == game.to_dict()


def test_targeted_policy_preserves_pool_and_rejection_is_atomic(throne):
    engine, game, _ = throne
    result = engine.upper_institution_action(
        game.id, "faction_decree", "restrain:blood_clans"
    )
    rows = result["upper_institution"]["court"]["factions"]["rows"]
    assert sum(r["external"] for r in rows) == pytest.approx(100)
    assert all(5 <= r["external"] <= 70 for r in rows)
    saved = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError, match="间隔"):
        engine.upper_institution_action(
            game.id, "faction_decree", "patronize:war_hosts"
        )
    assert engine.store._path(game.id).read_bytes() == saved


def test_imbalance_uses_existing_representative_and_defeat_swaps_seats(throne):
    _, game, state = throne
    roster = asura_court.people(game)
    npc = next(n for n in roster.values() if asura_court.present(n))
    faction = asura_factions.faction_of(npc.id)
    for row in state["court"]["factions"]["rows"]:
        row["loyalty"] = 0 if row["id"] == faction else 100
    for _ in range(4):
        state["unit"] += 1
        asura_factions.tick(game, state, roster)
    challenge = state["court"]["challenge"]
    assert (
        challenge
        and challenge["npc_id"] in roster
        and challenge["faction_id"] == faction
    )
    representative = roster[challenge["npc_id"]]
    asura_court.change_rank(game, state, 4, opponent=representative.id)
    holders = state["court"]["holders"]
    assert holders["5"] == representative.id and holders["4"] == "player"
    assert len(set(holders.values())) == 5
    asura_factions.settle_duel(state, challenge, False)
    assert state["court"]["factions"]["pressure"] == 0


@pytest.mark.parametrize("kind", ["item", "crafting", "formation"])
def test_tribute_materials_cover_base_sources_only(throne, kind):
    engine, game, _ = throne
    rows = asura_factions.materials()
    assert not any("guixu" in r["id"] or r["id"].startswith("SPATIAL_") for r in rows)
    row = next(r for r in rows if r["kind"] == kind)
    engine.upper_institution_action(game.id, "royal_tribute", "material:" + row["id"])
    p = engine.store.load(game.id).player
    if kind == "item":
        assert any(i.id == row["id"] and i.quantity > 0 for i in p.inventory)
    else:
        assert any(
            i["material_id"] == row["id"] for i in getattr(p, kind + "_materials")
        )
    with pytest.raises(ValueError):
        engine.upper_institution_action(
            game.id, "royal_tribute", "material:guixu_asura_fake"
        )


def test_real_opportunity_debited_and_prisoner_keeps_identity(throne):
    engine, game, _ = throne
    donor = SectNpc(
        "tribute_donor",
        "献贡者",
        "",
        10,
        9,
        100,
        None,
        world="asura",
        cultivation_progress=1000,
        spirit_root="supreme_metal",
    )
    victim = SectNpc(
        "tribute_victim",
        "被俘者",
        "",
        1,
        1,
        20,
        100,
        world="asura",
        spirit_root="supreme_metal",
    )
    game.world_npcs.update({donor.id: donor, victim.id: victim})
    before = game.player.opportunity
    engine.store.save(game)
    engine.upper_institution_action(game.id, "royal_tribute", "opportunity:" + donor.id)
    loaded = engine.store.load(game.id)
    assert loaded.player.opportunity == before + 1000
    assert loaded.world_npcs[donor.id].cultivation_progress == 0
    engine.upper_institution_action(game.id, "royal_tribute", "prisoner:" + donor.id)
    loaded = engine.store.load(game.id)
    assert any(p["id"] == victim.id for p in loaded.player.prisoners)
    assert loaded.inactive_npcs[victim.id].alive
    assert loaded.inactive_npcs[victim.id].roster_state == "held"
