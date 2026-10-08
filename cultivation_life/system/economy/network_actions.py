"""Atomic player fleet, branch and passage construction commands."""
import copy
from ...content_registry import WORLD_SYSTEMS
from ...rules import combat_power
from ...runtime import now_iso
from .ledger import balance, transfer_value
from .local_market import require_access
from .dependencies import MarketDependencies
from .fleet_network import (alliance_at, active_fleets, fleet_limit, new_fleet, guard_required,
    owner_key, leader_record, route_key, routes, maintenance_quote, member_of)


def controlled_alliance(game):
    return next((a for a in game.merchant_state.get('worlds', {}).get(game.player.world, []) if a.get('player_owned')), None)


def home_alliance(game):
    return next((a for rows in game.merchant_state.get('worlds', {}).values() for a in rows
                 if a.get('player_owned') and a['home_world'] == a['world']), None)


def _create_alliance(game, region, fleets, home=None):
    p = game.player
    identity = home.get('network_id', home['id']) if home else f'player-{game.id}'
    name = home['name'] if home else f'{p.name}商盟'
    cap = int(WORLD_SYSTEMS['world_profiles'][p.world]['npc_realm_cap'])
    realm = max(1, cap - 1) if home else min(cap, p.realm_index)
    leader = leader_record(game, f'merchant-{p.world}-{identity}-leader', f'{name}驻地主事', realm)
    alliance = dict(id=identity, name=name, world=p.world, hq=p.location_id,
        home_world=home['world'] if home else p.world, linked_worlds=[p.world], cross_world=bool(home),
        leader=leader, offices=[], chief_name=p.name, chief_realm=(home or {}).get('chief_realm', p.realm_index),
        chief_power=combat_power(p), reserves=0, policy='economy', next_policy_age=p.age + 12,
        relation='自主经营', board_epoch=0, player_owned=True)
    game.merchant_state['worlds'][p.world].append(alliance)
    for fleet in fleets:
        fleet.update(owner_kind='alliance', owner_id=identity, alliance_id=identity, pledged=False, player_controlled=True)
    if not home:
        game.merchant_state['membership'] = dict(world=p.world, alliance_id=identity, site='hq', rank=2)
    return alliance


