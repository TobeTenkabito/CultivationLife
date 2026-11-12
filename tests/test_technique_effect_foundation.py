"""Frozen generation and real paid battle paths, including adversarial replay."""
import copy
import json
import random
from dataclasses import replace
from unittest.mock import patch

import pytest

from cultivation_life.content_registry import CONTENT_DOCUMENTS
from cultivation_life.models import Technique
from cultivation_life.technique_effect_schema import validate_effect, validate_loadout
from cultivation_life.technique_effect_generation import generate_effect, attach_effect
from cultivation_life.system.combat.contracts import Combatant, CombatCapabilities
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.system.combat.trials import dump_battle, load_battle
from cultivation_life.system.doctrine.generation import generate
from cultivation_life.system.doctrine.fusion import compile_manual


def effect(kind='guard', **changes):
    result = dict(version=1, generator_version=1, kind=kind, trigger='opening', delivery='immediate',
                  strength_bp=100 if kind in {'guard', 'frugal', 'recover'} else 800,
                  cost_bp=200, cooldown=2, uses=3, duration=2, refund_bp=2000 if kind == 'frugal' else 0)
    return validate_effect(result | changes)


def manual(kind='guard', identity='test-book', **changes):
    return dict(id=identity, name='试验功法', level=1, effect=effect(kind, **changes))


def actor(identity, side, books=(), *, current=100., capacity=100., integrity=1., linked=False):
    return Combatant(identity, identity, side, 100., integrity=integrity,
        capabilities=CombatCapabilities(current=current, capacity=capacity, usable_capacity=capacity,
            resource_tier=2, resource_link='legacy_mp' if linked else 'independent', technique_effects=books))


def battle(*books, **kwargs):
    return VoisinageBattle([actor('player', 'player', books, **kwargs), actor('enemy-0', 'enemy')])


def begin(b, number):
    b.begin_round(number, player_condition=1-b.ordinary_loss('player'), enemy_condition=1-b.ordinary_loss('enemy'),
                  player_mp=b.mp_ratio('player', 1), enemy_mp=b.mp_ratio('enemy', 1), rng=random.Random(7))
    return b.semantic_ordinary_start()


def test_seed_stream_keeps_old_catalog_exact_and_fixed_doctrines_fixed():
    config = CONTENT_DOCUMENTS['doctrines.json']
    powers = {r: 10**r for r in range(9, 13)}
    with patch('cultivation_life.technique_effect_generation.attach_effect', return_value=False):
        old = generate(442, config, powers)
    new = generate(442, config, powers)
    assert new == generate(442, config, powers)
    stripped = copy.deepcopy(new)
    for d in stripped['definitions'].values():
        for book in d['manuals']:
            book.pop('combat_effect')
            book.pop('description')
    assert stripped == old
    other = generate(443, config, powers)
    for key, d in new['definitions'].items():
        if d['fixed']:
            assert d == other['definitions'][key]
    recipes = [book['combat_effect'] for d in new['definitions'].values() for book in d['manuals']]
    assert len({json.dumps(e, sort_keys=True) for e in recipes}) > 20
    assert {e['kind'] for e in recipes} == {'guard', 'strike', 'breach', 'recover', 'frugal'}


def test_frozen_effect_never_rerolls_and_model_detaches_input():
    book = dict(id='celestial:x:manual:1', doctrine_id='celestial:x', growth_preference='main')
    assert attach_effect(book, 1, feature='fortify', theme='water')
    before = copy.deepcopy(book)
    assert not attach_effect(book, 999, feature='execution', theme='fire')
    assert book == before
    value = effect()
    t = Technique(combat_effect=value, description='原书描述')
    value['cost_bp'] = 9999
    assert t.combat_effect['cost_bp'] == 200
    assert Technique(**t.__dict__) == t


