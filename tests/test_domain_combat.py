"""Behavioral coverage of the voisinage/ordinary boundary and resource ownership."""
import copy
import random
import shutil
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import pytest

from cultivation_life.models import Player, SectNpc
from cultivation_life.system.combat.contracts import (
    Combatant, CombatCapabilities, VoisinageDefinition, ResourceSupply, resolve_capabilities,
)
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.system.combat_system import BattleUnit, PlayerCombatSystem


def voisinage(**changes):
    values = dict(id="test_field", name="测试仙域", attainment="test_attainment",
                  required_level=4, strength=100, opening_cost=120, upkeep_cost=40,
                  effect="suppress", effect_cost=20)
    values.update(changes)
    return VoisinageDefinition(**values)


def capability(*, definition=None, current=800, stance="press", **changes):
    values = dict(capacity=1000, current=current, force_tier=2, ward_tier=2,
                  resource_tier=2, stance=stance,
                  voisinages=(definition or voisinage(),), attainments={"test_attainment": 4})
    values.update(changes)
    return CombatCapabilities(**values)


def unit(key, side, caps=None, power=1000):
    return Combatant(key, key, side, power, caps or CombatCapabilities())


def begin(battle, n=1):
    return battle.begin_round(n, player_condition=1, enemy_condition=1, player_mp=1, enemy_mp=1)


def fight(player_caps, enemy_caps, *, player_power=1000, enemy_power=1000, rounds=5):
    p = Player("测试者", "none", realm_index=4, layer=1)
    units = [BattleUnit("player", p.name, "player", player_power, 4)]
    phases = VoisinageBattle([unit("player", "player", player_caps, player_power),
                          unit("enemy-0", "enemy", enemy_caps, enemy_power)])
    result = PlayerCombatSystem.resolve(
        p, units, {"target_name": "测试敌人", "target_power": enemy_power,
                   "target_realm_index": 4, "max_rounds": rounds}, True, random.Random(42),
        current_hp_ratio=1, current_mp_ratio=1, phases=phases,
    )
    return result, phases


def test_attainment_and_resource_are_independent_gates():
    d = voisinage()
    state = dict(conversion=1, capacity=1000, current=800, voisinage_ids=[d.id],
                 attainments={"test_attainment": 3})
    assert not resolve_capabilities(state, {d.id: d}).voisinages
    state["attainments"]["test_attainment"] = 4
    state["current"] = 100
    caps = resolve_capabilities(state, {d.id: d})
    assert caps.voisinages == (d,)
    battle = VoisinageBattle([unit("player", "player", caps), unit("enemy", "enemy")])
    assert begin(battle).relations["enemy"]["relation"] == "uncovered"
    assert battle.units["player"].current == 100


def test_unconverted_voisinage_grant_cannot_activate():
    caps = capability(resource_tier=1)
    battle = VoisinageBattle([unit("player", "player", caps), unit("enemy", "enemy")])
    begin(battle)
    assert battle.fields == []


def test_voisinage_control_bypasses_power_shortcut_and_ordinary_rng():
    with patch.object(PlayerCombatSystem, "_wave", side_effect=AssertionError("ordinary exchange was called")):
        result, battle = fight(capability(), CombatCapabilities(), enemy_power=1_000_000)
    assert result.outcome == "victory"
    assert result.rounds[0]["initiative"] == "voisinage"
    assert result.rounds[0]["voisinage"]["relations"]["enemy-0"]["relation"] == "dominated"
    assert battle.units["player"].current == 620
    assert not result.kill_ready  # suppression is not a free kill


def test_enemy_voisinage_suppresses_player_without_claiming_death_or_escape():
    result, _ = fight(CombatCapabilities(), capability(), player_power=1_000_000)
    assert result.outcome == "defeat"
    assert result.voisinage_controlled
    assert not result.voisinage_lethal
    assert not result.retreat_impossible


def test_matched_voisinages_call_conventional_exchange_and_keep_round_state():
    result, battle = fight(capability(), capability(), rounds=2)
    assert result.rounds[0]["initiative"] in {"player", "enemy"}
    assert result.rounds[0]["voisinage"]["relations"]["player"]["relation"] == "contested"
    assert result.enemy_combat_state < result.enemy_combat_state_max
    assert battle.units["player"].current == 800 - 120 - len(result.rounds) * 40
    assert len(result.rounds) > 1


