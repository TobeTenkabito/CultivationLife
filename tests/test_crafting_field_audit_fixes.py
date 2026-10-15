"""Real HTTP boundaries for helper custody, field work and finite plant stacks."""
import copy
import random

import pytest

from test_other_systems_audit_fixes import api, new_game, snapshot
from cultivation_life.rules import add_item
from cultivation_life.runtime import encode_rng
from cultivation_life.system.crafting_system import make_crafting_material_instance
from cultivation_life.system.economy.ledger import balance
from cultivation_life.system import talismans


def basic_recipe(engine, game):
    rng = random.Random(17)
    definitions = engine._crafting_material_defs()
    rows = [make_crafting_material_instance(definitions[key], rng, source='隔离验收', origin_world='human')
            for key in ('human_cold_iron', 'human_cloud_silk', 'human_cloud_silk', 'human_sun_fire')]
    game.player.crafting_materials.extend(rows)
    return dict(mold_id='umbrella', primary_id=rows[0]['id'], secondary_a_id=rows[1]['id'],
                secondary_b_id=rows[2]['id'], quench_id=rows[3]['id'], allocations=dict(combat_power=10))


def blocking_state(engine, game, mode='event', *, followup=False):
    if mode == 'event':
        game.pending_event = engine._instantiate_event(engine.events_by_id['EVT_SECT_FIRST_WARNING_001'], game, random.Random(1))
        if followup:
            game.pending_event['_followup_event'] = engine._prepare_treasure_reward_event(game, random.Random(11))
    else:
        jailer = next(s for s in game.sects.values() if s.world == game.player.world and not s.extinct)
        engine._imprison_or_execute(game, 'sect:' + jailer.id, random.Random(1), surrendered=True)
        assert game.player.imprisonment['remaining_years'] > 0
    engine.store.save(game)
    snapshot(engine, game.id)
    return engine._load(game.id)


def field_game(engine, act):
    game = new_game(engine, realm=4)
    game.player.spirit_field['reclaimed_qing'] = 2
    add_item(game.player, 'spirit_stone', 10**7)
    add_item(game.player, 'mystic_heaven_vine_seed', 2)
    engine._add_harvested_plant(game.player, 'mystic_heaven_vine', 10000)
    engine.store.save(game)
    act(game.id, 'spirit-field-plant', plant_id='mystic_heaven_vine', slot=0)
    game = engine._load(game.id)
    game.player.spirit_field['plots'][0].update(growth_years=10000, booster_unlocked=True)
    engine.store.save(game)
    return game


def helper_game(engine, act):
    game = new_game(engine, realm=4)
    add_item(game.player, 'spirit_stone', 10**7)
    engine.store.save(game)
    act(game.id, 'create-faction', name='注灵资格验收宗')
    game = engine._load(game.id)
    helper = game.sects[game.player.faction_id].npcs[0]
    helper.spirit_root, helper.affinity = 'supreme_water', 100
    add_item(game.player, 'talisman_human_1_paper', 2)
    game.rng_state = encode_rng(random.Random(1))
    engine.store.save(game)
    act(game.id, 'talisman-action', action='learn', method_id='talisman_human_1_protection')
    payload = dict(action='craft', method_id='talisman_human_1_protection',
                   material1='talisman_human_1_paper', material2='talisman_human_1_paper', element='water', npc_id=helper.id)
    return engine._load(game.id), helper.id, payload