def test_fusion_gets_own_seeded_effect_without_multiplying_strength():
    config = CONTENT_DOCUMENTS['doctrines.json']
    d = next(d for d in generate(117, config, {r: 10**r for r in range(9, 13)})['definitions'].values() if len(d['manuals']) >= 6)
    before = copy.deepcopy(d)
    fused = compile_manual(117, d, config['words'])
    assert fused == compile_manual(117, d, config['words'])
    assert fused['id'].endswith(':concordance')
    validate_effect(fused['combat_effect'])
    assert d == before


@pytest.mark.parametrize('change', [dict(kind=[]), dict(trigger='exec'), dict(strength_bp=999999),
    dict(cost_bp=True), dict(uses=100), dict(version=2), dict(refund_bp=1), dict(payload='print(1)')])
def test_malformed_rule_rejected(change):
    with pytest.raises(ValueError):
        Technique(combat_effect=effect() | change)


def test_duplicate_book_rejected_not_double_applied():
    with pytest.raises(ValueError):
        validate_loadout([manual(), manual()])


def test_guard_is_paid_once_and_finite_across_multiple_hits():
    b = battle(manual())
    begin(b, 1)
    assert b.units['player'].current == pytest.approx(98)
    b.semantic_ordinary_start()
    assert b.units['player'].current == pytest.approx(98)
    _, received = b.ordinary_damage(0, .006)
    assert received == pytest.approx(0)
    _, received = b.ordinary_damage(0, .006)
    assert received == pytest.approx(.002)
    record = next(iter(b.techniques.records.values()))
    assert record['used'] == 1 and record['paid'] == pytest.approx(2)
    assert sum(p['remaining'] for p in record['packets']) == pytest.approx(0)


@pytest.mark.parametrize('current,capacity', [(0., 100.), (.5, 100.), (0., 0.)])
def test_no_resource_no_free_effect(current, capacity):
    b = battle(manual(), current=current, capacity=capacity)
    begin(b, 1)
    assert b.units['player'].current == current
    assert not next(iter(b.techniques.records.values()))['used']
    assert b.ordinary_damage(0, .1)[1] == pytest.approx(.1)


def test_split_preserves_one_budget_and_round_trip_does_not_reset():
    b = battle(manual(delivery='split'))
    begin(b, 1)
    assert b.ordinary_damage(0, .1)[1] == pytest.approx(.095)
    resumed = load_battle(json.loads(json.dumps(dump_battle(b))))
    for obj in (b, resumed):
        begin(obj, 2)
        assert obj.ordinary_damage(0, .1)[1] == pytest.approx(.095)
        assert obj.units['player'].current == pytest.approx(98)
    # Existing empty tuple/list fields normalize through JSON independently of
    # this component. Compare the persisted representation, including receipts.
    assert json.loads(json.dumps(dump_battle(b))) == json.loads(json.dumps(dump_battle(resumed)))


@pytest.mark.parametrize('kind', ['guard', 'frugal'])
def test_large_real_balances_survive_payment_rounding_and_resume(kind):
    capacity = 12345678901234.56
    b = battle(manual(kind, cost_bp=250), current=capacity, capacity=capacity)
    begin(b, 1)
    b.ordinary_damage(0, .002)
    resumed = load_battle(json.loads(json.dumps(dump_battle(b))))
    assert resumed.units['player'].current == b.units['player'].current
    assert resumed.techniques.dump() == b.techniques.dump()


def test_refund_requires_actual_prevention_and_cannot_repeat_receipt():
    b = battle(manual('frugal'))
    begin(b, 1)
    b.ordinary_damage(0, .002)
    assert b.units['player'].current == pytest.approx(98.4)
    b.ordinary_damage(0, .002)
    assert b.units['player'].current == pytest.approx(98.4)
    r = next(iter(b.techniques.records.values()))
    assert r['refunded'] == pytest.approx(.4)


def test_overkill_cannot_become_refundable_shield_damage():
    b = battle(manual('frugal'), integrity=.02)
    begin(b, 1)
    b.ordinary_damage(0, .5)
    assert b.units['player'].current == pytest.approx(98)
    assert not next(iter(b.techniques.records.values()))['refunded']


