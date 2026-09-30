"""Behavioral regressions for multi-effect control and independent loadouts."""
import copy
import random
from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest

from cultivation_life.models import Item, Technique, SectNpc, Player
from cultivation_life.content_registry import ITEM_CATALOG, TECHNIQUE_CATALOG
from cultivation_life.system.combat.contracts import (
    CombatCapabilities, Combatant, VoisinageDefinition, VoisinageEffect, Intervention, ResourceSupply,
)
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.system.combat_loadout import project_loadout
from cultivation_life.system.cultivation_ranks import npc_golden_light
from test_domain_combat import engine_game


def domain(*effects, **kw):
    data = dict(id='test', name='邻域', attainment='test', required_level=4, strength=100,
                opening_cost=1, upkeep_cost=1, effect='seal', effect_cost=10, effect_power=.2,
                authority=100, effects=effects, max_targets=3)
    data.update(kw)
    return VoisinageDefinition(**data)


def caster(d, **kw):
    data = dict(capacity=100, current=100, resource_tier=2, voisinages=(d,), attainments={'test': 4})
    data.update(kw)
    return CombatCapabilities(**data)


def actor(key, side, caps=None, rank=-1, **kw):
    return Combatant(key, key, side, 100, caps or CombatCapabilities(), cultivation_rank=rank, **kw)


def begin(b, n=1):
    return b.begin_round(n, player_condition=1, enemy_condition=1, player_mp=1, enemy_mp=1)


def test_continuous_dominance_without_active_budget_and_no_body_injury():
    b = VoisinageBattle([actor('player', 'player', caster(domain(), current=3)), actor('enemy', 'enemy')])
    begin(b); frame = begin(b, 2)
    assert frame.relations['enemy']['relation'] == 'dominated'
    assert b.units['enemy'].pressure > 0 and frame.morale_loss['enemy'] > 0
    assert b.units['enemy'].body == 1 and b.units['enemy'].vitality < 1
    assert b.units['player'].current == 0


def test_effect_selection_uses_affordable_declared_alternative():
    d = domain(VoisinageEffect('strike', 50, 1), VoisinageEffect('suppress', 3, .2))
    b = VoisinageBattle([actor('player', 'player', caster(d, current=6)), actor('enemy', 'enemy')])
    begin(b)
    assert b.units['enemy'].vitality == pytest.approx(.8)
    assert b.units['enemy'].body == 1
    assert b.units['player'].current == 1


@pytest.mark.parametrize('purpose,dead', [('kill', True), ('capture', False), ('repel', False)])
def test_two_round_terminal_requires_real_means(purpose, dead):
    d = domain(VoisinageEffect('seal', 2, .2))
    b = VoisinageBattle([actor('player', 'player', caster(d, artifact_tier=2), 101),
                         actor('enemy', 'enemy', CombatCapabilities(ward_tier=2), 89)])
    b.set_objectives(purpose, 'kill')
    begin(b)
    assert b.units['enemy'].vitality == 1
    begin(b, 2)
    assert b.enemy_killed() == dead
    assert b.enemy_suppressed() != dead
    assert b.units['player'].current == 97  # maintenance only, no invented strike charges


def test_seal_only_cannot_kill_golden_body_without_attack_qualification():
    b = VoisinageBattle([actor('player', 'player', caster(domain()), 101),
                         actor('enemy', 'enemy', CombatCapabilities(ward_tier=2), 89)])
    begin(b); begin(b, 2)
    assert not b.enemy_killed() and b.enemy_suppressed()


def test_passive_golden_light_survives_empty_energy_and_does_not_spend_it():
    for energy in (0, 10):
        ward = CombatCapabilities(capacity=10, current=energy, ward_tier=2, ward_cost=100)
        b = VoisinageBattle([actor('player', 'player'), actor('enemy', 'enemy', ward)])
        begin(b)
        assert b.ordinary_damage(.5, 0)[0] == 0
        assert b.units['enemy'].current == energy
        b = VoisinageBattle([actor('player', 'player', CombatCapabilities(artifact_tier=2)), actor('enemy', 'enemy', ward)])
        begin(b)
        assert b.ordinary_damage(.5, 0)[0] == .5
        assert b.units['enemy'].current == energy