def test_jailed_helper_is_hidden_and_refused_atomically_then_released_helper_works(api):
    engine, act = api
    game, identity, payload = helper_game(engine, act)
    assert identity in {r['id'] for r in engine.get_game(game.id)['talismans']['helpers']}
    act(game.id, 'intrigue-personnel', kind='sect', action='imprison', npc_id=identity, years=100)
    saved = engine._load(game.id)
    assert engine._intrigue_is_imprisoned(saved, identity)
    before = copy.deepcopy(saved.to_dict())
    for _ in range(2):
        assert identity not in {r['id'] for r in talismans.public(saved)['helpers']}
    assert saved.to_dict() == before
    frozen = snapshot(engine, game.id)
    act(game.id, 'talisman-action', status=400, **payload)
    assert engine.store._path(game.id).read_bytes() == frozen
    act(game.id, 'intrigue-personnel', kind='sect', action='release', npc_id=identity)
    saved = engine._load(game.id)
    before_cash, before_mp = balance(saved, 'player'), saved.player.mp
    assert identity in {r['id'] for r in engine.get_game(game.id)['talismans']['helpers']}
    act(game.id, 'talisman-action', **payload)
    saved = engine._load(game.id)
    assert len(saved.player.talismans) == 1 and saved.player.talismans[0]['element'] == 'water'
    assert balance(saved, 'player') == before_cash - 400 and saved.player.mp == before_mp


@pytest.mark.parametrize('mode', ['event', 'imprisonment'])
def test_all_field_writes_refuse_busy_state_without_changing_resources_or_followup(api, mode):
    engine, act = api
    game = field_game(engine, act)
    game = blocking_state(engine, game, mode, followup=True)
    assert not engine.get_game(game.id)['spirit_field']['operation_available']
    plot = game.player.spirit_field['plots'][0]
    vine = next(i for i in game.player.inventory if i.plant_id == 'mystic_heaven_vine')
    frozen = snapshot(engine, game.id)
    for operation, payload in [
        ('spirit-field-reclaim', {}),
        ('spirit-field-plant', dict(plant_id='mystic_heaven_vine', slot=1)),
        ('spirit-field-irrigate', dict(plot_id=plot['id'])),
        ('spirit-field-harvest', dict(plot_id=plot['id'])),
        ('spirit-plant-use', dict(item_id=vine.id)),
        ('market-sell-plant', dict(item_id=vine.id)),
    ]:
        act(game.id, operation, status=400, **payload)
        assert engine.store._path(game.id).read_bytes() == frozen, operation


def test_field_operations_restore_after_real_event_followup_reward(api):
    engine, act = api
    game = blocking_state(engine, field_game(engine, act), followup=True)
    followup = copy.deepcopy(game.pending_event['_followup_event'])
    shown = act(game.id, 'choice', event_id=game.pending_event['id'], choice_id='acknowledge')
    assert shown['pending_event']['runtime'] == followup['runtime']
    act(game.id, 'choice', event_id=followup['id'], choice_id='pill')
    saved = engine._load(game.id)
    assert saved.pending_event is None and engine.get_game(game.id)['spirit_field']['operation_available']
    plot_id = saved.player.spirit_field['plots'][0]['id']
    act(game.id, 'spirit-field-harvest', plot_id=plot_id)
    vine = next(i for i in engine._load(game.id).player.inventory if i.plant_id == 'mystic_heaven_vine')
    assert vine.quantity == 2
    act(game.id, 'spirit-plant-use', item_id=vine.id)
    saved = engine._load(game.id)
    assert next(i.quantity for i in saved.player.inventory if i.id == vine.id) == 1
    assert next(i.quantity for i in saved.player.inventory if i.id == 'mystic_heaven_sword') == 1


@pytest.mark.parametrize('mode', ['event', 'imprisonment'])
def test_unique_artifact_sale_refuses_busy_state_without_removing_item_or_moving_cash(api, mode):
    engine, act = api
    game = new_game(engine, realm=4)
    payload = basic_recipe(engine, game)
    engine.store.save(game)
    act(game.id, 'crafting-forge', **payload)
    saved = blocking_state(engine, engine._load(game.id), mode)
    artifact = saved.player.crafted_artifacts[-1]
    assert not engine.get_game(game.id)['crafting_system']['market_available']
    frozen = snapshot(engine, game.id)
    act(game.id, 'crafted-artifact', action='sell', artifact_id=artifact['id'], status=400)
    assert engine.store._path(game.id).read_bytes() == frozen


