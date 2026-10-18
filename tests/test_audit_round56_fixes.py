"""Seven confirmed audit classes: real commands and isolated disk saves."""
import copy
import random

import pytest

from cultivation_life.models import SectNpc, SectState
from cultivation_life.relationship_records import find_person
from cultivation_life.runtime import encode_rng
from cultivation_life.rules import add_item, max_hp, max_mp
from cultivation_life.engine.world import regions
from cultivation_life.system.economy import organizations, depot
from cultivation_life.system.economy.ledger import transfer_value, balance
from cultivation_life.system.economy.local_market import quote
from cultivation_life.system.economy.state import ensure_regional_market
from test_pending_audit_fixes import engine, local_game, new, captive, convert
from test_regional_rifts import node, enter
from test_economy_enterprises import buy, estate_act, own_fleet, fleet, order
from test_economy_network import act


def war_game(engine):
    game = local_game(engine)
    first = SectNpc('audit-loser-disciple', '林青', '弟子', 1, 1, 30, 200,
        world='human', faction_id='audit-loser-sect', spirit_root='supreme_wood',
        encountered_player=True, location_id='wudi_plain')
    second = SectNpc('audit-winner-lord', '陆玄', '宗主', 5, 9, 500, 10000,
        world='human', faction_id='audit-winner-sect', spirit_root='supreme_wood',
        encountered_player=True, location_id='wudi_plain')
    for identity, npc, owned in [('audit-loser-sect', first, True), ('audit-winner-sect', second, False)]:
        game.sects[identity] = SectState(identity, identity, 'human', [npc], kind='sect',
            location_id='wudi_plain', founded_by_player=owned,
            founder_player_id=game.id if owned else None, allegiance_race='human')
        organizations.register(game, 'sect', identity, 'human')
        transfer_value(game, 'background:human', depot.treasury(game, game.sects[identity]), 100000, '测试资本')
    game.player.faction_id = 'audit-loser-sect'
    engine.store.save(game)
    engine.propose_sect_diplomacy(game.id, 'audit-winner-sect', 'war')
    game = engine.store.load(game.id)
    return game, next(w for w in game.wars if w['attacker_id'] == 'audit-loser-sect')


def test_naturally_zero_control_living_puppet_can_be_reinforced(engine):
    game = new(engine)
    captive(game, 'living-low')
    game = convert(engine, game, 'living-low')
    puppet = game.player.puppets[0]
    identity = puppet['id']
    puppet['control'] = .1
    game.rng_state = encode_rng(random.Random(17))
    engine.store.save(game)
    engine.advance(game.id, 'rest', 1)
    game = engine.store.load(game.id)
    puppet = next(p for p in game.player.puppets if p['id'] == identity)
    assert puppet['control'] == 0 and puppet['alive']
    assert find_person(game, 'living-low', include_inactive=True).alive
    shown = engine.get_game(game.id)['demonic_system']['puppets'][0]
    assert shown['usable'] and shown['annual_opportunity'] > 0
    before = game.player.mp
    engine.puppet_action(game.id, identity, 'reinforce_control')
    game = engine.store.load(game.id)
    assert game.player.puppets[0]['control'] > 0 and game.player.mp < before


@pytest.mark.parametrize('dead_source', [False, True])
def test_destroyed_puppet_public_has_no_growth_or_contribution(engine, dead_source):
    game = new(engine)
    captive(game, 'display-source', realm=2)
    game = convert(engine, game, 'display-source')
    puppet = game.player.puppets[0]
    if dead_source:
        source = find_person(game, 'display-source', include_inactive=True)
        source.alive = False
        source.death_reason = '测试陨落'
    else:
        puppet['control'] = 10
        power = engine._player_battle_power(game) * 1.5
        engine._combat(game, dict(target_name='强敌', target_power=power,
            target_realm_index=4, target_layer=1, combat_type='cultivator',
            members=[dict(name='强敌', power=power, realm_index=4, layer=1, path='dao', race='human')]),
            False, random.Random(19))
        assert not puppet['alive']
    game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
    engine.store.save(game)
    public = engine.get_game(game.id)['demonic_system']['puppets'][0]
    assert not public['usable']
    assert public['battle_contribution'] == public['annual_opportunity'] == 0
    for rows in public['training'].values():
        assert all(not row['can_train'] and row['opportunity'] == row['mp'] == 0 for row in rows)


