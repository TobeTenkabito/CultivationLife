"""Local property deeds and inventory commands inside the existing transaction."""
from ...rules import add_item, remove_item
from ...content_registry import ITEM_CATALOG
from .enterprise_acquisition import price, acquire
from .enterprise_rules import KINDS, MAX_LEVEL, title_cost, recipes, capacity
from .enterprise_state import estates, payer, owner_allowed, require_local, cash_ready, quantity, put, take, encumbered, log
from .enterprise_operations import market_at, market_trade, start_job
from .state import commodity_catalog
from .ledger import account, balance, transfer_value


def actor(game, kind):
    p = game.player
    if kind == 'player':
        return game.id, 'player'
    if kind == 'family':
        identity = game.family.id if game.family else ''
    elif kind == 'sect':
        identity = p.faction_id
    elif kind == 'alliance':
        owner = next((a for a in game.merchant_state['worlds'].get(p.world, []) if a.get('player_owned')), None)
        identity = owner['id'] if owner else ''
    else:
        raise ValueError('机构不参与这类产业投资')
    if not owner_allowed(game, kind, identity, p.world):
        raise ValueError('只有本人或组织执掌者可以办理产权')
    if kind in {'sect', 'family'}:
        from .organizations import register
        register(game, kind, identity, p.world)
    return identity, f'alliance:{p.world}:{identity}' if kind == 'alliance' else f'organization:{kind}:{identity}'