def test_delayed_recovery_cannot_resurrect_or_exceed_initial_integrity():
    b = battle(manual('recover', delivery='delayed'), integrity=.8)
    begin(b, 1)
    assert b.units['player'].current == 100  # No missing initial state, no payment.
    b.ordinary_damage(0, .05)
    begin(b, 2)
    assert b.units['player'].vitality == pytest.approx(.75)
    assert b.units['player'].current == pytest.approx(98)
    begin(b, 3)
    assert b.units['player'].vitality == pytest.approx(.76)
    b.units['player'].vitality = 0
    begin(b, 4)
    assert b.units['player'].vitality == 0


def test_attacker_effects_add_from_same_baseline_and_stay_tier_gated():
    b = battle(manual('strike', 'one'), manual('strike', 'two'))
    begin(b, 1)
    dealt, _ = b.ordinary_damage(.1, 0)
    assert dealt == pytest.approx(.116)  # .1 * (1 + .08 + .08), not .1 * 1.08**2.
    c = battle(manual('strike'))
    enemy = c.units['enemy-0']
    enemy.unit = replace(enemy.unit, capabilities=replace(enemy.unit.capabilities, ward_tier=2))
    begin(c, 1)
    assert c.units['player'].current == 100
    assert c.ordinary_damage(.1, 0)[0] == 0


def test_retaliation_needs_real_damage_not_blocked_hits():
    b = battle(manual('strike', trigger='after_hurt'))
    begin(b, 1)
    assert b.units['player'].current == 100
    b.ordinary_damage(0, .02)
    begin(b, 2)
    assert b.units['player'].current == pytest.approx(98)
    assert b.ordinary_damage(.1, 0)[0] == pytest.approx(.108)


def test_enemy_uses_same_rules_and_original_resource_pool():
    b = VoisinageBattle([actor('player', 'player'), actor('enemy-0', 'enemy', (manual(),))])
    begin(b, 1)
    assert b.units['enemy-0'].current == pytest.approx(98)
    assert b.units['player'].current == 100
    assert b.ordinary_damage(.1, 0)[0] == pytest.approx(.09)


def test_background_npc_battle_commits_paid_cost_to_original_npc():
    from cultivation_life.models import SectNpc
    from cultivation_life.system.combat.contracts import CapabilitySource
    from cultivation_life.system.combat.npc_battle import resolve_npc_engagement
    resource = dict(version=1, capacity=100, current=100, conversion=1, force_tier=2, ward_tier=1)
    a = SectNpc('a', '甲', '', 9, 1, 1000, None, transcendence=copy.deepcopy(resource))
    b = SectNpc('b', '乙', '', 9, 1, 1000, None, transcendence=copy.deepcopy(resource))
    result = resolve_npc_engagement([(a, 1000)], [(b, 1000)], {}, random.Random(11), max_rounds=1,
        sources={'a': CapabilitySource(technique_effects=(manual(),))})
    assert a.transcendence['current'] == pytest.approx(98)
    assert b.transcendence['current'] == 100
    assert result.rounds[0]['voisinage']['technique_effects']['receipts']


def test_linked_pool_payment_precedes_other_mana_expenses():
    b = battle(manual(), linked=True)
    begin(b, 1)
    ordinary_mp = b.mp_ratio('player', 1)
    assert ordinary_mp == pytest.approx(.98)
    ordinary_mp -= .1
    b.sync_resources(player_mp=ordinary_mp, enemy_mp=1)
    assert b.units['player'].current == pytest.approx(88)


@pytest.mark.parametrize('kind', ['guard', 'strike', 'breach', 'recover', 'frugal'])
def test_real_player_driver_pays_and_reports_bounded_effects(kind):
    from test_domain_combat import fight
    caps = CombatCapabilities(current=100, capacity=100, usable_capacity=100, resource_tier=2,
                              resource_link='legacy_mp', technique_effects=(manual(kind),))
    result, phases = fight(caps, CombatCapabilities(), rounds=4)
    record = next(iter(phases.techniques.records.values()))
    assert 1 <= record['used'] <= 3 and record['paid'] == pytest.approx(2 * record['used'])
    assert 0 <= phases.units['player'].current < 100
    assert any(row.get('voisinage', {}).get('technique_effects', {}).get('receipts') for row in result.rounds)
    assert result.mp_loss_ratio >= (record['paid'] - record['refunded']) / 100 - .0001


