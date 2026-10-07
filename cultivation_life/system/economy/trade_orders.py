"""One bounded standing instruction per fleet; no remote stock teleportation."""
import math
from .state import ensure_regional_market, commodity_catalog
from .local_market import quote
from .ledger import balance
from .enterprise_state import estates, owner_allowed, quantity, used, put
from .enterprise_rules import capacity


def authorized(game, fleet):
    from .fleet_network import alliance_at
    if not fleet or fleet['world'] != game.player.world or fleet['status'] == 'retired':
        raise ValueError('商队不在本界或已经解散')
    owner = alliance_at(game, fleet['world'], fleet['alliance_id']) if fleet['owner_kind'] == 'alliance' else None
    if not fleet.get('player_controlled') and not (owner and owner.get('player_owned')):
        raise ValueError('只能安排本人领办或自建商盟的商队')
    if game.player.location_id not in {fleet['location'], owner['hq'] if owner else None}:
        raise ValueError('请前往商队驻地或所属本界总部下达订单')


def configure(game, maps, fleet, payload):
    authorized(game, fleet)
    mode = payload.get('mode')
    if mode not in {'auto', 'hold', 'once', 'repeat'}:
        raise ValueError('请选择自动、停运、单次或长期订单')
    if mode in {'auto', 'hold'}:
        fleet['trade_order'] = dict(mode=mode)
        return
    if fleet.get('cargo') or fleet.get('cross_trip'):
        raise ValueError('请先完成当前运输；在途可以停用后续订单或调整限价')
    kind = payload.get('kind')
    if kind not in {'local', 'cross', 'delivery'}:
        raise ValueError('未知商路类型')
    item = payload.get('item')
    if item not in commodity_catalog():
        raise ValueError('订单只允许可流通的标准商品')
    count = quantity(payload.get('quantity'), fleet['capacity'])
    limits = {}
    for key in ('buy_limit', 'sell_limit'):
        value = payload.get(key)
        if type(value) is not int or not 0 <= value <= 10**12:
            raise ValueError('限价必须是非负整数')
        limits[key] = value
    destination = payload.get('destination')
    order = dict(mode=mode, kind=kind, origin=fleet['location'], destination=destination, item=item,
                 quantity=count, **limits)
    if kind == 'delivery':
        first, second = (estates(game).get(payload.get(k)) for k in ('source_estate', 'target_estate'))
        if (not first or not second or first is second or first['world'] != fleet['world']
                or first['location'] != fleet['location'] or first['world'] != second['world']
                or first['location'] == second['location']
                or (first['owner_kind'], first['owner_id']) != (second['owner_kind'], second['owner_id'])
                or not owner_allowed(game, first['owner_kind'], first['owner_id'], first['world'])):
            raise ValueError('调货需要同界异地、同一所有者的两处产业，商队须位于源仓所在地')
        order.update(source_estate=first['id'], target_estate=second['id'], destination=second['location'])
        destination = second['location']
    if kind != 'cross':
        maps.location(fleet['world'], destination)
        if destination == fleet['location']:
            raise ValueError('异地货运的起终点不能相同')
    else:
        from .fleet_network import alliance_at, route_path
        owner = alliance_at(game, fleet['world'], fleet['alliance_id'])
        if not owner or fleet['owner_kind'] != 'alliance' or len(route_path(game, owner, destination)) < 2:
            raise ValueError('该商队没有通往目标界面的开放通道')
        return_item = payload.get('return_item')
        if return_item and return_item not in commodity_catalog(destination):
            raise ValueError('返程货物须为目标界面可流通的本地商品')
        order['return_item'] = return_item
    fleet['trade_order'] = order
    fleet['next_departure'] = game.player.age
    fleet['next_cross'] = game.player.age


def update_limits(game, fleet, payload):
    authorized(game, fleet)
    low = payload.get('sell_limit')
    if type(low) is not int or not 0 <= low <= 10**12:
        raise ValueError('最低卖出均价须为非负整数')
    if fleet.get('trade_order') and fleet['trade_order']['mode'] in {'once', 'repeat'}:
        fleet['trade_order']['sell_limit'] = low
    cargo = fleet.get('cargo') or fleet.get('cross_trip')
    if cargo:
        cargo['sell_limit'] = low