def command(game, maps, payload):
    action = payload['action'].removeprefix('estate_')
    p = game.player
    if action == 'buy':
        kind = payload.get('kind')
        if kind not in KINDS:
            raise ValueError('未知产业类型')
        if type(payload.get('cost')) is not int:
            raise ValueError('请先取得有效产权报价')
        owner_kind = payload.get('owner_kind', 'player')
        identity, source = actor(game, owner_kind)
        acquire(game, maps, p.world, p.location_id, kind, owner_kind, identity, source, p.realm_index, payload.get('cost'))
        return
    row = require_local(game, payload.get('estate_id'))
    if type(payload.get('revision')) is not int or payload['revision'] != row['revision']:
        raise ValueError('产业状态已经变化，请刷新后重新操作')
    key = cash_ready(game, row)
    if action == 'fund':
        if row['owner_kind'] != 'player':
            raise ValueError('组织产业使用原府库，请通过既有组织注资入口办理')
        transfer_value(game, 'player', key, quantity(payload.get('amount'), 10**12), '产业追加周转金')
    elif action == 'withdraw_cash':
        if row['owner_kind'] != 'player' or row['arrears']:
            raise ValueError('只可提取本人产业的无欠费现金')
        transfer_value(game, key, 'player', quantity(payload.get('amount'), 10**12), '在产业所在地提取经营现金')
    elif action == 'pay_arrears':
        transfer_value(game, key, f'background:{p.world}', row['arrears'], '结清产业仓储欠费')
        row['expense'] += row['arrears']
        row['arrears'] = 0
    elif action == 'entrust':
        if type(payload.get('enabled')) is not bool:
            raise ValueError('请明确启用或收回委托')
        row['entrusted'] = payload['enabled']
        if row['entrusted']:
            from .estate_management import plan
            plan(game, maps, row)
        log(row, p.age, '委托驻地掌柜自动经营' if row['entrusted'] else '收回经营委托，保留当前批次与方案')
    elif action == 'configure':
        row['entrusted'] = False
        for name in ('enabled', 'auto_buy', 'auto_sell'):
            if type(payload.get(name)) is not bool:
                raise ValueError('经营开关必须明确设置')
        recipe = payload.get('recipe')
        catalog = commodity_catalog(p.world)
        options = recipes(p.world, catalog)
        product = recipe if row['kind'] == 'shop' else (options.get(recipe) or {}).get('output')
        if product not in catalog or catalog[product]['tier'] > p.realm_index + 1:
            raise ValueError('本界商品或经营资质不满足所选配方')
        if row['kind'] != 'shop' and options[recipe]['kind'] != row['kind']:
            raise ValueError('该配方不适用于此产业')
        batches = quantity(payload.get('batches'), row['level'] * 4)
        quota = payload.get('sale_quota', row.get('sale_quota', 1000000))
        if type(quota) is not int or not 0 <= quota <= 1000000:
            raise ValueError('每次结算的自动出货上限须为零至一百万件')
        for name in ('buy_limit', 'sell_limit'):
            if type(payload.get(name)) is not int or not 0 <= payload[name] <= 10**12:
                raise ValueError('买卖单价限制须为非负整数')
        for name, default in (('reserve_cash',100),('expense_limit',100000)):
            value=payload.get(name,row.get(name,default))
            if type(value) is not int or not 0 <= value <= 10**12:
                raise ValueError('自动经营储备和单次支出上限须为非负整数')
            row[name]=value
        row.update({k:payload[k] for k in ('enabled', 'auto_buy', 'auto_sell', 'buy_limit', 'sell_limit')})
        row.update(recipe=recipe, batches=batches, sale_quota=quota)
    elif action == 'start':
        start_job(game, maps, row)
    elif action == 'upgrade':
        if row['level'] >= MAX_LEVEL:
            raise ValueError('产业已达五级上限')
        cost = price(game, maps, row, row['level'] + 1)
        if payload.get('cost') != cost:
            raise ValueError('扩建报价已变化')
        transfer_value(game, key, f'background:{p.world}', cost, '产业与仓储扩建')
        row['level'] += 1
        row['expense'] += cost
    elif action in {'deposit', 'withdraw', 'purchase', 'sell', 'move_stock'}:
        item, number = payload.get('item'), quantity(payload.get('quantity'))
        if item not in commodity_catalog() or item not in ITEM_CATALOG:
            raise ValueError('产业仓库只接收可流通的标准商品')
        if action == 'deposit':
            if not remove_item(p, item, number):
                raise ValueError('背包标准商品数量不足')
            put(row, item, number)
        elif action == 'withdraw':
            take(row, item, number)
            add_item(p, item, number)
        elif action == 'move_stock':
            target = require_local(game, payload.get('target_estate'))
            if target is row or (target['owner_kind'], target['owner_id']) != (row['owner_kind'], row['owner_id']):
                raise ValueError('仅可在同地、同一所有者的不同产业间调拨；异地请委托商队')
            take(row, item, number)
            put(target, item, number)
            target['revision'] += 1
        else:
            market = market_at(game, maps, row)
            from .local_market import quote
            product = market['commodities'].get(item)
            if not product or (action == 'purchase' and product['tier'] > p.realm_index + 1):
                raise ValueError('本地没有此商品或购买资质不足')
            bill = quote(product, 'buy' if action == 'purchase' else 'sell', number)
            if payload.get('market_revision') != market['revision'] or payload.get('total') != bill['total']:
                raise ValueError('市场报价已变化，请刷新后重新交易')
            market_trade(game, row, market, item, number, 'buy' if action == 'purchase' else 'sell')
    elif action in {'release', 'transfer'}:
        if row['job'] or row['stock'] or row['arrears'] or encumbered(game, row['id']):
            raise ValueError('请先结清生产、库存、欠费和关联商路订单，再办理产权交接')
        refund = price(game, maps, row) // 2
        if payload.get('cost') != refund:
            raise ValueError('产权转让报价已变化')
        recipient = 'player' if row['owner_kind'] == 'player' else key
        if action == 'transfer':
            kind = payload.get('owner_kind')
            identity, source = actor(game, kind)
            if (kind, identity) == (row['owner_kind'], row['owner_id']):
                raise ValueError('不能向原所有者转让')
        else:
            kind, identity, source = 'background', p.world, f'background:{p.world}'
        transfer_value(game, source, recipient, refund, '产业产权实付转让')
        if row['owner_kind'] == 'player':
            transfer_value(game, key, 'player', balance(game, key), '产权交接提回原经营现金')
        row.update(owner_kind=kind, owner_id=identity, enabled=False, entrusted=False, last_year=p.age)
        if kind != 'background':
            cash_ready(game, row)
        log(row, p.age, '产权有偿交接；矿藏储量、等级与原编号保留')
    else:
        raise ValueError('未知产业操作')
    row['revision'] += 1