def command(deps: MarketDependencies, game_id, payload, *, committed=None):
    game = copy.deepcopy(deps._load(game_id))
    require_access(game)
    from .caravans import ensure_caravans
    ensure_caravans(game, deps.maps)
    p = game.player
    region = game.economy_v2['transport']['worlds'][p.world]
    action = payload.get('action')
    tier = WORLD_SYSTEMS['world_profiles'][p.world]['tier']
    capital = 5000 * tier
    fleet = region['fleets'].get(payload.get('fleet_id'))
    alliance = controlled_alliance(game)
    home = home_alliance(game)
    identity = home.get('network_id', home['id']) if home else None
    if isinstance(action, str) and action.startswith('depot_'):
        from .depot import command as depot_command
        depot_command(game, deps.maps, payload)
    elif action in {'market_policy', 'market_relief'}:
        from .market_governance import command as governance_command
        governance_command(game, deps.maps, payload)
    elif isinstance(action, str) and action.startswith('estate_'):
        from .enterprise_actions import command as estate_command
        estate_command(game, deps.maps, payload)
    elif action in {'order_configure', 'order_dispatch', 'order_limits'}:
        from .trade_orders import authorized, configure, update_limits
        authorized(game, fleet)
        if action == 'order_configure':
            configure(game, deps.maps, fleet, payload)
        elif action == 'order_limits':
            update_limits(game, fleet, payload)
        else:
            if fleet['cargo'] or fleet.get('cross_trip') or fleet['status'] != 'waiting':
                raise ValueError('商队已有在途货物')
            order = fleet.get('trade_order', {})
            if order.get('mode') not in {'once', 'repeat'}:
                raise ValueError('请先保存单次或长期订单')
            if order['kind'] == 'cross':
                from .cross_freight import dispatch
                dispatch(game, deps.maps, fleet, order['destination'], remittance_percent=0, order=order)
            else:
                from .caravans import _dispatch
                from .fleet_network import owner_sites
                _dispatch(game, deps.maps, owner_sites(game, deps.maps, fleet), fleet, region)
    elif action == 'industry':
        from .industry_actions import invest
        invest(game, deps.maps, payload.get('owner_kind'))
    elif action == 'relocate':
        from .headquarters import relocate
        relocate(game, home, alliance, lambda fleets, old: _create_alliance(game, region, fleets, old))
    elif action == 'create':
        kind = payload.get('owner_kind', 'independent')
        identity, payer, name, location = 'player', 'player', f'{p.name}商队', p.location_id
        owner = None
        if kind == 'alliance':
            member = game.merchant_state.get('membership') or {}
            owner = next((a for a in game.merchant_state['worlds'].get(p.world, []) if member_of(game, a)), None)
            if not owner or p.location_id not in {owner['hq'], *(o['location_id'] for o in owner['offices'])}:
                raise ValueError('请先加入商盟，并前往本界总部或分部申请')
            identity, payer, name = owner['id'], f'alliance:{p.world}:{owner["id"]}', f'{p.name}领办商队'
        elif kind in {'sect', 'family'}:
            entity = game.family if kind == 'family' else game.sects.get(p.faction_id)
            from ..faction_geography import faction_site
            if not entity or entity.extinct or entity.world != p.world or entity.kind == 'institution':
                raise ValueError('当前没有可申请商队的本界宗门或家族')
            if p.location_id != faction_site(entity)['id']:
                raise ValueError('请前往组织驻地申请')
            from .organizations import register
            register(game, kind, entity.id, p.world)
            identity, payer, name = entity.id, f'organization:{kind}:{entity.id}', f'{entity.name}领办商队'
        elif kind != 'independent':
            raise ValueError('机构不经营商队')
        if len(active_fleets(game, p.world, kind, identity)) >= fleet_limit(kind, owner):
            raise ValueError('所属方的商队容量已满')
        guard_fee = max(100, round(guard_required(p.world) ** .5) * 5) if kind == 'alliance' else 0
        if balance(game, payer) < capital + guard_fee:
            raise ValueError('出资方不足以支付商队本金及初始护卫费用')
        fleet = new_fleet(game, region, p.world, identity, kind, location, name, player=True)
        transfer_value(game, payer, f'caravan:{fleet["id"]}', capital, '出资组建商队')
        transfer_value(game, payer, f'background:{p.world}', guard_fee, '商盟派遣初始护卫')
        fleet['investment'] = capital
    elif action in {'guard', 'fund', 'pledge'}:
        if not fleet or fleet['status'] == 'retired' or fleet['cargo'] or fleet.get('cross_trip'):
            raise ValueError('商队已解散或正在运输')
        if fleet['location'] != p.location_id:
            raise ValueError('请前往商队驻地办理')
        if action == 'pledge':
            if fleet['owner_kind'] != 'independent' or fleet['player_controlled'] or fleet['pledged']:
                raise ValueError('只能招揽尚未归附的无势力商队')
            transfer_value(game, 'player', f'caravan:{fleet["id"]}', 1000 * tier, '招揽无势力商队的合作出资')
            fleet['pledged'] = True
            fleet['investment'] += 1000 * tier
        else:
            if not fleet.get('player_controlled'):
                raise ValueError('只能管理本人领办的商队')
            if action == 'guard':
                if fleet['guard_power'] >= guard_required(p.world):
                    raise ValueError('现有护卫已足额')
                transfer_value(game, 'player', f'background:{p.world}', max(100, round(guard_required(p.world) ** .5) * 5), '聘请商队护卫')
                fleet['guard_power'] = guard_required(p.world)
            else:
                transfer_value(game, 'player', f'caravan:{fleet["id"]}', capital, '商队追加周转金')
                fleet['investment'] += capital
    elif action in {'found', 'regional_hq', 'affiliate'}:
        if game.merchant_state.get('active'):
            raise ValueError('请先完成当前商盟委托')
        candidates = [f for f in region['fleets'].values() if f['owner_kind'] == 'independent'
                      and f['status'] == 'waiting' and not f['cargo'] and not f.get('cross_trip')
                      and (f['pledged'] or f['player_controlled'])]
        if action == 'found':
            if home or game.merchant_state.get('membership'):
                raise ValueError('已有自建商盟或仍在其他商盟任职')
            own = [f for f in candidates if f['player_controlled']]
            others = [f for f in candidates if not f['player_controlled'] and f['pledged']]
            if not own or len(others) < 2:
                raise ValueError('成立商盟需要自己的商队及另两支已招揽的无势力商队')
            transfer_value(game, 'player', f'background:{p.world}', 20000 * tier, '设立商盟总部与聘用主事')
            alliance = _create_alliance(game, region, [own[0], *others[:2]])
        else:
            true_realm = (p.sealed_cultivation or {}).get('realm_index', p.realm_index)
            if (not home or true_realm < 8 or WORLD_SYSTEMS['world_profiles'][home['world']]['tier'] < 2
                    or home['world'] == p.world or alliance):
                raise ValueError('需大乘道果、位于二级以上界面的自建总部，并亲赴尚未设分总部的异界')
            cap = int(WORLD_SYSTEMS['world_profiles'][p.world]['npc_realm_cap'])
            home['chief_realm'] = true_realm
            if action == 'regional_hq':
                if len(candidates) < 3:
                    raise ValueError('分总部需要三支本界已招揽的无势力商队')
                transfer_value(game, 'player', f'background:{p.world}', 1000000 * tier, '异界分总部营建及坐镇修士聘任')
                alliance = _create_alliance(game, region, candidates[:3], home)
            else:
                alliance = alliance_at(game, p.world, str(payload.get('alliance_id', '')))
                if not alliance or alliance['cross_world'] or alliance['hq'] != p.location_id:
                    raise ValueError('请前往尚未归属跨界网络的本地商盟总部洽谈')
                if alliance['leader']['realm_index'] < cap - 1 or combat_power(p) < alliance['chief_power']:
                    raise ValueError('坐镇修为或说服所需实力不足')
                transfer_value(game, 'player', f'alliance:{p.world}:{alliance["id"]}', max(1000000 * tier, alliance['reserves']), '商盟加盟合作出资')
                alliance.update(network_id=identity, name=home['name'], home_world=home['world'], player_owned=True)
                for existing in active_fleets(game, p.world, 'alliance', alliance['id']):
                    existing['player_controlled'] = True
            worlds = sorted({*home['linked_worlds'], p.world})
            for world in worlds:
                row = alliance_at(game, world, identity)
                row.update(cross_world=True, linked_worlds=worlds, chief_realm=true_realm, chief_name=p.name)
            routes(game)[route_key(identity, home['world'], p.world)] = dict(alliance_id=identity,
                home=home['world'], branch=p.world, open=False, maintenance=0, paid=0, shortfall=0, last_year=p.age)
    elif action == 'branch':
        if not alliance or not alliance.get('player_owned'):
            raise ValueError('请先在本界建立自己的商盟')
        if p.location_id in {alliance['hq'], *(o['location_id'] for o in alliance['offices'])}:
            raise ValueError('这里已有本盟据点')
        if alliance['reserves'] < 40000 * tier or len(active_fleets(game, p.world, 'alliance', alliance['id'])) < 3:
            raise ValueError('建立分部需要三支存续商队和至少四万乘界层的本界储备')
        transfer_value(game, f'alliance:{p.world}:{alliance["id"]}', f'background:{p.world}', 20000 * tier, '商盟增设分部')
        leader = leader_record(game, f'merchant-{p.world}-{alliance["id"]}-{p.location_id}', '分部主事', max(1, alliance['leader']['realm_index'] - 1))
        alliance['offices'].append(dict(location_id=p.location_id, leader=leader))
    elif action in {'build_passage', 'reopen'}:
        from .headquarters import passage_command
        passage_command(game, deps.maps, home, alliance, payload)
    elif action == 'alliance_fund':
        if not alliance or p.location_id not in {alliance['hq'], *(o['location_id'] for o in alliance['offices'])}:
            raise ValueError('请前往本界自建商盟据点注资')
        transfer_value(game, 'player', f'alliance:{p.world}:{alliance["id"]}', 50000 * tier, '商盟本界府库注资')
    elif action in {'cross_dispatch', 'cross_recall'}:
        if not alliance or not fleet or fleet['alliance_id'] != alliance['id'] or p.location_id != alliance['hq']:
            raise ValueError('请在自建商盟总部指派本盟商队')
        from .cross_freight import dispatch, recall
        if action == 'cross_recall':
            recall(game, fleet)
        else:
            dispatch(game, deps.maps, fleet, str(payload.get('destination', '')), remittance_percent=payload.get('remittance_percent', 25))
    else:
        raise ValueError('未知商队经营操作')
    game.updated_at = now_iso()
    result = deps.present(game)
    deps.store.save(game)
    if committed:
        committed(game)
    return result