def candidate(game, maps, fleet, route_quote):
    order = fleet.get('trade_order') or {}
    if order.get('mode') not in {'once', 'repeat'} or order.get('kind') == 'cross':
        return None
    world, origin = fleet['world'], fleet['location']
    returning = origin != order['origin']
    destination = order['origin'] if returning else order['destination']
    for place in (origin, destination):
        ensure_regional_market(game, maps, world, place)
    source = game.economy_v2['markets'][f'{world}:{origin}']
    target = game.economy_v2['markets'][f'{world}:{destination}']
    item, count = order['item'], order['quantity']
    if count > fleet['capacity']:
        raise ValueError('商队运力下降，请缩减订单数量')
    if returning:
        count = 0
    row = source['commodities'].get(item)
    if not row and count:
        raise ValueError('源市场没有所订商品')
    if item not in target['commodities'] and row:
        target['commodities'][item] = dict(row, stock=0., production=0., consumption=0., volume=0, history=[], imported=True)
    purchase = quote(row, 'buy', count) if count else dict(total=0, gross=0, fee=0)
    if order['kind'] == 'delivery' and not returning:
        estate = estates(game).get(order['source_estate'])
        target_estate = estates(game).get(order['target_estate'])
        if (not estate or not target_estate or estate['owner_kind'] == 'background'
                or (estate['owner_kind'], estate['owner_id']) != (target_estate['owner_kind'], target_estate['owner_id'])
                or estate['stock'].get(item, 0) < count):
            raise ValueError('源产业仓库库存不足')
        purchase = dict(total=0, gross=0, fee=0)
    elif count and (row['stock'] < count or purchase['total'] > count * order['buy_limit']):
        raise ValueError('订单库存不足或采购均价超过上限')
    plan = route_quote(game, maps, world, origin, destination, max(1, purchase['total']))
    if not plan:
        raise ValueError('当前地图没有可用运输路线')
    from .fleet_network import guard_required
    plan['risk'] = min(.95, plan['risk'] + .65 * max(0, 1 - fleet['guard_power'] / guard_required(world)))
    if any(w.get('status') in {'active','peace_ready'} and w.get('world') == world and w.get('location_id') in plan['route'] for w in game.wars):
        plan['risk'] = min(.95, plan['risk'] + .2)
    shipping = max(1, math.ceil(max(1, purchase['total'], count * (row['reference'] if row else 1)) * .003 * plan['normal_years']))
    plan.update(cost=shipping, array_fee=math.floor(shipping * plan['saved_ratio']))
    plan['transport_cost'] = shipping - plan['array_fee']
    if balance(game, f'caravan:{fleet["id"]}') < purchase['total'] + shipping:
        raise ValueError('商队周转金不足以执行订单')
    return dict(item=item, quantity=count, purchase=purchase, transport=plan, expected=0, cost=purchase['total'] + shipping,
                score=0, quoted_sale=0, sell_limit=order['sell_limit'], empty_return=returning,
                source_estate=order.get('source_estate'), target_estate=order.get('target_estate'))


def finish(fleet, cargo):
    order = fleet.get('trade_order') or {}
    if order.get('mode') == 'once':
        order['mode'] = 'hold'


def unload(game, fleet, cargo):
    """Arrival transfers only what fits; unpaid/blocked cargo stays aboard."""
    source = estates(game).get(cargo['source_estate'])
    target = estates(game).get(cargo['target_estate'])
    if (not source or not target or source['owner_kind'] == 'background'
            or (source['owner_kind'], source['owner_id']) != (target['owner_kind'], target['owner_id'])):
        return
    count = min(cargo['quantity'], capacity(target) - used(target))
    if count > 0:
        put(target, cargo['item'], count)
        target['revision'] += 1
        cargo['quantity'] -= count
        fleet['delivered'] += count