@pytest.mark.parametrize('kind', ['resist', 'escape', 'shelter', 'disrupt'])
def test_explicit_intervention_precedes_cost_and_blocks_effect(kind):
    response = Intervention(kind, ('strike',), strength=1000)
    b = VoisinageBattle([actor('player', 'player', caster(domain(VoisinageEffect('strike', 10, 1)))),
                         actor('enemy', 'enemy', CombatCapabilities(interventions=(response,)))])
    begin(b)
    assert b.units['enemy'].body == 1 and b.units['enemy'].vitality == 1
    assert b.units['player'].current == 98
    if kind in {'escape', 'shelter', 'disrupt'}:
        assert not b.units['enemy'].escape_locked


def test_ordinary_artifact_tier_is_not_an_intervention():
    b = VoisinageBattle([actor('player', 'player', caster(domain(VoisinageEffect('strike', 10, 1)))),
                         actor('enemy', 'enemy', CombatCapabilities(artifact_tier=2))])
    begin(b)
    assert b.enemy_killed()


def test_intervention_only_item_does_not_replace_mortal_combat():
    b = VoisinageBattle([actor('player', 'player'), actor('enemy', 'enemy', CombatCapabilities(
        interventions=(Intervention('resist', ('suppress',)),)))])
    assert not b.enabled


def test_isolation_disables_only_artifact_and_expires_with_its_field():
    b = VoisinageBattle([actor('player', 'player', caster(domain(VoisinageEffect('isolate', 2, restriction='artifact')))),
                         actor('enemy', 'enemy', CombatCapabilities(artifact_tier=2))])
    begin(b)
    assert b.attack_tier(b.units['enemy']) == 1
    b.units['player'].suppressed = True
    b.finish_round(player_mp=1, enemy_mp=1)
    assert not b.units['enemy'].escape_locked
    assert b.frame.relations['enemy']['relation'] == 'uncovered'
    assert b.attack_tier(b.units['enemy']) == 2


def test_supply_isolation_stops_next_round_supply():
    b = VoisinageBattle([actor('player', 'player', caster(domain(VoisinageEffect('isolate', 2, restriction='supply')))),
                         actor('enemy', 'enemy', CombatCapabilities(capacity=100, resource_tier=2))],
                        supplies=(ResourceSupply('enemy', 5),))
    begin(b); begin(b, 2)
    assert b.units['enemy'].current == 5


@pytest.mark.parametrize('kind', ['restore_body', 'restore_spirit', 'restore_field'])
def test_restoration_costs_energy_but_never_restores_it(kind):
    d = domain(VoisinageEffect(kind, 3, .2, target='ally'))
    b = VoisinageBattle([actor('player', 'player', caster(d, stance='protect', protect_ids=('ally',))),
                         actor('ally', 'player', caster(domain(), stance='guard'), body_integrity=.5),
                         actor('enemy', 'enemy')])
    ally = b.units['ally']
    ally.pressure, ally.morale, ally.field_strain = .5, 50, .4
    begin(b)
    assert b.units['player'].current == 95
    assert ally.current == 98  # upkeep only; restoration never replenishes it
    if kind == 'restore_body':
        assert ally.body == pytest.approx(.7)
    elif kind == 'restore_spirit':
        assert ally.pressure == pytest.approx(.3) and ally.morale > 50
    else:
        assert ally.field_strain == pytest.approx(.2)


def test_healing_does_not_remove_enemy_dominance_or_resurrect():
    heal = caster(domain(VoisinageEffect('restore_body', 3, .2, target='ally'), strength=1),
                  stance='protect', protect_ids=('ally',))
    b = VoisinageBattle([actor('player', 'player', heal), actor('ally', 'player', body_integrity=.5),
                         actor('enemy', 'enemy', caster(domain(effect_cost=200), target_ids=('ally',)))])
    begin(b)
    assert b.units['ally'].body == pytest.approx(.7)
    assert b.units['ally'].escape_locked
    b.units['ally'].suppressed = True
    begin(b, 2)
    assert b.units['ally'].suppressed


