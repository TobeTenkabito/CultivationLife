"""Resource accounting, retry persistence and player capability gates."""
import copy
import random
from unittest.mock import patch

import pytest

from test_immortal_cultivation import prepared
from cultivation_life.models import Player, GameState, Item
from cultivation_life.rules import add_item, max_hp, max_mp, intrinsic_resource_breakdown
from cultivation_life.system.ghost_system import canonical_intrinsic_hp, canonical_intrinsic_mp
from cultivation_life.system.immortal_cultivation import grant_trace_chance, vein_probability, body_probability, golden_light
from cultivation_life.system.doctrine.provider import conversion_state


def test_trace_probability_stream_is_persisted_and_only_positive_awards_roll():
    p = Player('测试', 'supreme_metal', immortal_trace_rng=1460)
    for amount in (0, -1, -100):
        assert not grant_trace_chance(p, amount)
    assert p.immortal_trace_rng == 1460
    for _ in range(10000):
        grant_trace_chance(p, 1)
    assert 650 <= p.immortal_traces <= 750
    q = Player.from_dict(p.to_dict())
    for _ in range(50):
        assert grant_trace_chance(p, 100) == grant_trace_chance(q, 100)
    assert p.to_dict() == q.to_dict()
    assert not p.inventory


def test_legacy_trace_inventory_migrates_exactly_once(prepared):
    _, game, _ = prepared
    data = game.to_dict()
    data['player']['inventory'].append(Item('immortal_trace', '仙痕', quantity=37).to_dict())
    count = game.player.immortal_traces + 37
    loaded = GameState.from_dict(data)
    assert loaded.player.immortal_traces == count
    assert not any(i.id == 'immortal_trace' for i in loaded.player.inventory)
    assert GameState.from_dict(loaded.to_dict()).player.immortal_traces == count


def test_common_opportunity_award_rolls_once_even_for_large_reward(prepared):
    engine, game, _ = prepared
    with patch('cultivation_life.system.immortal_cultivation.grant_trace_chance') as grant:
        engine._add_opportunity(game.player, 10**9)
        grant.assert_called_once_with(game.player, 10**9)
        engine._add_opportunity(game.player, -100)
        assert grant.call_count == 1


def test_vein_failure_spends_once_retains_layer_and_pity_survives_reload(prepared):
    engine, game, _ = prepared
    game.player.immortal_veins['9'] = 2
    engine.store.save(game)
    before = engine.get_game(game.id)['doctrines']['veins']
    rng = random.Random(2)  # First roll .956 > the first-stage .85.
    with patch('cultivation_life.system.immortal_system.decode_rng', return_value=rng):
        engine.immortal_action(game.id, 'open_vein')
    saved = engine.store.load(game.id)
    assert saved.player.layer == 1 and saved.player.immortal_veins['9'] == 2
    assert saved.player.immortal_traces == before['traces'] - before['next_cost']['traces']
    assert saved.player.opportunity == before['opportunity'] - before['next_cost']['opportunity']
    assert vein_probability(saved.player) == pytest.approx(.90)
    saved.player.immortal_vein_pity['9:3'] = 50
    engine.store.save(saved)
    shown = engine.immortal_action(game.id, 'open_vein')
    assert shown['player']['layer'] == 1 and shown['doctrines']['veins']['opened'] == 3
    assert '9:3' not in engine.store.load(game.id).player.immortal_vein_pity


def test_immortal_manual_break_failure_uses_common_chance_and_keeps_surplus(prepared):
    engine, game, _ = prepared
    game.player.immortal_veins['9'] = 3
    engine.store.save(game)
    before = game.player.opportunity
    with patch.object(engine, '_breakthrough_chance', return_value={'final': 0}):
        shown = engine.immortal_action(game.id, 'breakthrough')
    assert shown['player']['layer'] == 1
    assert before * .99 < shown['player']['opportunity'] < before
    assert shown['doctrines']['veins']['opened'] == 3


