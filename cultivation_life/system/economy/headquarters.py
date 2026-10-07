"""Administrative HQ promotion; regional people, goods and treasuries stay put."""
from ...content_registry import WORLD_SYSTEMS
from ...rules import combat_power
from .ledger import transfer_value
from .fleet_network import alliance_at, leader_record, routes, route_key


def relocate(game, home, local, create):
    p = game.player
    if not home or game.merchant_state.get('active'):
        raise ValueError('需拥有自建商盟，并先完成当前商盟委托')
    identity = home.get('network_id', home['id'])
    regions = game.economy_v2['transport']['worlds']
    for world, region in regions.items():
        owner = alliance_at(game, world, identity)
        if owner and any(f.get('cross_trip') for f in region['fleets'].values() if f['alliance_id'] == owner['id']):
            raise ValueError('请先让本盟跨界商队完成或撤回本趟运输，再迁移总部')
    tier = WORLD_SYSTEMS['world_profiles'][p.world]['tier']
    if p.world == home['world']:
        if p.location_id == home['hq']:
            raise ValueError('这里已经是总部')
        transfer_value(game, 'player', f'background:{p.world}', 20000 * tier, '本界总部迁址')
        office = next((o for o in home['offices'] if o['location_id'] == p.location_id), None)
        if office:
            home['offices'].remove(office)
            chief = office['leader']
        else:
            chief = leader_record(game, f'merchant-{p.world}-{identity}-{p.location_id}', '总部主事', home['leader']['realm_index'])
        home['offices'].append(dict(location_id=home['hq'], leader=home['leader']))
        home.update(hq=p.location_id, leader=chief)
    else:
        realm = (p.sealed_cultivation or {}).get('realm_index', p.realm_index)
        if tier < 2 or realm < 8:
            raise ValueError('跨界迁总部需要大乘道果，并亲赴二级以上界面')
        if local and p.location_id != local['hq']:
            raise ValueError('请前往本界自建分总部，将其升为主总部')
        if not local:
            candidates = [f for f in regions[p.world]['fleets'].values() if f['owner_kind'] == 'independent'
                          and f['status'] == 'waiting' and not f['cargo'] and not f.get('cross_trip')
                          and (f['pledged'] or f['player_controlled'])]
            if len(candidates) < 3:
                raise ValueError('新总部需要三支本界已招揽或本人领办的无势力商队')
        transfer_value(game, 'player', f'background:{p.world}', 1000000 * tier, '跨界总部营建、交接及原界坐镇聘任')
        if not local:
            local = create(candidates[:3], home)
        worlds = sorted({*home['linked_worlds'], p.world})
        # Original local officers remain local; an inadequate former HQ officer
        # retires into the local historical roster, replaced by a paid local hire.
        cap = int(WORLD_SYSTEMS['world_profiles'][home['world']]['npc_realm_cap'])
        if home['leader']['realm_index'] < cap - 1 or not home['leader'].get('alive', True):
            home.setdefault('retired_leaders', []).append(home['leader'])
            del home['retired_leaders'][:-4]
            home['leader'] = leader_record(game, f'merchant-{home["world"]}-{identity}-handover-{p.age}',
                                          '分总部坐镇主事', cap - 1, world=home['world'])
        for world in worlds:
            row = alliance_at(game, world, identity)
            row.update(network_id=identity, home_world=p.world, linked_worlds=worlds, cross_world=True,
                       chief_realm=realm, chief_name=p.name, chief_power=combat_power(p))
        # Existing physical passages are retained. A genuinely new edge is unbuilt.
        routes(game).setdefault(route_key(identity, home['world'], p.world), dict(alliance_id=identity,
            home=home['world'], branch=p.world, open=False, built=False, maintenance=0, paid=0, shortfall=0, last_year=p.age))
        for row in routes(game).values():
            if row['alliance_id'] == identity:
                row['last_year'] = p.age
        game.merchant_state['membership'] = dict(world=p.world, alliance_id=local['id'], site='hq', rank=2)


def passage_command(game, maps, home, local, payload):
    from .fleet_network import maintenance_cost, qualified_site
    p = game.player
    if not local or not home or p.location_id != local['hq']:
        raise ValueError('请前往自建商盟的总部或分总部办理通道')
    identity = home.get('network_id', home['id'])
    candidates = [r for r in routes(game).values() if r['alliance_id'] == identity and p.world in {r['home'], r['branch']}]
    key = payload.get('route_id')
    if key:
        candidates = [r for r in candidates if route_key(identity, r['home'], r['branch']) == key]
    else:
        candidates = [r for r in candidates if not r['open']]
    if len(candidates) != 1 or candidates[0]['open']:
        raise ValueError('请选择一条本地关闭或待建的通道')
    route = candidates[0]
    if not qualified_site(game, home) or any(not qualified_site(game, alliance_at(game, w, identity)) for w in (route['home'], route['branch'])):
        raise ValueError('总部或通道端点坐镇资格不足')
    annual = maintenance_cost(game, maps, home['world'], home['hq'])
    cost = annual if route.get('built') or route['paid'] else 10000000 * max(WORLD_SYSTEMS['world_profiles'][w]['tier'] for w in (route['home'], route['branch']))
    transfer_value(game, 'player', f'background:{p.world}', cost, '建设或修复逆灵通道')
    route.update(open=True, built=True, last_year=p.age, shortfall=0, maintenance=annual)