def test_mixed_roster_never_inherits_artifact_qualification():
    b = VoisinageBattle([actor('player', 'player', CombatCapabilities(artifact_tier=2)), actor('ally', 'player'),
                         actor('enemy', 'enemy', CombatCapabilities(ward_tier=2))])
    begin(b)
    assert b.ordinary_damage(.4, 0)[0] == pytest.approx(.2)


def test_loadout_is_persistent_independent_of_treasure_and_resolved_once(monkeypatch):
    sword = Item('audit_sword', '仙剑', force_tier=2)
    book = Technique(id='audit_book', force_tier=2)
    monkeypatch.setitem(ITEM_CATALOG, sword.id, sword)
    monkeypatch.setitem(TECHNIQUE_CATALOG, book.id, book)
    npc = SectNpc('a', 'a', '', 8, 1, 100, None, treasure_item_id=sword.id)
    game = SimpleNamespace(doctrine_state={})
    assert project_loadout(game, npc).artifact_tier == 1
    npc.combat_artifact_id = sword.id
    npc.main_technique_id = book.id
    saved = SectNpc.from_dict(npc.to_dict())
    assert saved.treasure_item_id == sword.id and saved.combat_artifact_id == sword.id
    caps = project_loadout(game, saved)
    assert caps.artifact_tier == caps.technique_tier == 2
    saved.combat_artifact_id = None
    assert project_loadout(game, saved).artifact_tier == 1
    assert saved.treasure_item_id == sword.id


def test_npc_golden_light_uses_body_not_cultivation():
    npc = SectNpc('a', 'a', '', 9, 9, 100, None)
    assert not npc_golden_light(npc)
    npc.immortal_body_level = 14
    assert not npc_golden_light(npc)
    npc.immortal_body_level = 15
    assert npc_golden_light(npc)
    npc.realm_index = 8
    assert npc_golden_light(npc)


@pytest.mark.parametrize('bad', [{'kind': 'restore_energy', 'target': 'self'},
                                {'kind': 'isolate'}, {'kind': 'restore_body'},
                                {'kind': 'strike', 'defense': 'anything'}])
def test_unsupported_semantics_are_rejected(bad):
    with pytest.raises(ValueError):
        VoisinageEffect(cost=1, **bad)


def test_roundtrip_effect_definition_is_data_only():
    d = domain(VoisinageEffect('restore_body', 3, target='self'), VoisinageEffect('strike', 4))
    assert VoisinageDefinition(**asdict(d)) == d


def test_simultaneous_breaches_are_order_independent():
    d = domain(VoisinageEffect('strike', 3, .4), incursion=500, stability=1)
    rows = [actor('player', 'player', caster(d)), actor('enemy', 'enemy', caster(d))]
    snapshots = []
    for roster in (rows, list(reversed(rows))):
        b = VoisinageBattle(roster); begin(b)
        snapshots.append({k: (s.current, s.vitality) for k, s in b.units.items()})
    assert snapshots[0] == snapshots[1]


def test_body_restoration_reaches_player_hp_and_stored_energy(engine_game, monkeypatch):
    from cultivation_life.content_registry import WORLD_SYSTEMS
    from cultivation_life.rules import max_hp
    engine, game = engine_game
    d = domain(VoisinageEffect('restore_body', 3, .2, target='self'))
    monkeypatch.setitem(WORLD_SYSTEMS, 'transcendent_combat', {'voisinages': [asdict(d)]})
    game.player.transcendence = dict(capacity=100, current=100, conversion=1,
        voisinage_ids=['test'], attainments={'test': 4}, plan={'stance': 'guard'})
    game.player.hp = max_hp(game.player) * .4
    before = game.player.hp
    engine._combat(game, dict(target_name='切磋者', target_power=1, target_realm_index=4,
                              combat_type='cultivator', max_rounds=1), False, random.Random(1))
    assert before < game.player.hp <= max_hp(game.player)
    assert game.player.transcendence['current'] == 95
    engine.store.save(game)
    assert engine.store.load(game.id).player.hp == game.player.hp


