"""Shared paid deed acquisition; one owner and one fixed stock ledger."""
from .enterprise_market import market_at
from .enterprise_rules import recipes, title_cost
from .enterprise_state import estates, cash_ready, log
from .state import commodity_catalog
from .ledger import transfer_value


def price(game, maps, row, level=None):
    market = market_at(game, maps, row)
    goods = [r for r in market['commodities'].values() if not r.get('imported')]
    multiplier = sum(r['price'] / r['reference'] for r in goods) / max(1, len(goods))
    return max(1, round(title_cost(row['world'], row['kind'], level or row['level']) * multiplier))


def acquire(game, maps, world, location, kind, owner_kind, identity, source, realm_index, expected_cost=None):
    key = f'{world}:{location}:{kind}'
    existing = estates(game).get(key)
    if existing and existing['owner_kind'] != 'background':
        raise ValueError('该地块已有产权所有者')
    options = recipes(world, commodity_catalog(world))
    catalog = commodity_catalog(world)
    recipe = next((k for k,r in options.items() if r['kind'] == kind and catalog[r['output']]['tier'] <= realm_index + 1), None)
    row = existing or dict(id=key, kind=kind, world=world, location=location, level=1, reserve=5000,
        recipe=recipe, stock={}, job=None, produced=0, income=0, expense=0, arrears=0,
        enabled=False, auto_buy=False, auto_sell=False, batches=1, buy_limit=10**12,
        sell_limit=0, history=[], revision=0, last_year=game.player.age)
    cost = price(game, maps, row)
    if expected_cost is not None and expected_cost != cost:
        raise ValueError('产权报价已变化，请刷新后重新办理')
    transfer_value(game, source, f'background:{world}', cost, '购入固定地点产业产权')
    row.update(owner_kind=owner_kind, owner_id=identity, last_year=game.player.age, enabled=False, entrusted=False, revision=row['revision'] + 1)
    game.economy_v2.setdefault('estates', {})[key] = row
    cash_ready(game, row)
    log(row, game.player.age, '产权登记完成；库存、储量与产业地点保持唯一')
    return row