def test_unlimited_configuration_is_not_cut_off_at_128_books():
    books = [manual(identity=f'book-{i}') for i in range(225)]
    assert len(validate_loadout(books)) == 225


def test_actual_game_acquisition_projection_save_and_npc_identity(tmp_path):
    from pathlib import Path
    from cultivation_life.engine import GameEngine
    from cultivation_life.models import SectNpc
    from cultivation_life.rules import learn_technique, assign_technique
    from cultivation_life.system.technique_effect_provider import project
    from cultivation_life.system.npc_techniques import learn
    engine = GameEngine(Path(__file__).resolve().parents[1], tmp_path)
    made = engine.create_game('效果验收', 'supreme_metal', 'dao', seed=7142, preset_id='true_immortal')
    game = engine.store.load(made['id'])
    definition = next(iter(game.doctrine_state['definitions'].values()))
    frozen = copy.deepcopy(definition['manuals'][0])
    book = Technique(**frozen)
    learn_technique(game.player, book)
    assign_technique(game.player, book, 'main')
    game.player.immortal_power_converted = True
    from cultivation_life.system.duel_techniques import select
    assign_technique(game.player, copy.deepcopy(book), 'combat')
    select(game.player, book.id)
    first = project(game, game.player, player=True)
    assert any(r['id'] == book.id and r['effect'] == frozen['combat_effect'] for r in first)
    game.player.combat_techniques.append(copy.deepcopy(book))
    assert sum(r['id'] == book.id for r in project(game, game.player, player=True)) == 1
    engine.store.save(game)
    loaded = engine.store.load(game.id)
    assert loaded.doctrine_state['definitions'][definition['id']]['manuals'][0] == frozen
    assert loaded.player.technique.description == book.description
    assert project(loaded, loaded.player, player=True) == project(game, game.player, player=True)
    npc = SectNpc('original-npc', '同道', '同道', 9, 1, 100, None, world='celestial', spirit_root='supreme_metal')
    npc.transcendence = {'conversion': 1}
    learn(npc, book, level=3, slot='main')
    npc.duel_technique_ids = [book.id]
    projected = project(game, npc)
    assert projected[0]['id'] == book.id and projected[0]['level'] == 3
    assert projected[0]['effect'] == book.combat_effect
    npc.world = 'human'
    assert not project(game, npc)
    assert npc.technique_levels[book.id] == 3  # Leaving only suppresses the projection.


@pytest.mark.parametrize('mutation', ['paid', 'refund', 'packets', 'missing', 'source', 'free',
    'duplicate', 'split_budget', 'time', 'receipt_type', 'baseline_bool'])
def test_corrupt_resume_rejected(mutation):
    b = battle(manual(delivery='split'))
    begin(b, 1)
    snapshot = dump_battle(b)
    runtime = snapshot['technique_runtime']
    r = next(iter(runtime['records'].values()))
    if mutation == 'paid': r['paid'] = float('nan')
    elif mutation == 'refund': r['refunded'] = 999
    elif mutation == 'packets': r['packets'][0]['remaining'] = 1
    elif mutation == 'missing': snapshot.pop('technique_runtime')
    elif mutation == 'free':
        r['paid'] = r['receipts']['1']['paid'] = 0
    elif mutation == 'duplicate': r['packets'][1] = copy.deepcopy(r['packets'][0])
    elif mutation == 'split_budget':
        r['packets'][0]['remaining'] = .009
        r['packets'][1]['remaining'] = .001
    elif mutation == 'time': r['packets'][0]['expires'] -= 1
    elif mutation == 'receipt_type': r['packets'][0]['receipt'] = []
    elif mutation == 'baseline_bool': runtime['initial_state']['player'] = True
    else: runtime['records']['fake-owner'] = copy.deepcopy(r)
    with pytest.raises(ValueError):
        load_battle(snapshot)