def controlled_ghost(engine):
    game = engine._load(engine.create_game('拘魂验证', 'mutated_yin', 'ghost', 20261018)['id'])
    game.settings.update(silent_events=True, guixu_event_popup=False)
    game.pending_event = None
    p = game.player
    p.realm_index, p.layer, p.lifespan = 1, 1, 100000
    p.hp, p.mp = max_hp(p), max_mp(p)
    npc = SectNpc('dying-controller', '年迈拘魂者', '散修', 3, 1, 999, 1000,
        world=p.world, spirit_root='none', encountered_player=True, location_id=p.location_id)
    game.notable_npcs[npc.id] = npc
    p.ghost_captor = dict(id=npc.id, npc_id=npc.id, name=npc.name, combat_power=10000,
        realm_index=3, layer=1, location_id=p.location_id, followed_years=0,
        controlled_form='拘魂', source='defeat_capture')
    return game, npc


def test_original_captor_dies_and_free_actions_resume(engine):
    game, npc = controlled_ghost(engine)
    location = game.player.location_id
    engine.store.save(game)
    engine.ghost_constraint_action(game.id, 'wait')
    game = engine.store.load(game.id)
    assert not find_person(game, npc.id, include_inactive=True).alive
    assert game.player.ghost_captor is None
    assert game.player.location_id == location
    assert sum(h.event_id == 'SYS_GHOST_CAPTOR_DIED' for h in game.history) == 1
    engine.advance(game.id, 'treasure', 1)
    assert engine.store.load(game.id).player.ghost_captor is None


@pytest.mark.parametrize('registered', [False, True])
def test_captor_load_reconciles_known_death_without_freeing_snapshot_only(engine, registered):
    game, npc = controlled_ghost(engine)
    if registered:
        npc.alive = False
        npc.death_reason = '已经陨落'
    else:
        del game.notable_npcs[npc.id]
    engine.store.save(game)
    loaded = engine._load(game.id)
    assert (loaded.player.ghost_captor is None) == registered
    if registered:
        engine.advance(game.id, 'rest', 1)
        assert engine.store.load(game.id).player.ghost_captor is None
    else:
        with pytest.raises(ValueError, match='拘魂|受制'):
            engine.advance(game.id, 'treasure', 1)


def planted_field(engine, game):
    add_item(game.player, 'spirit_stone', 100000)
    add_item(game.player, 'purple_cloud_ginseng_seed')
    engine.store.save(game)
    engine.reclaim_spirit_field(game.id)
    engine.plant_spirit_crop(game.id, 'purple_cloud_ginseng')
    return engine.store.load(game.id)


def test_field_freezes_in_foreign_world_rejects_remote_access_and_catches_up_once(engine):
    game = planted_field(engine, local_game(engine))
    crop = game.player.spirit_field['plots'][0]['id']
    original = copy.deepcopy(game.player.spirit_field)
    enter(engine, game.id, node(engine, game, 'spirit'))
    engine.advance(game.id, 'rest', 1)
    game = engine.store.load(game.id)
    assert game.player.spirit_field == original
    assert not engine.get_game(game.id)['spirit_field']['local_available']
    snapshot = engine.store._path(game.id).read_bytes()
    for fn, args in [(engine.reclaim_spirit_field, ()), (engine.plant_spirit_crop, ('purple_cloud_ginseng',)),
                     (engine.irrigate_spirit_crop, (crop,)), (engine.harvest_spirit_crop, (crop,))]:
        with pytest.raises(ValueError, match='原界面|空间实例'):
            fn(game.id, *args)
        assert engine.store._path(game.id).read_bytes() == snapshot
    enter(engine, game.id, node(engine, game, 'human'))
    game = engine.store.load(game.id)
    assert game.player.spirit_field['owner'] == original['owner']
    assert game.player.spirit_field['plots'][0]['growth_years'] == 5
    engine.get_game(game.id)
    assert engine.store.load(game.id).player.spirit_field['plots'][0]['growth_years'] == 5
    shown = engine.harvest_spirit_crop(game.id, crop)
    assert not shown['spirit_field']['plots']
    assert any(r.get('plant_id') == 'purple_cloud_ginseng' for r in shown['player']['inventory'])


