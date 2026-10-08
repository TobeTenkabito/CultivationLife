"""Progression boundaries and atomic, lock-aware Asura rerolls."""
import copy
import random
from pathlib import Path
from unittest.mock import patch

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.rules import breakthrough_opportunity_required, opportunity_required, public_player
from cultivation_life.system import asura

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def ready(tmp_path):
    engine = GameEngine(ROOT, tmp_path)
    shown = engine.create_game('修罗修复验收', 'supreme_metal', 'demonic', 1562, preset_id='asura_upper')
    game = engine.store.load(shown['id'])
    game.pending_event = None
    game.player.asura_cultivation.update(conversion=5, body_level=0, souls=10000,
        route='asura', level=9, domain_rank=1, domain_name='试域', veins={'9': 3})
    game.player.opportunity = 10 * opportunity_required(game.player)
    engine.store.save(game)
    return engine, game


@pytest.mark.parametrize('world,realm,path', [('human',1,'demonic'), ('true_demon',8,'demonic'),
                                           ('asura',8,'demonic'), ('asura',9,'dao')])
def test_locked_system_is_not_exposed_or_callable(ready, world, realm, path):
    engine, game = ready
    p = game.player
    p.world, p.realm_index, p.path = world, realm, path
    p.location_id = engine.maps.normalize_location(world, None)
    engine.store.save(game)
    assert asura.public(game) == {'available': False}
    engine._load(game.id)  # Complete ordinary save migration before measuring action atomicity.
    before = engine.store._path(game.id).read_bytes()
    for action in ('train_body','purify','learn_power','reroll_power','lock_power'):
        with pytest.raises(ValueError):
            engine.asura_action(game.id, action)
    assert engine.store._path(game.id).read_bytes() == before


def test_reserve_survives_load_gain_and_terminal_realm(ready):
    engine, game = ready
    saved = engine._load(game.id)
    before = saved.player.opportunity
    assert before == game.player.opportunity
    from cultivation_life.rules import opportunity_multiplier
    gain = 12345 * opportunity_multiplier(saved.player)
    engine._add_opportunity(saved.player, 12345)
    assert saved.player.opportunity == pytest.approx(before + gain)
    saved.player.realm_index, saved.player.layer = 12, 9
    engine._resolve_breakthroughs(saved, random.Random(1))
    engine.store.save(saved)
    result = engine.present(engine._load(game.id))
    assert result['player']['opportunity_unbounded']
    assert result['player']['opportunity'] == pytest.approx(before + gain)


def test_disabled_dlc_keeps_ordinary_cap_and_hides_ui(ready):
    engine, game = ready
    with patch.object(asura, 'enabled', return_value=False):
        saved = engine._load(game.id)
        assert saved.player.opportunity == opportunity_required(saved.player)
        assert not public_player(saved.player)['opportunity_unbounded']
        assert asura.public(saved) == {'available': False}
        assert breakthrough_opportunity_required(saved.player) == opportunity_required(saved.player)


def test_reserve_survives_sealed_return_to_lower_world(ready):
    engine, game = ready
    p = game.player
    p.sealed_cultivation = {'upper_world':'asura','realm_index':9,'layer':1}
    p.world, p.realm_index = 'true_demon', 8
    before = p.opportunity
    engine._resolve_breakthroughs(game, random.Random(1))
    assert public_player(p)['opportunity_unbounded']
    assert p.opportunity == before


@pytest.mark.parametrize('realm,base', [(9,18000),(10,90000),(11,120000),(12,150000)])
def test_breakthrough_fees_match_immortal_counterpart(ready, realm, base):
    _, game = ready
    p = game.player
    p.realm_index = realm
    for layer in (1,3,9):
        p.layer = layer
        fee = breakthrough_opportunity_required(p)
        assert fee == round(base * (1 + .12 * (layer - 1)))
        immortal = copy.deepcopy(p)
        immortal.world, immortal.path = 'celestial', 'dao'
        assert fee == breakthrough_opportunity_required(immortal)
        assert fee < opportunity_required(p)


def test_body_quote_matches_debit_and_does_not_scale_with_realm(ready):
    engine, game = ready
    assert asura.public(game)['body_cost'] == 6000
    before = game.player.opportunity
    shown = engine.asura_action(game.id, 'train_body')
    assert shown['player']['opportunity'] == before - 6000
    assert shown['asura']['body_level'] == 1
    assert shown['asura']['body_cost'] == 12000
    game.player.realm_index = 12
    game.player.asura_cultivation['body_level'] = 19
    assert asura.body_cost(game.player) == 120000


def test_breakthrough_enabled_at_reduced_fee_and_retains_excess(ready):
    engine, game = ready
    game.player.opportunity = 20000
    engine.store.save(game)
    shown = engine.present(engine._load(game.id))
    assert shown['breakthrough']['enabled']
    assert shown['breakthrough']['opportunity_cost'] == 18000
    with patch.object(engine, '_breakthrough_chance', return_value={'final':1.0}):
        engine.breakthrough(game.id)
    p = engine.store.load(game.id).player
    assert p.layer == 2 and p.opportunity == 2000


def populate(engine, game):
    s = game.player.asura_cultivation
    rng = random.Random(45)
    s['powers'] = [asura.generate_rule(rng, f'asura:power:{i}') for i in range(6)]
    engine.store.save(game)
    return copy.deepcopy(s['powers'])


def test_reroll_updates_all_unlocked_rules_and_persists_locks(ready):
    engine, game = ready
    old = populate(engine, game)
    engine.asura_action(game.id, 'lock_power', old[1]['id'])
    engine.asura_action(game.id, 'lock_power', old[4]['id'])
    result = engine.asura_action(game.id, 'reroll_power')
    assert result['asura']['souls'] == 9600
    saved = engine._load(game.id).player.asura_cultivation
    assert saved['locked_power_ids'] == [old[1]['id'],old[4]['id']]
    for i, rule in enumerate(saved['powers']):
        assert rule['id'] == old[i]['id'] and rule['source_id'] == old[i]['source_id']
        assert (rule == old[i]) == (i in (1,4))
    assert engine.asura_action(game.id,'reroll_power')['asura']['souls'] == 9200
    engine.asura_action(game.id,'lock_power',old[1]['id'])
    assert engine.asura_action(game.id,'reroll_power')['asura']['souls'] == 9000


@pytest.mark.parametrize('kind', ['empty','all_locked','poor','invalid_lock','single_target'])
def test_rejected_reroll_does_not_spend_or_change_rng(ready, kind):
    engine, game = ready
    powers = populate(engine, game)
    s = game.player.asura_cultivation
    if kind == 'empty': s['powers'] = []
    if kind == 'all_locked': s['locked_power_ids'] = [r['id'] for r in powers]
    if kind == 'poor': s['souls'] = 99
    engine.store.save(game)
    engine._load(game.id)  # Complete ordinary save migration before measuring action atomicity.
    before = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError):
        engine.asura_action(game.id, 'lock_power' if kind=='invalid_lock' else 'reroll_power',
                            'missing' if kind=='invalid_lock' else powers[0]['id'] if kind=='single_target' else '')
    assert engine.store._path(game.id).read_bytes() == before
