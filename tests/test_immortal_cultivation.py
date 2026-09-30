"""Gameplay boundaries: resources, discovery, commentary, pity and old saves."""
import copy
import random
from pathlib import Path
from unittest.mock import patch

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState, Technique, SectNpc
from cultivation_life.content_registry import CONTENT_DOCUMENTS, WORLD_SYSTEMS
from cultivation_life.rules import add_item, learn_technique, opportunity_required, breakthrough_opportunity_required
from cultivation_life.system.immortal_system import item_quantity
from cultivation_life.system.doctrine.cultivation import attempt, chance, prerequisites, vein_cost
from cultivation_life.system.doctrine.daomen import discover
from cultivation_life.system.doctrine.provider import battle_sources

ROOT = Path(__file__).resolve().parents[1]
RULES = CONTENT_DOCUMENTS['doctrines.json']['cultivation']


@pytest.fixture
def prepared(tmp_path):
    engine = GameEngine(ROOT, tmp_path)
    made = engine.create_game('问道', 'supreme_metal', 'dao', 7410, preset_id='true_immortal')
    game = engine.store.load(made['id'])
    game.pending_event = None
    game.heavenly_court['open_election'] = None
    game.player.next_tribulation_age = None
    game.doctrine_state['player']['annotations'] = {}
    game.player.opportunity = 10**10
    add_item(game.player, 'immortal_trace', 10000)
    add_item(game.player, 'spirit_stone', 10**8)
    d = next(iter(game.doctrine_state['definitions'].values()))
    learn_technique(game.player, Technique(**copy.deepcopy(d['manuals'][0])))
    game.doctrine_state['player']['progress'][d['id']] = {'level': 0, 'experience': 0}
    engine.store.save(game)
    return engine, game, d


def test_true_immortal_time_and_unbounded_reserve(prepared):
    engine, game, _ = prepared
    assert WORLD_SYSTEMS['time_units']['9'] == 100
    before = game.player.opportunity
    engine._resolve_breakthroughs(game, random.Random(1))
    assert game.player.opportunity == before > opportunity_required(game.player)
    shown = engine.present(game)['player']
    assert shown['opportunity_unbounded'] and shown['time_unit_years'] == 100
    assert game.player.realm_index == 9 and game.player.layer == 1


def test_every_three_veins_requires_manual_layer_and_body_20_for_major(prepared):
    engine, game, _ = prepared
    before = game.player.opportunity
    with patch('cultivation_life.system.immortal_system.decode_rng', side_effect=lambda *a: random.Random(1)), \
            patch.object(engine, '_breakthrough_chance', return_value={'final': 1}):
        for layer in range(1, 10):
            for _ in range(3):
                shown = engine.immortal_action(game.id, 'open_vein')
                assert shown['player']['layer'] == layer
            assert shown['doctrines']['veins']['opened'] == layer * 3
            with pytest.raises(ValueError, match='手动'):
                engine.immortal_action(game.id, 'open_vein')
            if layer == 9:
                with pytest.raises(ValueError, match='20'):
                    engine.immortal_action(game.id, 'breakthrough')
                saved = engine.store.load(game.id)
                saved.player.immortal_body = {'level': 20}
                engine.store.save(saved)
            shown = engine.immortal_action(game.id, 'breakthrough')
    assert shown['player']['realm_index'] == 9
    assert shown['pending_event']['id'] == 'EVT_IMMORTAL_TRIAL_HUMAN_DECLINE'
    shown = engine.choose(game.id, 'fight')
    assert shown['player']['realm_index'] == 10 and shown['player']['layer'] == 1
    assert 0 < shown['player']['opportunity'] < before
    assert shown['doctrines']['veins']['opened'] == 0
    assert shown['doctrines']['veins']['next_cost'] == vein_cost(10, 0, RULES)


