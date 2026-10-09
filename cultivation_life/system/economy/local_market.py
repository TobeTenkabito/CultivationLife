"""Local market commands and bridges for the existing shop frontends."""
import copy
import math

from ...content_registry import ITEM_CATALOG, restricted_acquisition
from ...models import HistoryRecord
from ...rules import add_item, remove_item
from ...runtime import now_iso
from .ledger import balance, account, transfer_value, record_external
from .state import ensure_state, ensure_market, local_market, operator_account, reprice, settings
from .dependencies import MarketDependencies
from .basket_trade import quote


def trade_available(game):
    p = game.player
    from ..buddhist.rules import buddhist_active
    session = game.buddhist_state.get('assembly') or {}
    at_assembly = buddhist_active(game) and (session.get('world'), session.get('location')) == (p.world, p.location_id)
    return not (not p.alive or game.pending_event or p.imprisonment or game.active_trial or p.ghost_captor
                or p.realm_index == 0 or p.world in {'lost', 'rift'}
                or game.guixu_state.get('player_session') or at_assembly)


def require_access(game):
    if not trade_available(game):
        raise ValueError('当前状态无法交易本地市场商品')


def trade(deps: MarketDependencies, game_id, payload, *, committed=None):
    # Copy-on-write also protects the request cache when save or presentation fails.
    game = copy.deepcopy(deps._load(game_id))
    require_access(game)
    ensure_market(game, deps.maps)
    market = local_market(game)
    if type(payload.get('revision')) is not int or type(payload.get('total')) is not int:
        raise ValueError('报价编号与金额必须为整数')
    if payload.get('market_id') != market['id'] or payload.get('revision') != market['revision']:
        raise ValueError('市场报价已经变化，请刷新后重新交易')
    item_id = payload.get('item_id')
    row = market['commodities'].get(item_id)
    if not row or item_id not in ITEM_CATALOG or restricted_acquisition('item', item_id):
        raise ValueError('本地市场没有这件标准商品')
    side, quantity = payload.get('side'), payload.get('quantity')
    bill = quote(row, side, quantity)
    if payload.get('total') != bill['total']:
        raise ValueError('成交金额已经变化，请刷新后重新交易')
    cash, operator = f'market:{market["id"]}', operator_account(game)
    if side == 'buy':
        if row['tier'] > game.player.realm_index + 1:
            raise ValueError('修为不足，暂不能购买此阶商品')
        if row['stock'] + 1e-9 < quantity:
            raise ValueError('本地库存不足')
        if balance(game, 'player') < bill['total']:
            raise ValueError('灵石不足')
        transfer_value(game, 'player', cash, bill['total'], '本地市场购货')
        transfer_value(game, cash, operator, bill['fee'], '交易手续费')
        add_item(game.player, item_id, quantity)
        row['stock'] -= quantity
    else:
        if balance(game, cash) < bill['gross']:
            raise ValueError('市场收购资金不足，请减少数量或等待回款')
        if not remove_item(game.player, item_id, quantity):
            raise ValueError('持有商品数量不足')
        transfer_value(game, cash, 'player', bill['total'], '本地市场收购')
        transfer_value(game, cash, operator, bill['fee'], '交易手续费')
        row['stock'] += quantity
    from .market_power import record_trade
    record_trade(game, market, item_id, 'player', side, quantity)
    row['volume'] += quantity
    market['turnover'] += bill['gross']
    market['fees'] += bill['fee']
    reprice(game, market, row)
    game.history.append(HistoryRecord('SYS_LOCAL_MARKET', 1, game.player.age, '本地市场成交',
        item_id, side, f"{'买入' if side == 'buy' else '卖出'}{ITEM_CATALOG[item_id].name} ×{quantity}，"
        f"{'支付' if side == 'buy' else '实得'} {bill['total']:,} 灵石，含手续费 {bill['fee']:,}。",
        dict(quantity=quantity, **bill), ['system', 'market', f'world:{game.player.world}']))
    game.updated_at = now_iso()
    result = deps.present(game)
    deps.store.save(game)
    if committed:
        committed(game)
    return result