def public_network(game, maps):
    from .caravans import public_caravans
    from .local_market import trade_available
    p = game.player
    own = controlled_alliance(game)
    home = home_alliance(game)
    fleets = public_caravans(game, maps)
    from .trade_orders import authorized
    from .state import commodity_catalog
    from .enterprise_view import known_estates
    for view in fleets:
        fleet = game.economy_v2['transport']['worlds'][p.world]['fleets'][view['id']]
        try:
            authorized(game, fleet)
            view.update(can_order=True, trade_order=copy.deepcopy(fleet.get('trade_order', {'mode':'auto'})))
        except ValueError:
            view['can_order'] = False
    member = game.merchant_state.get('membership') or {}
    joined = next((a for a in game.merchant_state.get('worlds', {}).get(p.world, []) if member_of(game, a)), None)
    tier = WORLD_SYSTEMS['world_profiles'][p.world]['tier']
    can_apply = bool(joined and p.location_id in {joined['hq'], *(o['location_id'] for o in joined['offices'])}
                     and len(active_fleets(game, p.world, 'alliance', joined['id'])) < fleet_limit('alliance', joined))
    from .fleet_network import route_path, leg_years
    identity = home.get('network_id', home['id']) if home else None
    destinations = []
    for world in own['linked_worlds'] if own else []:
        if world == p.world:
            continue
        path = route_path(game, own, world)
        destinations.append(dict(world=world, name=WORLD_SYSTEMS['world_names'][world], open=bool(path),
            path=[WORLD_SYSTEMS['world_names'][w] for w in path], years=sum(leg_years(a, b) for a, b in zip(path, path[1:]))))
    return dict(can_act=trade_available(game), fleets=fleets, owned=own['id'] if own else None,
        order_goods=[dict(id=k, name=v['name']) for k,v in commodity_catalog().items()],
        order_sites=[dict(id=k, name=v['name']) for k,v in maps._locations.get(p.world, {}).items()],
        order_estates=known_estates(game, maps),
        can_apply=can_apply, found_cost=20000 * tier, branch_cost=20000 * tier,
        hq_cost=1000000 * tier, passage_cost=10000000 * tier, pledge_cost=1000 * tier,
        guard_cost=max(100, round(guard_required(p.world) ** .5) * 5) if tier > 0 else 0,
        has_home=bool(home), world=p.world, location=p.location_id, destinations=destinations,
        at_hq=bool(own and own['hq'] == p.location_id), main_hq=bool(own and own['home_world'] == p.world),
        relocation_cost=(20000 if home and home['world'] == p.world else 1000000) * tier,
        capital=5000 * WORLD_SYSTEMS['world_profiles'][p.world]['tier'],
        routes=[{k:r[k] for k in ('home', 'branch', 'open', 'maintenance')} | dict(
            id=route_key(r['alliance_id'], r['home'], r['branch']), owned=r['alliance_id'] == identity,
            repair_cost=(maintenance_quote(game, home['world'], home['hq']) if home and r['alliance_id'] == identity and (r.get('built') or r['paid'])
                         else 10000000 * max(WORLD_SYSTEMS['world_profiles'][w]['tier'] for w in (r['home'], r['branch']))),
            home_name=WORLD_SYSTEMS['world_names'][r['home']], branch_name=WORLD_SYSTEMS['world_names'][r['branch']])
            for r in routes(game).values() if p.world in {r['home'], r['branch']}],
        alliances=[dict(id=a['id'], name=a['name'], count=len(active_fleets(game, p.world, 'alliance', a['id'])),
                       capacity=fleet_limit('alliance', a)) for a in game.merchant_state.get('worlds', {}).get(p.world, [])])
