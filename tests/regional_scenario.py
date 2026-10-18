"""Disposable integrated fixture shared by acceptance and timing, never imported by the game."""
import copy
import random
from unittest.mock import patch
from dataclasses import replace
from cultivation_life.engine.world import regions
from cultivation_life.system.economy import fleet_network, cross_freight
from cultivation_life.system.economy.ledger import transfer_value
from cultivation_life.system.heavens.state import initialize
from cultivation_life.system.heavens.definitions import HeavensDefinitions
from cultivation_life.system.heavens import campaign
from cultivation_life.system.heavens.campaign_definitions import INITIAL_SUPPLY
from cultivation_life.rules import max_hp, max_mp


def prepare(engine):
    from test_heavens_frontier import ready
    from test_heavens_campaign import military, construction
    game = engine.store.load(engine.create_game('并行事务验收', 'none', 'dao', 20261018)['id'])
    game.player.realm_index, game.player.layer = 4, 1
    game.player.lifespan = 10000
    game.player.next_tribulation_age = None
    game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
    game.settings.update(silent_events=True, guixu_event_popup=False)
    initialize(game)
    engine.store.save(game)
    deps = replace(engine._dependencies.heavens, load_game=engine.store.load,
                   get_definitions=lambda: HeavensDefinitions(generation_available=True))
    with patch.object(regions, 'synchronize'):
        fixture = military.__wrapped__(ready.__wrapped__((engine, game, deps)))
        game = construction(fixture)
    # The established campaign fixture authors its starting date with a focused
    # calendar. This is the initial observation, not replay of a user history.
    regions.ensure(engine, game)
    regions.synchronize(engine, game, regions.worlds())
    for row in game.economy_v2['organizations'].values():
        row['last_year'] = game.player.age
    for row in game.economy_v2['transport']['worlds'].values():
        row['last_year'] = game.player.age
    for route in game.economy_v2['network']['routes'].values():
        route['last_year'] = game.player.age
    alliance = fleet_network.alliance_at(game, 'spirit', 'xuanji')
    transfer_value(game, 'background:spirit', 'alliance:spirit:xuanji', 30_000_000, '验收原池提供百年维护资金')
    fleet = next(f for f in game.economy_v2['transport']['worlds']['spirit']['fleets'].values()
                 if f['alliance_id'] == 'xuanji')
    transfer_value(game, 'background:spirit', 'caravan:'+fleet['id'], 10_000_000, '验收原池商队周转金')
    fleet.update(investment=10_000_000, guard_power=fleet_network.guard_required('spirit')*100)
    from cultivation_life.system.economy.state import ensure_regional_market
    ensure_regional_market(game, engine.maps, 'spirit', alliance['hq'])
    market = game.economy_v2['markets']['spirit:'+alliance['hq']]
    item = next(k for k,r in market['commodities'].items() if r['stock'] >= 10)
    cross_freight.dispatch(game, engine.maps, fleet, 'true_demon', order=dict(
        item=item, quantity=4, buy_limit=10**10, sell_limit=0, return_item=None))
    local = game.merchant_state['worlds']['human'][0]
    transfer_value(game, 'background:human', 'player', 10**8, '验收原池委托本金')
    engine._merchant_post(game, local, dict(kind='intel', stars=1))
    order = game.merchant_state['posted'][-1]
    engine._merchant_start_order(game, order, random.Random(4))
    for identity in ('tianjian','wanmo'):
        transfer_value(game, 'background:human', 'organization:sect:'+identity, 2_000_000, '验收原池战争预算')
    engine._start_war(game, 'sect', 'tianjian', 'wanmo')
    return game


def check(game):
    from test_economy_network import cash
    row = campaign.get(game)
    supply = dict(row['supply'], inflight=row['shipment']['quantity'] if row['shipment'] else 0)
    assert sum(supply.values()) == INITIAL_SUPPLY, supply
    seen = {}
    for npc in [*(n for s in game.sects.values() for n in s.npcs), *game.world_npcs.values(), *game.notable_npcs.values()]:
        if npc.id in seen: assert seen[npc.id] is npc, npc.id
        seen[npc.id] = npc
    return dict(supply=supply, campaign=row['status'], deliveries=row['deliveries'],
        orders=[dict(id=o['id'], status=o['status']) for o in game.merchant_state['posted']],
        people=len(seen), alive=sum(n.alive for n in seen.values()),
        cash=cash(game), issued=game.economy_v2.get('issued', 0),
        spirit_sects={s.id:dict(extinct=s.extinct, alive=sum(n.alive for n in s.npcs),
                               recruits=sum('_recruit_' in n.id for n in s.npcs))
                      for s in game.sects.values() if s.world == 'spirit'})


def canonical(game):
    value = copy.deepcopy(game.to_dict())
    for key in ('created_at', 'updated_at', 'id'): value.pop(key, None)
    value['history'].sort(key=lambda r:(r['age'], str(r)))
    sim = value['world_simulation']
    sim.pop('revision', None); sim.pop('recent', None)
    # Ledger/history buffers order depends on when an unrelated world is read;
    # actual balances, goods, lives, annual RNG and local histories must match.
    value['economy_v2'].pop('ledger', None)
    value['guixu_state']['external_treasures'].sort(key=lambda r: (r['dungeon_id'], r['pool_entry_id'], str(r)))
    return value