def test_tier_gate_has_no_minimum_damage_and_does_not_drain_ward():
    caps = capability(voisinages=(), stance="off")
    battle = VoisinageBattle([unit("player", "player", caps), unit("enemy", "enemy", power=1e9)])
    begin(battle)
    dealt, received = battle.ordinary_damage(0, .4)
    assert (dealt, received) == (0, 0)
    assert battle.units["player"].current == 800
    result, _ = fight(caps, CombatCapabilities(), enemy_power=1e9, rounds=1)
    assert result.player_combat_state == result.player_combat_state_max
    assert result.outcome == "stalemate"


def test_finite_ward_absorption_is_not_also_body_damage():
    defender = capability(current=10, voisinages=(), ward_cost=100)
    attacker = capability(voisinages=())
    battle = VoisinageBattle([unit("player", "player", attacker), unit("enemy", "enemy", defender)])
    begin(battle)
    dealt, _ = battle.ordinary_damage(.25, 0)
    assert dealt == pytest.approx(.15)
    assert battle.units["enemy"].current == 0


def test_mortal_allies_do_not_inherit_immortal_attack_tier():
    immortal = capability(voisinages=())
    battle = VoisinageBattle([unit("player", "player", immortal), unit("mortal", "player", power=9000),
                          unit("enemy", "enemy", immortal)])
    begin(battle)
    dealt, _ = battle.ordinary_damage(.4, 0)
    assert dealt == pytest.approx(.04)


def test_coverage_is_per_target_and_ally_protection_grants_no_attack_tier():
    guardian = capability(definition=voisinage(max_targets=3), stance="protect", protect_ids=("ally",))
    enemy = capability(definition=voisinage(max_targets=3))
    battle = VoisinageBattle([unit("player", "player", guardian), unit("ally", "player"),
                          unit("outside", "player"), unit("enemy", "enemy", enemy)])
    frame = begin(battle)
    assert frame.relations["ally"]["protector"] == "player"
    assert frame.relations["ally"]["relation"] != "dominated"
    assert frame.relations["outside"]["relation"] == "dominated"
    assert battle.units["outside"].suppressed
    assert battle.units["ally"].unit.capabilities.force_tier == 1


def test_resource_failure_shrinks_coverage_before_abandoning_caster():
    caps = capability(current=160, definition=voisinage(extra_target_cost=50), stance="press")
    battle = VoisinageBattle([unit("player", "player", caps), unit("enemy", "enemy")])
    begin(battle)
    assert battle.fields[0].protects == ("player",)
    assert battle.fields[0].targets == ()
    assert battle.units["player"].current == 0


def test_guard_and_off_never_impose_hostile_coverage():
    for stance in ("guard", "off"):
        battle = VoisinageBattle([unit("player", "player", capability(stance=stance)), unit("enemy", "enemy")])
        assert begin(battle).relations["enemy"]["relation"] == "uncovered"


def test_roster_order_does_not_decide_control_or_ward_eligibility():
    units = [unit("player", "player", capability(definition=voisinage(strength=160))),
             unit("enemy", "enemy", capability()), unit("ally", "player")]
    outcomes = []
    for roster in (units, list(reversed(units))):
        battle = VoisinageBattle(roster)
        begin(battle)
        battle.ordinary_damage(.2, .2)
        outcomes.append({k: (s.current, s.vitality, s.suppressed) for k, s in battle.units.items()})
    assert outcomes[0] == outcomes[1]


def test_unaffordable_effect_does_not_get_free_ordinary_attack_on_dominated_target():
    caps = capability(current=160)
    battle = VoisinageBattle([unit("player", "player", caps), unit("enemy", "enemy")])
    frame = begin(battle)
    assert frame.relations["enemy"]["relation"] == "dominated"
    assert not frame.ordinary
    assert battle.ordinary_damage(.4, .4) == (0, 0)


def test_unknown_attainment_voisinage_does_not_mutate_or_invent_mastery():
    state = dict(capacity=1000, current=800, conversion=1, voisinage_ids=["future_voisinage"], attainments={})
    original = copy.deepcopy(state)
    assert resolve_capabilities(state, {}).voisinages == ()
    assert state == original


def test_npc_transcendence_roundtrips_without_battle_fields():
    npc = SectNpc("test", "测试", "", 9, 1, 1000, None,
                  transcendence={"version": 1, "conversion": .5, "capacity": 1000, "current": 450,
                                 "attainments": {"future": 2}})
    restored = SectNpc.from_dict(npc.to_dict())
    assert restored.transcendence == npc.transcendence
    assert "active_voisinage" not in restored.transcendence


@pytest.mark.parametrize("changes", [{"strength": float("nan")}, {"upkeep_cost": 0},
                                     {"effect": "python"}, {"max_targets": 0}])