def test_body_visible_before_prerequisite_and_old_body_manual_is_insufficient(prepared):
    engine, game, _ = prepared
    game.player.immortal_body = {}
    game.player.body_training = 0
    engine.store.save(game)
    assert engine.present(game)['doctrines']['immortal_body']['level'] == 0
    with pytest.raises(ValueError, match='100'):
        engine.immortal_action(game.id, 'train_body')
    game.player.body_training = 100
    engine.store.save(game)
    with pytest.raises(ValueError, match='仙躯功法'):
        engine.immortal_action(game.id, 'train_body')


def test_body_purchase_recipe_failure_pity_switch_and_level20(prepared):
    engine, game, _ = prepared
    game.player.body_training = 100
    game.player.immortal_body = {'level': 19}
    engine.store.save(game)
    engine.immortal_action(game.id, 'buy_body_manual', supply_id='jade_marrows')
    with pytest.raises(ValueError, match='药'):
        engine.immortal_action(game.id, 'train_body')
    saved = engine.store.load(game.id)
    for key in ('immortal_jade_herb', 'nine_leaf_immortal_lingzhi', 'golden_lotus_elixir'):
        add_item(saved.player, key, 2000)
    engine.store.save(saved)
    with patch('cultivation_life.system.immortal_body_system.decode_rng', return_value=random.Random(2)):
        shown = engine.immortal_action(game.id, 'train_body')
    assert shown['doctrines']['immortal_body']['failures'] == 1
    assert shown['doctrines']['immortal_body']['level'] == 19
    p = engine.store.load(game.id).player
    assert next(i.quantity for i in p.inventory if i.id == 'immortal_jade_herb') == 1880
    engine.immortal_action(game.id, 'buy_body_manual', supply_id='golden_lotus')
    shown = engine.immortal_action(game.id, 'select_body_manual', supply_id='golden_lotus')
    assert shown['doctrines']['immortal_body']['failures'] == 1
    saved = engine.store.load(game.id)
    saved.player.immortal_body['failures'] = 100
    saved.player.hp = max_hp(saved.player) * .4
    saved.player.mp = max_mp(saved.player) * .3
    old_hp, old_mp = canonical_intrinsic_hp(saved.player), canonical_intrinsic_mp(saved.player)
    assert not golden_light(saved.player) and conversion_state(saved.player)['ward_tier'] == 1
    engine.store.save(saved)
    shown = engine.immortal_action(game.id, 'train_body')
    p = engine.store.load(game.id).player
    assert golden_light(p) and conversion_state(p)['ward_tier'] == 2
    assert shown['doctrines']['immortal_body']['failures'] == 0
    assert canonical_intrinsic_hp(p) > old_hp and canonical_intrinsic_mp(p) > old_mp
    assert p.hp / max_hp(p) == pytest.approx(.4)
    assert p.mp / max_mp(p) == pytest.approx(.3)


@pytest.mark.parametrize('path', ['dao', 'ghost'])
def test_body_increases_intrinsic_caps_and_proportional_damage_does_not_reduce_them(path):
    from cultivation_life.system.ghost_system import grant_intrinsic_progression_if_new_highwater
    p = Player('本源', 'supreme_metal', path=path)
    old_hp, old_mp = canonical_intrinsic_hp(p), canonical_intrinsic_mp(p)
    p.body_training += 10
    grant_intrinsic_progression_if_new_highwater(p)
    assert canonical_intrinsic_hp(p) == old_hp + 120
    assert canonical_intrinsic_mp(p) == old_mp + 100
    p.hp, p.mp = max_hp(p), max_mp(p)
    before = intrinsic_resource_breakdown(p)
    p.hp *= .4
    p.mp *= .6
    after = intrinsic_resource_breakdown(p)
    for key, ratio in [('hp', .4), ('mp', .6)]:
        assert after[key]['maximum'] == before[key]['maximum']
        assert after[key]['current'] == pytest.approx(before[key]['current'] * ratio)
