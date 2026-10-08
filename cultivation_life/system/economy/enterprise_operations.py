"""Paid input acquisition, timed production and finite local sales."""
import math
from .enterprise_market import market_at
from .enterprise_rules import recipes, capacity
from .enterprise_state import estates, payer, cash_ready, put, take, used, log, owner_allowed
from .ledger import balance, transfer_value
from .local_market import quote
from .state import ensure_regional_market, commodity_catalog, reprice



def market_trade(game, row, market, item, number, side):
    product = market['commodities'].get(item)
    if not product:
        raise ValueError('本地市场尚无这件标准商品')
    bill = quote(product, side, number)
    key = cash_ready(game, row)
    dealer, operator = f'market:{market["id"]}', f'operator:{market["id"]}'
    if side == 'buy':
        if product['stock'] < number or balance(game, key) < bill['total']:
            raise ValueError('采购库存或产业周转金不足')
        put(row, item, number)
        transfer_value(game, key, dealer, bill['total'], '产业仓库采购实货')
        transfer_value(game, dealer, operator, bill['fee'], '产业采购手续费')
        product['stock'] -= number
        from .market_power import record_trade
        record_trade(game, market, item, f'estate:{row["id"]}', 'buy', number)
        row['expense'] += bill['total']
    else:
        if balance(game, dealer) < bill['gross']:
            raise ValueError('本地市场收购资金不足')
        take(row, item, number)
        transfer_value(game, dealer, key, bill['total'], '产业仓库实货销售')
        transfer_value(game, dealer, operator, bill['fee'], '产业销售手续费')
        product['stock'] += number
        row['income'] += bill['total']
        from .industry import supplier_delivery
        supplier_delivery(market, f'estate:{row["id"]}', number, game=game, item=item)
    product['volume'] += number
    market['turnover'] += bill['gross']
    market['fees'] += bill['fee']
    reprice(game, market, product)
    return bill


def start_job(game, maps, row):
    if row['job'] or row['kind'] == 'shop':
        raise ValueError('已有在制批次，或该产业不从事生产')
    recipe = recipes(row['world'], commodity_catalog(row['world'])).get(row['recipe'])
    if not recipe or recipe['kind'] != row['kind']:
        raise ValueError('此产业尚未配置有效配方')
    market = market_at(game, maps, row)
    batches = row['batches']
    count = batches * recipe['quantity']
    inputs = {k:q * batches for k,q in recipe['inputs'].items()}
    missing = {k:max(0, q - row['stock'].get(k, 0)) for k,q in inputs.items()}
    if not row['auto_buy'] and any(missing.values()):
        raise ValueError('仓库原料不足；补充原料或开启自动采购')
    if used(row) + sum(missing.values()) > capacity(row) or used(row) + sum(missing.values()) - sum(inputs.values()) + count > capacity(row):
        raise ValueError('原料与预留成品超过仓储容量')
    if row['kind'] == 'mine' and row['reserve'] < count:
        raise ValueError('此矿区剩余储量不足，不能凭空再生矿藏')
    wage = max(1, math.ceil(market['commodities'][recipe['output']]['price'] * count * recipe['labor']))
    total = wage
    for item, number in missing.items():
        if not number:
            continue
        product = market['commodities'][item]
        bill = quote(product, 'buy', number)
        if product['stock'] < number or bill['total'] > number * row['buy_limit']:
            raise ValueError('原料库存不足或采购均价超过设定上限')
        total += bill['total']
    source = cash_ready(game, row)
    if balance(game, source) < total or row['arrears']:
        raise ValueError('产业周转金不足，或尚有仓储欠费')
    for item, number in missing.items():
        if number:
            market_trade(game, row, market, item, number, 'buy')
    for item, number in inputs.items():
        take(row, item, number)
    transfer_value(game, source, f'background:{row["world"]}', wage, '产业工匠、种植或采掘劳务')
    row['expense'] += wage
    if row['kind'] == 'mine':
        row['reserve'] -= count
    row['job'] = dict(recipe=row['recipe'], item=recipe['output'], quantity=count, inputs=inputs,
                      started=game.player.age, finish=game.player.age + recipe['years'], cost=total)
    log(row, game.player.age, f'已付原料与劳务，投产 {batches} 批；第 {row["job"]["finish"]} 年完工')


def sell_stock(game, row, market):
    recipe = recipes(row['world'], commodity_catalog(row['world'])).get(row['recipe'])
    output = row['recipe'] if row['kind'] == 'shop' else (recipe or {}).get('output')
    for item, number in list(row['stock'].items()):
        if item not in market['commodities'] or item != output:
            continue
        product = market['commodities'][item]
        low, high = 0, min(number, row.get('sale_quota', 1000000))
        while low < high:
            mid = (low + high + 1) // 2
            sale = quote(product, 'sell', mid)
            if sale['gross'] <= balance(game, f'market:{market["id"]}') and sale['total'] >= mid * row['sell_limit']:
                low = mid
            else:
                high = mid - 1
        if low:
            market_trade(game, row, market, item, low, 'sell')


def advance_estates(game, maps):
    for row in estates(game).values():
        years = game.player.age - row['last_year']
        if years <= 0:
            continue
        row['last_year'] = game.player.age
        row['revision'] += 1
        if row['owner_kind'] == 'background':
            continue
        if row['owner_kind'] in {'sect', 'family'}:
            entity = game.family if row['owner_kind'] == 'family' else game.sects.get(row['owner_id'])
            if not entity or entity.extinct or entity.world != row['world']:
                continue
        if row['owner_kind'] == 'alliance':
            if not any(a['id'] == row['owner_id'] for a in game.merchant_state.get('worlds', {}).get(row['world'], [])):
                continue
        if row['owner_kind'] == 'player' and row['owner_id'] != game.id:
            continue  # Lost ownership authority never copies the estate to a new world.
        if row.get('entrusted'):
            from .estate_management import plan
            plan(game, maps, row)
        market = market_at(game, maps, row)
        due = min(10**12, row['arrears'] + max(1, math.ceil(sum(row['stock'].get(k, 0) * v['price'] * .002
                            for k,v in market['commodities'].items()))) * years)
        source = cash_ready(game, row)
        paid = min(due, balance(game, source))
        transfer_value(game, source, f'background:{row["world"]}', paid, '产业年度仓储及场地养护')
        row['expense'] += paid
        row['arrears'] = due - paid
        if row['job'] and game.player.age >= row['job']['finish']:
            job = row['job']
            row['job'] = None
            put(row, job['item'], job['quantity'])
            row['produced'] += job['quantity']
            log(row, game.player.age, f'实物完工入库 {job["quantity"]} 件')
        if not row['enabled']:
            continue
        if row['auto_sell']:
            sell_stock(game, row, market)
        if row['kind'] == 'shop' and row['auto_buy'] and not row['arrears'] and row['recipe'] in market['commodities']:
            item = row['recipe']
            amount = min(row['batches'] * 4 - row['stock'].get(item, 0), capacity(row) - used(row))
            if amount > 0 and quote(market['commodities'][item], 'buy', amount)['total'] <= amount * row['buy_limit']:
                try:
                    market_trade(game, row, market, item, amount, 'buy')
                except ValueError:
                    pass
        elif not row['job'] and not row['arrears'] and (not row.get('entrusted') or row['auto_buy']):
            try:
                start_job(game, maps, row)
            except ValueError as exc:
                log(row, game.player.age, str(exc))