def test_instance_field_stays_with_original_instance_and_does_not_grow_outside(engine):
    game = planted_field(engine, new(engine, lost=True))
    original = copy.deepcopy(game.player.spirit_field)
    assert original['owner']['instance_id'] == game.spatial_state['current']
    engine.advance(game.id, 'rest', 1)
    game = engine.store.load(game.id)
    assert game.player.spirit_field['plots'][0]['growth_years'] == 5
    enter(engine, game.id, node(engine, game, 'spirit'))
    engine.advance(game.id, 'rest', 1)
    game = engine.store.load(game.id)
    assert game.player.spirit_field['plots'][0]['growth_years'] == 5
    assert not engine.get_game(game.id)['spirit_field']['local_available']


@pytest.mark.parametrize('term', ['annex', 'dissolve'])
def test_dynamic_sect_peace_transfers_one_original_person_after_reload(engine, term):
    game, war = war_game(engine)
    engine.war_action(game.id, war['id'], 'retreat')
    engine.war_peace(game.id, war['id'], term, concede=True)
    game = engine.store.load(game.id)
    identity = 'audit-loser-disciple'
    assert game.sects['audit-loser-sect'].extinct
    assert not any(n.id == identity for n in game.sects['audit-loser-sect'].npcs)
    actual = find_person(game, identity, include_inactive=True)
    assert actual.faction_id == ('audit-winner-sect' if term == 'annex' else None)
    assert sum(n.id == identity for n in engine._all_world_npcs(game)) == 1
    age = actual.age
    engine.advance(game.id, 'rest', 1)
    game = engine.store.load(game.id)
    actual = find_person(game, identity, include_inactive=True)
    assert actual.age == age + 5 and actual.alive
    assert sum(n.id == identity for n in engine._all_world_npcs(game)) == 1


def test_retreat_rejects_stale_vanguard_atomically(engine):
    game, war = war_game(engine)
    engine.war_action(game.id, war['id'], 'retreat')
    snapshot = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError, match='胜负已定'):
        engine.war_action(game.id, war['id'], 'conquest')
    assert engine.store._path(game.id).read_bytes() == snapshot
    assert engine.store.load(game.id).pending_event is None


def test_four_internal_deliveries_keep_solvent_fleet_capacity_and_real_costs(engine):
    game = local_game(engine)
    transfer_value(game, 'background:human', 'player', 10**9, '测试资本')
    engine.store.save(game)
    game, source = buy(engine, game, 'shop')
    origin = game.player.location_id
    game = estate_act(engine, game, source, 'fund', amount=10000)
    market = game.economy_v2['markets'][f'human:{origin}']
    game = estate_act(engine, game, source, 'purchase', item='dew_grass_seed', quantity=1,
        market_revision=market['revision'], total=quote(market['commodities']['dew_grass_seed'], 'buy', 1)['total'])
    # Initial fixture warehouse only; every delivery and player trip is real.
    game.player.location_id = 'lanjiang_steppe'
    ensure_regional_market(game, engine.maps, 'human', game.player.location_id)
    game, target = buy(engine, game, 'shop')
    game.player.location_id = origin
    game, fid = own_fleet(engine, game)
    game = act(engine, game, 'fund', fleet_id=fid, amount=1000000)
    game = act(engine, game, 'guard', fleet_id=fid)
    before = copy.deepcopy(fleet(game, fid))
    initial_cash = balance(game, f'caravan:{fid}')
    for _ in range(4):
        game = order(engine, game, fid, kind='delivery', source_estate=source, target_estate=target, quantity=1)
        destination = game.economy_v2['estates'][target]['location']
        game = act(engine, game, 'order_dispatch', fleet_id=fid)
        engine.travel_map(game.id, destination)
        game = engine._load(game.id)
        for _wait in range(20):
            if not fleet(game, fid)['cargo']:
                break
            engine.advance(game.id, 'rest', 1)
            game = engine._load(game.id)
        assert not fleet(game, fid)['cargo']
        assert fleet(game, fid)['capacity'] == before['capacity']
        assert fleet(game, fid)['loss_streak'] == 0
        assert fleet(game, fid)['status'] != 'retired'
        source, target = target, source
    f = fleet(game, fid)
    assert f['lost'] == 0 and f['delivered'] == 4
    assert f['profit'] < before['profit'] and f['operating_costs'] > before['operating_costs']
    assert 20 < balance(game, f'caravan:{fid}') < initial_cash
    assert f.get('turnover', 0) == before.get('turnover', 0)
    assert f.get('sale_income', 0) == before.get('sale_income', 0)