def test_definitions_reject_invalid_rules(changes):
    with pytest.raises(ValueError):
        voisinage(**changes)


def state(*, current=800, **changes):
    value = dict(version=1, capacity=1000, current=current, conversion=1,
                 force_tier=2, ward_tier=2, voisinage_ids=["test_field"],
                 attainments={"test_attainment": 4})
    value.update(changes)
    return value


@pytest.fixture
def engine_game(tmp_path, monkeypatch):
    from cultivation_life.engine import GameEngine
    from cultivation_life.content_registry import WORLD_SYSTEMS
    from cultivation_life.rules import max_hp, max_mp
    shutil.copytree(Path(__file__).resolve().parents[1] / "content", tmp_path / "content")
    engine = GameEngine(tmp_path)
    game = engine.store.load(engine.create_game("领域测试", "none", "dao", 552, preset_id="core")["id"])
    game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
    monkeypatch.setitem(WORLD_SYSTEMS, "transcendent_combat", {"voisinages": [asdict(voisinage())]})
    return engine, game


def test_npc_resource_writeback_uses_authoritative_owner_and_survives_reload(engine_game):
    engine, game = engine_game
    npc = SectNpc("voisinage_npc", "领域修士", "", 9, 1, 1000, None, transcendence=state())
    game.notable_npcs[npc.id] = npc
    target = dict(npc_id=npc.id, target_name=npc.name, target_power=1,
                  target_realm_index=9, combat_type="cultivator")
    result, _ = engine._combat(game, target, False, random.Random(1))
    assert result == "controlled"
    assert npc.transcendence["current"] == 560
    engine.store.save(game)
    restored = engine.store.load(game.id)
    assert restored.notable_npcs[npc.id].transcendence["current"] == 560
    # A repeated fight pays a new opening cost, rather than refilling the NPC.
    engine._combat(restored, target, False, random.Random(1))
    assert restored.notable_npcs[npc.id].transcendence["current"] == 320


def test_cached_npc_resource_writeback_does_not_target_a_temporary_shell(engine_game):
    engine, game = engine_game
    npc = SectNpc("cached", "过客", "", 9, 1, 1000, None, transcendence=state())
    game.encounter_npc_cache.append({"id": npc.id, "npc": npc.to_dict()})
    engine._combat(game, dict(npc_id=npc.id, target_name=npc.name, target_power=1000,
                             target_realm_index=9, combat_type="cultivator"), False, random.Random(1))
    assert game.encounter_npc_cache[0]["npc"]["transcendence"]["current"] == 560


def test_linked_player_resource_is_not_double_debited_or_waived_by_story(engine_game):
    engine, game = engine_game
    game.player.transcendence = state(resource_link="legacy_mp")
    before = game.player.mp
    result, _ = engine._combat(game, dict(target_name="敌人", target_power=1e12,
                                        target_realm_index=8, combat_type="story", mp_loss_scale=0),
                               False, random.Random(1))
    assert result == "victory"
    assert game.player.mp == pytest.approx(before - 180)
    assert game.player.transcendence["current"] == 800  # not a second MP pool


def test_voisinage_capture_cannot_be_undone_by_ordinary_capture_roll(engine_game):
    engine, game = engine_game
    game.player.transcendence = state()
    result, _ = engine._combat(game, dict(target_name="敌人", target_power=1e12,
                                        target_realm_index=8, combat_type="cultivator", capture=True),
                               False, random.Random(1))
    assert result == "captured"
    assert game.player.prisoners[-1]["name"] == "敌人"


def test_voisinage_kill_cannot_be_undone_by_ordinary_pursuit_roll(engine_game, monkeypatch):
    from cultivation_life.content_registry import WORLD_SYSTEMS
    engine, game = engine_game
    monkeypatch.setitem(WORLD_SYSTEMS, "transcendent_combat", {
        "voisinages": [asdict(voisinage(effect="strike", effect_power=1))]})
    game.player.transcendence = state()
    npc = SectNpc("victim", "敌人", "", 8, 1, 1000, None)
    game.notable_npcs[npc.id] = npc
    result, _ = engine._combat(game, dict(npc_id=npc.id, target_name=npc.name, target_power=1e12,
                                        target_realm_index=8, combat_type="cultivator"),
                               True, random.Random(1))
    assert result == "killed"
    assert not npc.alive
    assert game.player.alive


