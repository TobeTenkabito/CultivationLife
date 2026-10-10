"""Fixed-site organizational stores, paid purchases and delayed requisitions."""
import copy
from functools import lru_cache
from math import ceil
from ...content_registry import ITEM_CATALOG, TECHNIQUE_CATALOG, MARKET_GOODS, WORLD_SYSTEMS, restricted_acquisition
from ...rules import add_item, add_technique_copy
from ...npc_custody import is_free
from ..faction_geography import faction_site
from .ledger import balance, transfer_value
from .state import ensure_regional_market, reprice
from .local_market import quote


def owner_kind(game, entity):
    return 'family' if entity is game.family else 'sect'


def treasury(game, entity):
    return f'organization:{owner_kind(game, entity)}:{entity.id}'


def find(game, entity):
    return game.economy_v2.get('depots', {}).get(f'{entity.world}:{entity.id}:{entity.location_id}')


def ensure(game, entity):
    site = faction_site(entity)['id']
    return game.economy_v2.setdefault('depots', {}).setdefault(f'{entity.world}:{entity.id}:{site}',
        dict(world=entity.world, location=site, owner=entity.id, kind=owner_kind(game, entity),
             stock={}, requests=[], sequence=0, revision=0, last_purchase=game.player.age, history=[]))


def record(row, game, message):
    row['revision'] += 1
    row['history'] = (row['history'] + [dict(year=game.player.age, text=message)])[-24:]


@lru_cache(maxsize=16)
def catalog(world):
    result = {}
    for good in MARKET_GOODS:
        kind, identity = good['kind'], good['content_id']
        if (good.get('world', 'human') != world or restricted_acquisition(kind, identity)
                or kind not in {'item', 'technique'} or identity == 'spirit_stone'):
            continue
        content = (ITEM_CATALOG if kind == 'item' else TECHNIQUE_CATALOG).get(identity)
        if content:
            result[f'{kind}:{identity}'] = dict(kind=kind, id=identity, name=content.name,
                price=max(1, int(good['price'])), tier=int(good['tier']))
    return result


@lru_cache(maxsize=16)
def manual_choices(world):
    offers=catalog(world)
    return tuple(sorted((k for k,r in offers.items() if r['kind']=='technique'),key=lambda k:(offers[k]['price'],k))[:2])


def unit_value(game, row, key):
    good = catalog(row['world']).get(key)
    if not good:
        return 0
    market = game.economy_v2['markets'].get(f"{row['world']}:{row['location']}", {})
    product = market.get('commodities', {}).get(good['id']) if good['kind'] == 'item' else None
    return max(1, round(product['price'] if product else good['price'] * game.economy_v2['worlds'][row['world']]['price_level']))


def worth(game, entity):
    row = find(game, entity)
    return sum(unit_value(game, row, k) * n for k, n in row['stock'].items()) if row else 0


def occupied(row):
    return sum(row['stock'].values()) + sum(r['reserved'] for r in row['requests'])


def purchase(game, maps, entity, key, quantity):
    row = ensure(game, entity)
    good = catalog(row['world']).get(key)
    if not good or type(quantity) is not int or not 1 <= quantity <= 1000:
        raise ValueError('请选择可流通府库物资，数量为 1 至 1000')
    if occupied(row) + quantity > 10000:
        raise ValueError('府库实物容量已满（10000 件）')
    ensure_regional_market(game, maps, row['world'], row['location'])
    market = game.economy_v2['markets'][f"{row['world']}:{row['location']}"]
    source = treasury(game, entity)
    if good['kind'] == 'item':
        product = market['commodities'].get(good['id'])
        if not product or int(product['stock']) < quantity:
            raise ValueError('本地市场库存不足')
        bill = quote(product, 'buy', quantity)
        if balance(game, source) < bill['total']:
            raise ValueError('府库灵石不足')
        transfer_value(game, source, f'market:{market["id"]}', bill['total'], '府库采购实物')
        transfer_value(game, f'market:{market["id"]}', f'operator:{market["id"]}', bill['fee'], '府库采购手续费')
        product['stock'] -= quantity
        product['volume'] += quantity
        from .market_power import record_trade
        record_trade(game, market, good['id'], source, 'buy', quantity)
        reprice(game, market, product)
    else:
        # Ordinary manuals are paid local copying work, with a bounded annual
        # publisher capacity. Unique equipment and mastered techniques aren't copied.
        orders = market.get('manual_orders', {})
        old = orders.get(good['id'], {})
        used = old.get('quantity', 0) if old.get('year') == game.player.age else 0
        if used + quantity > 12:
            raise ValueError('当地书坊本年抄录额度不足')
        gross = unit_value(game, row, key) * quantity
        bill = dict(gross=gross, fee=ceil(gross * .05), total=gross + ceil(gross * .05))
        if balance(game, source) < bill['total']:
            raise ValueError('府库灵石不足')
        transfer_value(game, source, f'market:{market["id"]}', bill['total'], '府库向当地书坊订购功法玉简')
        transfer_value(game, f'market:{market["id"]}', f'operator:{market["id"]}', bill['fee'], '书坊交易手续费')
        market.setdefault('manual_orders', {})[good['id']] = dict(year=game.player.age, quantity=used+quantity)
        market['revision'] += 1
    market['turnover'] += bill['gross']
    market['fees'] += bill['fee']
    row['stock'][key] = row['stock'].get(key, 0) + quantity
    record(row, game, f"采购{good['name']} ×{quantity}，实付 {bill['total']} 灵石")
    return bill['total']