def test_vein_cost_is_linear_across_realm_boundary():
    costs = [vein_cost(9 + n // 27, n % 27, RULES) for n in range(108)]
    for a, b in zip(costs, costs[1:]):
        assert b['opportunity'] - a['opportunity'] == RULES['vein_opportunity_step']
        assert b['traces'] - a['traces'] == RULES['vein_trace_step']


@pytest.mark.parametrize('balance,enabled', [(17999, False), (18000, True)])
def test_immortal_manual_fee_matches_buttons_and_actual_payment(prepared, balance, enabled):
    engine, game, _ = prepared
    game.player.immortal_veins['9'] = 3
    game.player.opportunity = balance
    engine.store.save(game)
    shown = engine.get_game(game.id)
    assert shown['doctrines']['veins']['breakthrough_cost'] == 18000
    assert shown['doctrines']['veins']['can_breakthrough'] is enabled
    assert shown['breakthrough']['enabled'] is enabled
    if not enabled:
        with pytest.raises(ValueError, match='瓶颈'):
            engine.immortal_action(game.id, 'breakthrough')
        assert engine.store.load(game.id).player.opportunity == balance
        return
    with patch.object(engine, '_breakthrough_chance', return_value={'final': 1}):
        shown = engine.immortal_action(game.id, 'breakthrough')
    assert shown['player']['layer'] == 2
    assert engine.store.load(game.id).player.opportunity == 0


def test_cheaper_manual_fee_still_requires_veins_and_retains_failure_rules(prepared):
    engine, game, _ = prepared
    game.player.opportunity = 18000
    game.player.immortal_veins['9'] = 2
    engine.store.save(game)
    with pytest.raises(ValueError, match='仙脉'):
        engine.immortal_action(game.id, 'breakthrough')
    # The first layer is an existing pity-eligible minor bottleneck.
    game.player.immortal_veins['9'] = 3
    fee = breakthrough_opportunity_required(game.player)
    game.player.opportunity = fee
    key = engine._minor_pity_key(game.player)
    engine.store.save(game)
    with patch.object(engine, '_breakthrough_chance', return_value={'final': 0}):
        engine.immortal_action(game.id, 'breakthrough')
    saved = engine.store.load(game.id).player
    assert saved.layer == 1 and saved.immortal_veins['9'] == 3
    assert saved.opportunity == fee * WORLD_SYSTEMS['breakthrough']['minor_failure_retention']
    assert saved.breakthrough_pity[key] == 1


def test_manual_fee_is_separate_from_reward_scale_and_other_worlds(prepared):
    _, game, _ = prepared
    p = game.player
    assert opportunity_required(p) == 1800000
    for realm, base in zip(range(9, 13), (18000, 90000, 120000, 150000)):
        p.realm_index = realm
        for layer in range(1, 10):
            p.layer = layer
            assert breakthrough_opportunity_required(p) == round(base * (1 + .12 * (layer - 1)))
        for world in ('asura', 'nether', 'reincarnation', 'spirit'):
            p.world = world
            assert breakthrough_opportunity_required(p) == opportunity_required(p)
        p.world = 'celestial'
    p.realm_index = 8
    assert breakthrough_opportunity_required(p) == opportunity_required(p)


def test_major_trial_uses_new_fee_but_preserves_body_gate(prepared):
    engine, game, _ = prepared
    game.player.layer = 9
    game.player.immortal_veins['9'] = 27
    game.player.immortal_body = {'level': 19}
    game.player.opportunity = 35280
    engine.store.save(game)
    with pytest.raises(ValueError, match='20'):
        engine.immortal_action(game.id, 'breakthrough')
    assert engine.store.load(game.id).player.opportunity == 35280
    game.player.immortal_body['level'] = 20
    engine.store.save(game)
    shown = engine.immortal_action(game.id, 'breakthrough')
    assert shown['player']['realm_index'] == 9
    assert shown['pending_event']['id'] == 'EVT_IMMORTAL_TRIAL_HUMAN_DECLINE'
    assert engine.store.load(game.id).player.opportunity == 0


def test_vein_opportunity_budget_matches_trace_accumulation(prepared):
    from scripts.calibrate_immortal_veins import budgets
    from cultivation_life.content_registry import ACTIONS
    from cultivation_life.rules import opportunity_multiplier
    _, game, _ = prepared
    annual = sum(ACTIONS['cultivate']['opportunity']) / 2 * opportunity_multiplier(game.player)
    for realm in range(9, 13):
        budget = budgets(realm, RULES)
        time_for_traces = budget['traces'] / RULES['trace_gain_chance']
        # Include every failed attempt. Neither ledger should be an order of
        # magnitude slower than the other before investing in better techniques.
        ratio = budget['opportunity'] / annual / time_for_traces
        assert 0.7 <= ratio <= 1.2


def test_repriced_vein_keeps_old_progress_and_failure_pity(prepared):
    engine, game, _ = prepared
    game.player.immortal_veins['9'] = 1
    game.player.immortal_vein_pity['9:2'] = 2
    game.player.opportunity = 9000
    game.player.immortal_traces = 8
    engine.store.save(game)
    with patch('cultivation_life.system.immortal_system.decode_rng') as rng:
        rng.return_value = random.Random(2)  # .956 > .85 + .10: fail once.
        shown = engine.immortal_action(game.id, 'open_vein')
    saved = engine.store.load(game.id).player
    assert saved.opportunity == 0 and saved.immortal_traces == 0
    assert saved.immortal_veins['9'] == 1 and saved.immortal_vein_pity['9:2'] == 3
    assert shown['doctrines']['veins']['next_cost']['opportunity'] == 9000


def test_insufficient_resources_cannot_partially_pay(prepared):
    engine, game, _ = prepared
    game.player.immortal_traces = 0
    engine.store.save(game)
    before = engine.store.load(game.id).player.to_dict()
    with pytest.raises(ValueError, match='不足'):
        engine.immortal_action(game.id, 'open_vein')
    assert engine.store.load(game.id).player.to_dict() == before


def test_elapsed_time_alone_does_not_award_traces(prepared):
    engine, game, _ = prepared
    start = game.player.immortal_traces
    engine._finish_doctrine_action(game, 'immortal_trace_gather', 100)
    assert game.player.immortal_traces == start


def test_manual_and_annotation_both_required(prepared):
    engine, game, d = prepared
    with pytest.raises(ValueError, match='注解'):
        engine.doctrine_action(game.id, 'study', doctrine_id=d['id'])
    record = game.doctrine_state['player']
    record['progress'][d['id']]['level'] = 1
    record['annotations'][d['id']] = [2]
    engine.store.save(game)
    with pytest.raises(ValueError, match='功法'):
        engine.doctrine_action(game.id, 'study', doctrine_id=d['id'])


@pytest.mark.parametrize('target,step', [(n, .05 if n <= 3 else .04 if n <= 6 else .02) for n in range(1, 10)])
def test_every_level_has_increasing_pity_and_eventual_guarantee(prepared, target, step):
    _, game, d = prepared
    p = {'level': target - 1, 'experience': 0}
    key = d['id']
    origin = key if target >= 5 else None
    prior = chance(p, RULES)
    assert attempt(p, d, 100000, origin, RULES, .999999) == 'failed'
    assert chance(p, RULES) == pytest.approx(min(1, prior + step))
    assert p['experience'] == 0
    for _ in range(50):
        result = attempt(p, d, 100000, origin, RULES, .999999)
        if result == 'success':
            break
    assert p['level'] == target and p['attempts'] <= 50


def test_commentary_is_permanent_and_failure_does_not_reveal_future(prepared):
    engine, game, d = prepared
    record = game.doctrine_state['player']
    record['annotations'][d['id']] = [1]
    record['study_target'] = d['id']
    with patch('cultivation_life.system.doctrine_system.rng_for') as rng:
        rng.return_value.random.return_value = .99
        engine._finish_doctrine_action(game, 'doctrine_study', 100)
    assert record['annotations'][d['id']] == [1]
    row = next(r for r in engine._public_doctrines(game)['rows'] if r['id'] == d['id'])
    assert row['level'] == 0 and len(row['stages']) == 1
    assert row['chance'] == pytest.approx(.90)
    engine.store.save(game)
    assert engine.get_game(game.id)['doctrines']['rows'][0]['chance'] == pytest.approx(.90)


def test_roster_only_reveals_discovered_actual_npcs(prepared):
    engine, game, d = prepared
    before = len(game.notable_npcs)
    key = d['id']
    record = game.doctrine_state['player']
    record['explore_target'] = key
    assert engine._public_doctrines(game)['rows'][0]['peers'] == []
    engine._finish_doctrine_action(game, 'daomen_explore', 99)
    assert len(game.notable_npcs) == before
    engine._finish_doctrine_action(game, 'daomen_explore', 1)
    row = engine._public_doctrines(game)['rows'][0]
    assert len(row['peers']) == 1 and len(game.notable_npcs) == before + 1
    peer = row['peers'][0]
    assert peer['id'] in game.notable_npcs
    engine.store.save(game)
    with pytest.raises(ValueError, match='尚未结识'):
        engine.doctrine_action(game.id, 'annotation', doctrine_id=key, npc_id='undiscovered')
    shown = engine.doctrine_action(game.id, 'annotation', doctrine_id=key, npc_id=peer['id'])
    assert shown['doctrines']['rows'][0]['has_annotation']
    with pytest.raises(ValueError, match='无需重复'):
        engine.doctrine_action(game.id, 'annotation', doctrine_id=key, npc_id=peer['id'])


def test_peer_can_teach_manual_before_doctrine_advances(prepared):
    engine, game, d = prepared
    words = CONTENT_DOCUMENTS['doctrines.json']['words']
    for _ in range(2):
        npc = discover(game, d['id'], d, WORLD_SYSTEMS['transcendent_combat'], words)
    engine.store.save(game)
    result = engine.doctrine_action(game.id, 'teach_manual', doctrine_id=d['id'], npc_id=npc.id, manual_id=d['manuals'][0]['id'])
    row = result['doctrines']['rows'][0]
    assert row['manual_level'] == 1 and row['level'] == 0
    from cultivation_life.rules import technique_copy_count, upgrade_known_technique
    saved = engine.store.load(game.id)
    assert technique_copy_count(saved.player, d['manuals'][0]['id'], 1) >= 1
    assert upgrade_known_technique(saved.player, d['manuals'][0]['id']) == 2


def test_voisinage_training_switches_one_active_source_and_preserves_growth(prepared):
    engine, game, first = prepared
    second = list(game.doctrine_state['definitions'].values())[1]
    learn_technique(game.player, Technique(**copy.deepcopy(second['manuals'][0])))
    record = game.doctrine_state['player']
    for d in (first, second):
        record['progress'][d['id']] = {'level':4, 'experience':0}
    record['active'] = first['id']
    before = battle_sources(game, {'player':game.player})['player'].voisinages[0]
    engine.store.save(game)
    engine.immortal_action(game.id, 'train_voisinage', doctrine_id=first['id'], axis='stability')
    after = engine.store.load(game.id)
    field = battle_sources(after, {'player':after.player})['player'].voisinages[0]
    assert field.stability == pytest.approx(before.stability * 1.03)
    assert field.incursion == before.incursion
    engine.doctrine_action(game.id, 'activate', doctrine_id=second['id'])
    engine.doctrine_action(game.id, 'activate', doctrine_id=first['id'])
    saved = engine.store.load(game.id)
    assert len(battle_sources(saved, {'player':saved.player})['player'].voisinages) == 1
    assert saved.doctrine_state['player']['voisinage_training'][first['id']]['stability'] == 1


def test_old_domain_save_migrates_without_changing_ability_id(prepared):
    _, game, d = prepared
    data = game.to_dict()
    data.pop('voisinage_schema')
    stage = data['doctrine_state']['definitions'][d['id']]['stages'][3]
    stage['domain'] = stage.pop('voisinage')
    stage['domain']['id'] = 'legacy:domain:stable-id'
    data['player']['transcendence'] = {'version':1, 'domain_ids':['legacy:domain:stable-id']}
    data['last_combat_report'] = {'rounds':[{'initiative':'domain','domain':{'fields':[]}}]}
    loaded = GameState.from_dict(data)
    assert loaded.player.transcendence['voisinage_ids'] == ['legacy:domain:stable-id']
    assert loaded.doctrine_state['definitions'][d['id']]['stages'][3]['voisinage']['id'] == 'legacy:domain:stable-id'
    assert loaded.last_combat_report['rounds'][0]['initiative'] == 'voisinage'
    assert loaded.to_dict()['voisinage_schema'] == 1


def test_failed_lv5_still_binds_only_one_origin(prepared):
    engine, game, first = prepared
    second = list(game.doctrine_state['definitions'].values())[1]
    learn_technique(game.player, Technique(**copy.deepcopy(second['manuals'][0])))
    record = game.doctrine_state['player']
    for d in (first, second):
        record['progress'][d['id']] = {'level':4, 'experience':650}
        record['annotations'][d['id']] = [5]
        next(t for t in game.player.known_techniques if t.doctrine_id == d['id']).level = 5
    engine.store.save(game)
    with patch('cultivation_life.system.doctrine_system.rng_for') as rng:
        rng.return_value.random.return_value = .9999
        engine.doctrine_action(game.id, 'origin', doctrine_id=first['id'], confirm_origin=True)
    saved = engine.store.load(game.id).doctrine_state['player']
    assert saved['origin'] == first['id']
    assert saved['progress'][first['id']]['level'] == 4
    assert saved['progress'][first['id']]['failures']['5'] == 1
    with pytest.raises(ValueError, match='唯一'):
        engine.doctrine_action(game.id, 'origin', doctrine_id=second['id'], confirm_origin=True)


def test_legacy_scripted_npc_grant_is_not_overwritten_by_doctrine(prepared):
    _, game, _ = prepared
    npc = SectNpc('scripted', '阵主', '', 9, 1, 10000, None, world='celestial',
                  transcendence={'version':1, 'conversion':1, 'domain_ids':['plot-ward']})
    assert battle_sources(game, {npc.id:npc}) == {}
    assert 'doctrine' not in npc.transcendence