def shelf_price(game, offer):
    if offer.get('locked'):
        return int(offer['price'])
    market = local_market(game)
    row = market['commodities'].get(offer['content_id']) if market else None
    base = offer.get('economy_base_price', offer['price'])
    return max(1, round(base * row['price'] / row['reference'])) if row else int(offer['price'])


def sync_shelf(game):
    """The dealer reserves displayed standard goods exactly once, including locks."""
    market = local_market(game)
    if not market:
        return False
    changed = False
    for offer in game.market_offers:
        if offer.get('world') != market['world'] or offer.get('location_id') != market['location']:
            continue
        if offer.get('sold') or offer.get('economy_reserved'):
            continue
        row = market['commodities'].get(offer['content_id'])
        if row:
            if row['stock'] < 1:
                changed = changed or not offer.get('economy_unavailable', False)
                offer['economy_unavailable'] = True
                continue
            offer['economy_base_price'] = offer['price']
            offer['price'] = shelf_price(game, offer)
            row['stock'] -= 1
            market['revision'] += 1
            offer['economy_reserved'] = market['id']
            offer.pop('economy_unavailable', None)
            changed = True
    return changed


def release_shelf(game, retained):
    keep = {o['id'] for o in retained}
    for offer in game.market_offers:
        if offer['id'] in keep or offer.get('sold'):
            continue
        key = offer.get('economy_reserved')
        market = game.economy_v2.get('markets', {}).get(key or f"{offer.get('world')}:{offer.get('location_id')}")
        if not market:
            continue
        if offer.get('locked'):
            reserved = market.setdefault('reserved_offers', [])
            if not any(row['id'] == offer['id'] for row in reserved):
                reserved.append(copy.deepcopy(offer))
            continue
        row = market['commodities'].get(offer['content_id'])
        if row and key:
            row['stock'] += 1
            market['revision'] += 1
            offer.pop('economy_reserved', None)


def pay_shelf(game, offer, price):
    if offer.get('economy_unavailable'):
        raise ValueError('商家尚未补到这件货物')
    market = local_market(game)
    if not market:
        raise ValueError('此处没有本地市场')
    cash = f'market:{market["id"]}'
    fee = math.floor(price * settings()['transaction_fee'])
    transfer_value(game, 'player', cash, price, '坊市货架购货')
    transfer_value(game, cash, operator_account(game), fee, '坊市交易手续费')
    if offer.get('content_id') in market['commodities']:
        from .market_power import record_trade
        record_trade(game, market, offer['content_id'], 'player', 'buy', 1)
    market['turnover'] += price
    market['fees'] += fee
    market['revision'] += 1


def legacy_sale(game, amount, reason, *, black_market=False):
    """Keep established independent-item valuations; book a real counterparty."""
    ensure_state(game)
    if black_market:
        source = f'background:{game.player.world}'
    else:
        market = local_market(game)
        if not market:
            raise ValueError('此处没有本地市场')
        source = f'market:{market["id"]}'
        market['unique_sales'] += 1
        market['turnover'] += amount
    transfer_value(game, source, 'player', int(amount), reason)


def black_market_receipt(game, amount, quantity):
    ensure_state(game)
    # The existing purchase has already removed this exact sum from the inventory.
    record_external(game, 'player', f'world:{game.player.world}', int(amount), '黑市保底购货')
    world = game.economy_v2['worlds'][game.player.world]
    world['black_market_volume'] += amount
    world['black_market_quantity'] += quantity


def auction_fee(game, amount, reason):
    venue = game.auction_state
    destination = operator_account(game, venue.get('world'), venue.get('location_id'))
    if reason == '拍卖占位费':
        record_external(game, 'player', destination, int(amount), reason)
    else:
        transfer_value(game, f'background:{game.player.world}', destination, int(amount), reason)
