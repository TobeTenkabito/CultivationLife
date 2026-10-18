"""Boundary regressions for the repaired scopes and retained trade rules."""
import copy

from test_pending_audit_fixes import engine, new, local_game
from test_audit_round56_fixes import planted_field
from test_regional_rifts import node, enter
from test_caravan_economy import trade, dispatch, arrive, cash
from cultivation_life.system.economy import caravans
from cultivation_life.relationship_records import find_person
from cultivation_life.system.demonic.annual import _annual_demonic_update
from test_pending_audit_fixes import captive, convert
import random


def test_other_lost_instance_cannot_use_first_instances_field(engine):
    game = planted_field(engine, new(engine, lost=True))
    owner = copy.deepcopy(game.player.spirit_field['owner'])
    enter(engine, game.id, node(engine, game, 'spirit'))
    game = engine.store.load(game.id)
    enter(engine, game.id, node(engine, game, 'lost'))
    game = engine.store.load(game.id)
    assert game.player.world == owner['world'] == 'lost'
    assert game.spatial_state['current'] != owner['instance_id']
    assert not engine.get_game(game.id)['spirit_field']['local_available']
    engine.advance(game.id, 'rest', 1)
    assert engine.store.load(game.id).player.spirit_field['plots'][0]['growth_years'] == 0


def test_legacy_field_adopts_before_departure_and_portable_harvest_still_works(engine):
    game = planted_field(engine, local_game(engine))
    field = game.player.spirit_field
    field.pop('owner')
    field.pop('settled_year')
    item = engine._add_harvested_plant(game.player, 'mystic_heaven_vine', 10000)
    engine.store.save(game)
    enter(engine, game.id, node(engine, game, 'spirit'))
    game = engine.store.load(game.id)
    assert game.player.spirit_field['owner']['world'] == 'human'
    assert not engine.get_game(game.id)['spirit_field']['local_available']
    before = copy.deepcopy(game.player.spirit_field)
    engine.use_harvested_plant(game.id, item.id)
    game = engine.store.load(game.id)
    assert game.player.spirit_field == before
    assert not any(i.id == item.id for i in game.player.inventory)
    assert any(i.id == 'mystic_heaven_sword' for i in game.player.inventory)


def test_real_commercial_loss_still_counts_and_shrinks_fleet(trade, monkeypatch):
    engine, game, fleet, source, target, item = trade
    fleet['loss_streak'] = 1
    capacity = fleet['capacity']
    dispatch(trade)
    arrive(trade)
    monkeypatch.setattr(caravans, '_roll', lambda *args: .99)
    target['commodities'][item]['stock'] = target['commodities'][item]['target'] * 20
    money = cash(game)
    caravans.advance_caravans(game, engine.maps)
    assert fleet['cargo'] is None and fleet['profit'] < 0
    assert fleet['loss_streak'] == 2 and fleet['capacity'] == max(6, capacity // 2)
    assert fleet['dividends'] == 0 and cash(game) == money


def test_dead_original_living_source_does_not_pay_annual_opportunity(engine):
    game = new(engine)
    captive(game, 'dead-annual-source')
    game = convert(engine, game, 'dead-annual-source')
    source = find_person(game, 'dead-annual-source', include_inactive=True)
    source.alive = False
    source.death_reason = '测试陨落'
    before = game.player.opportunity
    _annual_demonic_update(engine._dependencies.demonic_flows.annual, game, random.Random(1))
    assert game.player.opportunity == before
    assert not source.alive and game.player.puppets[0]['alive']
    assert not engine._living_puppet_party_powers(game.player, game)
    assert not any(unit.id == game.player.puppets[0]['id'] for unit in engine._player_combat_units(game))