def test_npc_only_engagement_obeys_voisinage_and_persists_consumption():
    from cultivation_life.system.combat.npc_battle import resolve_npc_engagement
    weak = SectNpc("weak", "弱者", "", 9, 1, 1000, None, transcendence=state())
    strong = SectNpc("strong", "强者", "", 8, 1, 1000, None)
    result = resolve_npc_engagement([(weak, 1)], [(strong, 1e12)],
                                    {"voisinages": [asdict(voisinage())]}, random.Random(1))
    assert result.outcome == "victory"
    assert result.killed == ("strong",)
    assert not strong.alive
    assert len(result.rounds) == 2
    assert weak.transcendence["current"] == 560


def test_npc_legacy_path_does_not_consume_randomness_or_write_state():
    from cultivation_life.system.combat.npc_battle import resolve_npc_engagement
    a = SectNpc("a", "甲", "", 9, 1, 1000, None)
    b = SectNpc("b", "乙", "", 9, 1, 1000, None)
    rng = random.Random(2)
    before = rng.getstate()
    assert resolve_npc_engagement([(a, 1000)], [(b, 1000)], {}, rng) is None
    assert rng.getstate() == before
    assert a.transcendence is None


def test_supply_can_enable_voisinage_and_stops_when_source_is_lost():
    battle = VoisinageBattle([unit("player", "player", capability(current=100)),
                           unit("furnace", "player"), unit("enemy", "enemy")],
                          supplies=(ResourceSupply("player", 100, "furnace"),))
    frame = begin(battle)
    assert frame.relations["enemy"]["relation"] == "dominated"
    assert battle.units["player"].current == 20
    battle.units["furnace"].suppressed = True
    begin(battle, 2)
    assert battle.units["player"].current == 20
    assert battle.fields == []


def test_supply_respects_partial_conversion_and_never_restores_unconverted_power():
    caps = capability(current=100, voisinages=(), usable_capacity=200)
    battle = VoisinageBattle([unit("player", "player", caps), unit("enemy", "enemy")],
                          supplies=(ResourceSupply("player", 1000),))
    begin(battle)
    assert battle.units["player"].current == 200


def test_battle_modules_do_not_import_engine_or_global_content():
    import ast
    root = Path(__file__).resolve().parents[1] / "cultivation_life" / "system" / "combat"
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert "engine" not in (node.module or "")
                assert "content_registry" not in (node.module or "")
            elif isinstance(node, ast.Import):
                assert all("engine" not in alias.name and "content_registry" not in alias.name for alias in node.names)


def test_voisinage_suppression_does_not_award_a_beast_kill(engine_game):
    engine, game = engine_game
    game.player.transcendence = state()
    result, summary = engine._combat(game, dict(target_name="妖兽", target_power=1e12,
                                               target_realm_index=8, combat_type="beast",
                                               success_threshold=100), True, random.Random(1))
    assert result == "victory_controlled"
    assert "没有形成实际击杀" in summary


def test_npc_field_war_does_not_reroll_casualties_after_voisinage_control(engine_game, monkeypatch):
    engine, game = engine_game
    a = SectNpc("caster", "仙域修士", "", 9, 1, 1000, None, transcendence=state())
    b = SectNpc("opponent", "敌将", "", 9, 1, 1000, None)
    monkeypatch.setattr(engine, "_available_warriors", lambda game, war, side: [a] if side == "attacker" else [b])
    monkeypatch.setattr(engine, "_npc_power", lambda npc: 1 if npc is a else 1e12)
    war = {"morale": {"attacker": 100, "defender": 100}, "war_score": 0}
    engine._resolve_field_attack(game, war, "attacker", random.Random(1),
                                 {"attacker": {"modifier": 1}, "defender": {"modifier": 1}})
    assert war["voisinage_suppressed"] == [b.id]
    assert b.alive
    assert a.transcendence["current"] == 620
    assert war["morale"]["defender"] < 100


def test_destroying_a_supply_artifact_does_not_award_cultivator_kill(engine_game, monkeypatch):
    from cultivation_life.content_registry import WORLD_SYSTEMS
    engine, game = engine_game
    monkeypatch.setitem(WORLD_SYSTEMS, "transcendent_combat", {
        "voisinages": [asdict(voisinage(effect="strike", effect_power=1))]})
    game.player.transcendence = state()
    before_fame, before_karma = game.player.fame, game.player.karma
    result, _ = engine._combat(game, dict(target_name="仙炉", target_power=1000,
                                         target_realm_index=8, combat_type="story",
                                         members=[{"name": "仙炉", "power": 1000,
                                                   "realm_index": 8, "kind": "artifact"}]),
                               True, random.Random(1))
    assert result == "victory"
    assert (game.player.fame, game.player.karma) == (before_fame, before_karma)
