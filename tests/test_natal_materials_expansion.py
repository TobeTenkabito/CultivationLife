"""Eleven-world stage coverage, real acquisition, sockets and owned return paths."""
from pathlib import Path

import pytest

from cultivation_life.content_registry import ITEM_CATALOG, MARKET_GOODS, WORLD_SYSTEMS
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item
from test_other_systems_audit_fixes import api

ROOT = Path(__file__).resolve().parents[1]
NEW = [r for r in WORLD_SYSTEMS['natal_artifact']['materials'] if r['item_id'].startswith('natal_')]
STAGES = sorted({(r['world'], r['minimum_realm']) for r in NEW})


def test_all_native_stages_have_three_distinct_choices_and_real_sources():
    assert len(NEW) == 111 and len(STAGES) == 37
    assert len({r['world'] for r in NEW}) == 11
    assert len({r['name'] for r in NEW}) == 111
    for world, stage in STAGES:
        rows = [r for r in NEW if r['world'] == world and r['minimum_realm'] == stage]
        assert {r['specialization'] for r in rows} == {'攻伐', '护持', '养灵'}
        assert len(rows) == 3
        for row in rows:
            item = ITEM_CATALOG[row['item_id']]
            assert len(item.name) == 4 and item.name == row['name']
            assert item.combat_bonus == item.hp_bonus == item.mp_bonus == item.opportunity_bonus == 0
            goods = [g for g in MARKET_GOODS if g['content_id'] == item.id]
            assert len(goods) == 1
            assert (goods[0]['world'], goods[0]['tier']) == (world, stage)
            assert goods[0]['price'] > 0


@pytest.mark.parametrize('world,stage', STAGES)
def test_each_native_stage_can_socket_replace_and_return_without_duplication(tmp_path, world, stage):
    engine = GameEngine(ROOT, tmp_path / 'saves')
    made = engine.create_game('十一界镶材', 'supreme_metal', 'dao', 2142,
                              custom_start=dict(world=world, realm_index=stage, layer=1))
    game = engine._load(made['id'])
    game.pending_event = None
    add_item(game.player, 'starfall_blade')
    materials = [r for r in NEW if r['world'] == world and r['minimum_realm'] == stage]
    for row in materials:
        add_item(game.player, row['item_id'])
    engine.store.save(game)
    engine.natal_artifact_action(game.id, 'bind', 'starfall_blade')
    game = engine._load(game.id)
    game.natal_artifact.update(level=30, slots=[None] * 3)
    engine.store.save(game)
    before = engine.get_game(game.id)['natal_artifact']['bonuses']
    rng, age = game.rng_state, game.player.age
    for slot, row in enumerate(materials):
        shown = engine.natal_artifact_action(game.id, 'socket', row['item_id'], slot)
        assert shown['natal_artifact']['slots'][slot]['material_id'] == row['item_id']
    loaded = engine.store.load(game.id)
    for stat in ('combat_bonus', 'hp_bonus', 'mp_bonus', 'opportunity_bonus'):
        expected = before[stat] + sum(r.get('effect', {}).get(stat, 0) for r in materials)
        assert shown['natal_artifact']['bonuses'][stat] == pytest.approx(expected)
    effects = engine._natal_artifact_combat_effects(loaded)
    assert len([r for r in effects if r['item_id'] in {m['item_id'] for m in materials}]) == 3
    for slot in range(3):
        engine.natal_artifact_action(game.id, 'unsocket', slot_index=slot)
    returned = engine.store.load(game.id)
    assert (returned.player.age, returned.rng_state) == (age, rng)
    assert all(next(i.quantity for i in returned.player.inventory if i.id == r['item_id']) == 1 for r in materials)
    # Replacement transfers the old material back, with no duplicate socket ownership.
    engine.natal_artifact_action(game.id, 'socket', materials[0]['item_id'], 0)
    engine.natal_artifact_action(game.id, 'socket', materials[1]['item_id'], 0)
    replaced = engine.store.load(game.id)
    assert next(i.quantity for i in replaced.player.inventory if i.id == materials[0]['item_id']) == 1
    assert not any(i.id == materials[1]['item_id'] for i in replaced.player.inventory)


def test_remote_carried_material_keeps_qualification_and_rejects_stale_state(api):
    engine, act = api
    made = engine.create_game('镶材资格', 'supreme_metal', 'dao', 2142, preset_id='core')
    game = engine._load(made['id'])
    game.pending_event = None
    add_item(game.player, 'starfall_blade')
    high = next(r for r in NEW if r['world'] == 'celestial' and r['minimum_realm'] == 12)
    low = next(r for r in NEW if r['world'] == 'demon' and r['minimum_realm'] == 3)
    add_item(game.player, high['item_id'])
    add_item(game.player, low['item_id'])
    engine.store.save(game)
    act(game.id, 'natal-artifact', action='bind', item_id='starfall_blade')
    game = engine._load(game.id)
    game.natal_artifact.update(level=20, slots=[None, None])
    engine.store.save(game)
    snapshot = engine.store._path(game.id).read_bytes()
    act(game.id, 'natal-artifact', action='socket', item_id=high['item_id'], slot_index=0, status=400)
    assert engine.store._path(game.id).read_bytes() == snapshot
    act(game.id, 'natal-artifact', action='socket', item_id=low['item_id'], slot_index=0)
    snapshot = engine.store._path(game.id).read_bytes()
    act(game.id, 'natal-artifact', action='socket', item_id=low['item_id'], slot_index=1, status=400)
    assert engine.store._path(game.id).read_bytes() == snapshot
    game = engine._load(game.id)
    game.player.imprisonment = dict(years_remaining=1)
    engine.store.save(game)
    snapshot = engine.store._path(game.id).read_bytes()
    act(game.id, 'natal-artifact', action='unsocket', slot_index=0, status=400)
    assert engine.store._path(game.id).read_bytes() == snapshot


@pytest.mark.parametrize('world', sorted({r['world'] for r in NEW}))
def test_native_material_is_really_purchasable_in_its_world(tmp_path, world):
    engine = GameEngine(ROOT, tmp_path / 'saves')
    row = next(r for r in NEW if r['world'] == world)
    made = engine.create_game('产地购材', 'supreme_metal', 'dao', 21420,
                             custom_start=dict(world=world, realm_index=row['minimum_realm'], layer=1))
    game = engine._load(made['id'])
    game.pending_event = None
    game.auction_state = dict(id='material-source', status='black_market',
        world=world, location_id=game.player.location_id,
        location_name=engine.maps.location(world, game.player.location_id)['name'],
        lots=[], consignments=[], attendees=[], black_market_results=[])
    add_item(game.player, 'spirit_stone', 10**15)
    engine.store.save(game)
    shown = engine.search_black_market(game.id, row['name'])
    offer = next(r for r in shown['auction_system']['black_market_results'] if r['content_id'] == row['item_id'])
    before = engine._spirit_stones(engine._load(game.id).player)
    engine.buy_black_market_item(game.id, offer['id'])
    purchased = engine.store.load(game.id)
    assert next(i.quantity for i in purchased.player.inventory if i.id == row['item_id']) == 1
    assert engine._spirit_stones(purchased.player) < before
    assert row['item_id'] in {r['id'] for r in engine._merchant_items(world)}