def test_background_uses_imitation_ledger_and_nonlethal_objective():
    from cultivation_life.system.combat.contracts import CapabilitySource
    from cultivation_life.system.combat.npc_battle import resolve_npc_engagement
    d = domain(VoisinageEffect('suppress', 3, 1), id='spirit:test')
    npc = SectNpc('a', 'a', '', 9, 1, 1000, None, world='spirit',
                  transcendence=dict(capacity=100, current=90, conversion=1))
    enemy = SectNpc('b', 'b', '', 8, 1, 1000, None, world='spirit')
    result = resolve_npc_engagement([(npc, 1)], [(enemy, 10**8)], {}, random.Random(1),
        sources={npc.id: CapabilitySource((d,), {'test': 4})}, attacker_objective='capture')
    assert result.suppressed == ('b',) and not result.killed and enemy.alive
    assert npc.transcendence['current'] == 90
    assert npc.transcendence['imitation']['current'] == 17
    assert enemy.wounds == 0  # suppression/pressure alone are not bodily damage


def test_npc_body_restoration_updates_wounds_in_both_callers(engine_game, monkeypatch):
    from cultivation_life.system.combat.contracts import CapabilitySource
    from cultivation_life.system.combat.npc_battle import resolve_npc_engagement
    from cultivation_life.content_registry import WORLD_SYSTEMS
    engine, game = engine_game
    d = domain(VoisinageEffect('restore_body', 3, .2, target='self'))
    config = {'voisinages': [asdict(d)]}
    npc = SectNpc('healer', 'healer', '', 8, 1, 1000, None, wounds=4, immortal_body_level=20,
        transcendence=dict(capacity=100, current=100, conversion=1, voisinage_ids=['test'],
                           attainments={'test': 4}, plan={'stance': 'guard'}))
    original = copy.deepcopy(npc)
    enemy = SectNpc('enemy', 'enemy', '', 8, 1, 1000, None)
    resolve_npc_engagement([(npc, 100)], [(enemy, 100)], config, random.Random(1), max_rounds=1)
    assert npc.wounds < 4
    game.notable_npcs[original.id] = original
    monkeypatch.setitem(WORLD_SYSTEMS, 'transcendent_combat', config)
    engine._combat(game, dict(npc_id=original.id, target_name=original.name, target_power=100,
                              target_realm_index=8, combat_type='cultivator', max_rounds=1), False, random.Random(1))
    assert original.wounds == npc.wounds


def test_actual_main_artifact_qualifies_but_same_treasure_does_not(engine_game):
    from cultivation_life.engine.combat_capabilities import bind_capabilities
    from cultivation_life.system.combat_system import BattleUnit
    from cultivation_life.content_registry import WORLD_SYSTEMS
    _, game = engine_game
    npc = SectNpc('armed', 'armed', '', 8, 1, 1000, None, treasure_item_id='heavenly_river_sword_embryo')
    game.notable_npcs[npc.id] = npc
    target = dict(npc_id=npc.id, target_name=npc.name, target_power=100, target_realm_index=8)
    roster = [BattleUnit('player', 'player', 'player', 100, 4)]
    binding = bind_capabilities(game, roster, target, WORLD_SYSTEMS['transcendent_combat'])
    assert binding.battle.units[npc.id].unit.capabilities.artifact_tier == 1
    npc.combat_artifact_id = 'heavenly_river_sword_embryo'
    binding = bind_capabilities(game, roster, target, WORLD_SYSTEMS['transcendent_combat'])
    assert binding.battle.units[npc.id].unit.capabilities.artifact_tier == 2


def test_special_escape_cannot_be_undone_by_ordinary_pursuit():
    from cultivation_life.system.combat_system import PlayerCombatSystem, BattleUnit
    p = Player('a', 'none', realm_index=9)
    b = VoisinageBattle([actor('player', 'player', caster(domain(), artifact_tier=2), 101),
                        actor('enemy-0', 'enemy', CombatCapabilities(interventions=(
                            Intervention('escape', ('execute',)),)), 89)])
    result = PlayerCombatSystem.resolve(p, [BattleUnit('player', 'a', 'player', 10**9, 9)],
        {'target_name': 'b', 'target_power': 1, 'target_realm_index': 8}, True, random.Random(1),
        current_hp_ratio=1, current_mp_ratio=1, phases=b)
    assert b.units['enemy-0'].escaped and not result.kill_ready and not result.capture_ready