def seniors(game, entity):
    people = sorted((n for n in entity.npcs if is_free(n) and n.world == entity.world),
                    key=lambda n: (-n.realm_index, -n.layer, n.id))
    positions = game.intrigue_state.get('factions', {}).get(f'{owner_kind(game, entity)}:{entity.id}', {})
    ids = {positions.get('controller_id'), *positions.get('positions', {}).values()}
    selected = [n for n in people if n.id in ids or n in people[:min(3, max(1, len(people)//3))]]
    return selected


def can_manage(game, entity):
    p = game.player
    if not (p.world == entity.world and (p.faction_id == entity.id or entity is game.family)):
        return False
    row = game.intrigue_state.get('factions', {}).get(f'{owner_kind(game, entity)}:{entity.id}', {})
    return bool(entity.founded_by_player or row.get('controller_id') == 'player'
                or 'player' in row.get('positions', {}).values())


def contribution_cost(good,quantity=1):
    return max(1,ceil(good['tier']*.75))*quantity


def refund_contribution(game,entity,request):
    reserved=request.get('contribution_reserved',0)
    if reserved and game.player.faction_id==entity.id and game.player.faction_join_age==request.get('join_age'):
        game.player.faction_contribution+=reserved
    request['contribution_reserved']=0


def approve(game, entity, request, approver):
    row = ensure(game, entity)
    if request['status'] != 'pending' or game.diplomacy_unit < request['ready_unit']:
        raise ValueError('申请须提前一个行动单位，且尚未结案')
    if approver != 'player' and approver not in {n.id for n in seniors(game, entity)}:
        raise ValueError('批准者须为本组织在世且自由的高层修士')
    if approver == 'player' and not can_manage(game, entity):
        raise ValueError('你没有本组织的审批权限')
    qty, key = request['quantity'], request['item']
    request.update(approver=approver, status='approved' if row['stock'].get(key, 0) >= qty else 'rejected')
    if request['status'] == 'approved':
        row['stock'][key] -= qty
        request['reserved'] = qty  # Unique escrow; neither stock nor war requisition may reuse it.
    else:
        refund_contribution(game,entity,request)
    record(row, game, f"申请 {request['id']}：{'批准并留存待领' if request['status']=='approved' else '库存不足，驳回'}")


def advance(game, maps, entity, finance):
    row = ensure(game, entity)
    if row['last_purchase'] >= game.player.age:
        return
    row['last_purchase'] = game.player.age
    # Purchase at most four lots per settlement, only from genuine operating
    # surplus. Zero cash never receives complimentary stock on adoption.
    budget = min(balance(game, treasury(game, entity)) // 10, max(0, finance['income'] - finance['expense']) // 4)
    from .basket_rules import candidates
    market=game.economy_v2['markets'][f'{entity.world}:{entity.location_id}']
    grade=max((int(r) for r in finance.get('workforce',{})),default=1)
    items=candidates(market,f'training:{grade}') or candidates(market,f'material:{grade}')
    chosen=[*manual_choices(entity.world),*('item:'+item for item in items[:2])]
    for key in chosen:
        if row['stock'].get(key, 0) >= 20 or occupied(row) >= 10000:
            continue
        if unit_value(game, row, key) * 1.1 > budget:
            continue
        try:
            paid = purchase(game, maps, entity, key, 1)
        except ValueError:
            continue
        budget -= paid
        finance['expense'] += paid
    for request in row['requests']:
        if request['status'] == 'pending' and game.diplomacy_unit >= request['ready_unit']:
            elder = next((n for n in seniors(game, entity) if (n.affinity or 0) >= 0), None)
            if elder:
                approve(game, entity, request, elder.id)


def command(game, maps, payload):
    identity = payload.get('owner_id')
    entity = game.family if game.family and game.family.id == identity else game.sects.get(identity)
    p = game.player
    if not entity or entity.extinct or entity.kind == 'institution' or entity.world != p.world:
        raise ValueError('只能办理本界存续宗门或家族的府库业务')
    if p.faction_id != identity and entity is not game.family:
        raise ValueError('你不是该组织成员')
    if faction_site(entity)['id'] != p.location_id:
        raise ValueError('请亲赴本组织驻地办理府库业务')
    row = ensure(game, entity)
    if type(payload.get('revision')) is not int or payload['revision'] != row['revision']:
        raise ValueError('府库账目已变化，请刷新后重试')
    action = payload['action']
    if action == 'depot_purchase':
        if not can_manage(game, entity):
            raise ValueError('须由门内高层安排采购')
        purchase(game, maps, entity, payload.get('item'), payload.get('quantity'))
    elif action == 'depot_request':
        key, qty = payload.get('item'), payload.get('quantity')
        good = catalog(entity.world).get(key)
        if not good or type(qty) is not int or not 1 <= qty <= 10 or row['stock'].get(key, 0) < qty:
            raise ValueError('申领数量须为 1 至 10 且不能超过库存')
        if good['tier'] > p.realm_index + 1:
            raise ValueError('此物资超出当前修为可申领品阶')
        if sum(r['status'] in {'pending','approved'} for r in row['requests']) >= 5:
            raise ValueError('最多保留五份未完成申请')
        cost=contribution_cost(good,qty) if entity.kind=='sect' else 0
        if p.faction_contribution<cost: raise ValueError(f'宗门贡献不足，本次申请需要{cost}点贡献')
        p.faction_contribution-=cost
        row['sequence'] += 1
        row['requests'] = [r for r in row['requests'] if r['status'] in {'pending','approved'}] + [r for r in row['requests'] if r['status'] not in {'pending','approved'}][-14:]
        row['requests'].append(dict(id=str(row['sequence']), applicant='player', item=key, quantity=qty,
            ready_unit=game.diplomacy_unit + 1, status='pending', approver=None, reserved=0,
            contribution_reserved=cost,join_age=p.faction_join_age))
        record(row, game, f"申请{good['name']} ×{qty}，一个行动单位后可审批")
    else:
        request = next((r for r in row['requests'] if r['id'] == payload.get('request_id')), None)
        if not request:
            raise ValueError('申请不存在')
        if action == 'depot_approve':
            approve(game, entity, request, 'player')
        elif action == 'depot_review':
            elder = next((n for n in seniors(game, entity) if n.id == payload.get('approver_id')), None)
            if not elder or (elder.affinity or 0) < 0:
                raise ValueError('该高层修士目前不愿批准申请')
            approve(game, entity, request, elder.id)
        elif action == 'depot_collect':
            if request['status'] != 'approved' or request['reserved'] != request['quantity']:
                raise ValueError('须获得高层批准后才能领取，不能重复领取')
            good = catalog(entity.world).get(request['item'])
            if not good:
                raise ValueError('此物资内容当前未启用；可取消申请归还原府库')
            if good['kind'] == 'item':
                add_item(p, good['id'], request['reserved'])
            else:
                for _ in range(request['reserved']):
                    add_technique_copy(p, copy.deepcopy(TECHNIQUE_CATALOG[good['id']]))
            request.update(status='collected', reserved=0,contribution_reserved=0)
            record(row, game, f"领取{good['name']} ×{request['quantity']}")
        elif action == 'depot_cancel':
            if request['status'] not in {'pending','approved'}:
                raise ValueError('该申请已经结案')
            row['stock'][request['item']] = row['stock'].get(request['item'], 0) + request['reserved']
            refund_contribution(game,entity,request)
            request.update(status='cancelled', reserved=0)
            record(row, game, '取消申请，已预留实物归还府库')
        else:
            raise ValueError('未知府库操作')


def public(game, entity):
    if not entity or entity.extinct or entity.world != game.player.world or entity.kind == 'institution':
        return None
    row = find(game, entity)
    offers = catalog(entity.world)
    stock = row['stock'] if row else {}
    return dict(owner_id=entity.id, name=entity.name, revision=row['revision'] if row else 0,
        location=entity.location_id, local=game.player.location_id == entity.location_id,
        can_manage=can_manage(game, entity), balance=int(game.intrigue_state.get('factions', {}).get(f'{owner_kind(game,entity)}:{entity.id}', {}).get('resources', 0)),
        value=worth(game, entity), unit=game.diplomacy_unit,
        contribution=game.player.faction_contribution if entity.kind=='sect' else None,
        stock=[dict(key=k, quantity=n, value=unit_value(game, row, k), contribution_cost=contribution_cost(offers[k]) if entity.kind=='sect' else 0,
            requestable=offers[k]['tier']<=game.player.realm_index+1 and (entity.kind!='sect' or game.player.faction_contribution>=contribution_cost(offers[k])), **offers[k]) for k,n in stock.items() if n and k in offers],
        offers=[dict(key=k, **v) for k,v in offers.items()][:128],
        seniors=[dict(id=n.id, name=n.name) for n in seniors(game, entity)],
        requests=copy.deepcopy(row['requests']) if row else [], history=list(row['history']) if row else [])