def stacked_recipe(engine, act, count=2, plant='golden_thunder_bamboo'):
    game = new_game(engine, realm=4)
    game.player.spirit_field['reclaimed_qing'] = 2
    add_item(game.player, plant + '_seed', 2)
    payload = basic_recipe(engine, game)
    engine.store.save(game)
    for slot in range(2):
        act(game.id, 'spirit-field-plant', plant_id=plant, slot=slot)
    game = engine._load(game.id)
    identities = [r['id'] for r in game.player.spirit_field['plots']]
    for plot in game.player.spirit_field['plots']:
        plot['growth_years'] = 10000
    engine.store.save(game)
    for identity in identities:
        act(game.id, 'spirit-field-harvest', plot_id=identity)
    game = engine._load(game.id)
    stack = next(i for i in game.player.inventory if i.plant_id == plant)
    assert stack.quantity == 2
    stack.quantity = count
    engine.store.save(game)
    return game, stack.id, payload


@pytest.mark.parametrize('count', [2, 4, 1000000])
def test_stacked_plants_offer_bounded_slots_and_forge_consumes_exact_quantity(api, count):
    engine, act = api
    game, identity, payload = stacked_recipe(engine, act, count)
    before = copy.deepcopy(next(i.to_dict() for i in game.player.inventory if i.id == identity))
    rows = [r for r in engine.get_game(game.id)['crafting_system']['materials'] if r.get('inventory_item_id') == identity]
    assert len(rows) == min(4, count) and len({r['id'] for r in rows}) == len(rows)
    assert rows[0]['id'] == 'plant:' + identity
    assert len(engine._exchange_materials(game)) == len({r['id'] for r in engine._exchange_materials(game)})
    exchange = next(r for r in engine._exchange_materials(game) if r.get('inventory_item_id') == identity)
    assert exchange['quantity'] == count
    slots = ('primary_id', 'secondary_a_id', 'secondary_b_id', 'quench_id') if count >= 4 else ('secondary_a_id', 'secondary_b_id')
    payload.update({key: row['id'] for key, row in zip(slots, rows)})
    frozen = snapshot(engine, game.id)
    act(game.id, 'crafting-preview', **payload)
    assert engine.store._path(game.id).read_bytes() == frozen
    act(game.id, 'crafting-forge', **payload)
    saved = engine._load(game.id)
    remaining = next((i for i in saved.player.inventory if i.id == identity), None)
    assert (remaining.quantity if remaining else 0) == count - len(slots)
    if remaining:
        assert remaining.to_dict() | {'quantity': count} == before
    artifact_count = len(saved.player.crafted_artifacts)
    # Once the chosen stack units no longer exist, a repeated submit is atomic.
    if count <= 4:
        frozen = snapshot(engine, game.id)
        act(game.id, 'crafting-forge', status=400, **payload)
        assert engine.store._path(game.id).read_bytes() == frozen
        assert len(engine._load(game.id).player.crafted_artifacts) == artifact_count


def test_stale_stack_and_forbidden_duplicate_type_are_still_rejected(api):
    engine, act = api
    game, identity, payload = stacked_recipe(engine, act)
    rows = [r for r in engine.get_game(game.id)['crafting_system']['materials'] if r.get('inventory_item_id') == identity]
    payload.update(secondary_a_id=rows[0]['id'], secondary_b_id=rows[1]['id'])
    # A real sale from the other page invalidates the second selected unit.
    act(game.id, 'market-sell-plant', item_id=identity)
    frozen = snapshot(engine, game.id)
    act(game.id, 'crafting-forge', status=400, **payload)
    assert engine.store._path(game.id).read_bytes() == frozen
    game, identity, payload = stacked_recipe(engine, act, plant='mystic_heaven_vine')
    rows = [r for r in engine.get_game(game.id)['crafting_system']['materials'] if r.get('inventory_item_id') == identity]
    payload.update(secondary_a_id=rows[0]['id'], secondary_b_id=rows[1]['id'])
    frozen = snapshot(engine, game.id)
    act(game.id, 'crafting-preview', status=400, **payload)
    assert engine.store._path(game.id).read_bytes() == frozen
