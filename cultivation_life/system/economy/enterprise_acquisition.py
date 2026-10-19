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


def acquire(game, maps, world, location, kind, owner_kind, identity, source, realm_index, expected_cost=None, *, settling=False):
    key = f'{world}:{location}:{kind}'
    existing = estates(game).get(key)
    if existing and existing['owner_kind'] != 'background':
        raise ValueError('该地块已有产权所有者')
    options = recipes(world, commodity_catalog(world))
    catalog = commodity_catalog(world)
    from .resource_access import permits
    site=dict(world=world,location=location,kind=kind)
    recipe = next((k for k,r in options.items() if r['kind'] == kind and permits(site,r)
                   and catalog[r['output']]['tier'] <= realm_index + 1), None)
    row = existing or dict(id=key, kind=kind, world=world, location=location, level=1, reserve=5000,
        recipe=recipe, stock={}, job=None, produced=0, income=0, expense=0, arrears=0,
        enabled=False, auto_buy=False, auto_sell=False, batches=1, buy_limit=10**12,
        sell_limit=0, history=[], revision=0, last_year=game.player.age)
    cost = price(game, maps, row)
    if expected_cost is not None and expected_cost != cost:
        raise ValueError('产权报价已变化，请刷新后重新办理')
    transfer_value(game, source, f'background:{world}', cost, '购入固定地点产业产权')
    from .organization_accounts import prepare_ownership_change, book_expense
    _, finance = prepare_ownership_change(game, row, owner_kind, identity)
    row.pop('trust_config', None)
    row.pop('trust_profit_base', None)
    row.update(owner_kind=owner_kind, owner_id=identity, last_year=game.player.age,
               recipe=recipe, enabled=False, entrusted=False, auto_buy=False, auto_sell=False,
               revision=row['revision'] + 1)
    game.economy_v2.setdefault('estates', {})[key] = row
    cash_ready(game, row)
    if finance is not None:
        # Capital outlay is a period expense, not another production-cost
        # credit deducted from future sales. Personal deeds use inventory cash.
        if settling:
            finance['expense'] += cost  # Original autonomous settlement is in progress.
        else:
            book_expense(game, finance, cost)
    log(row, game.player.age, '产权登记完成；库存、储量与产业地点保持唯一')
    return row


def upgrade(game, maps, row, expected_cost=None):
    if row.get('building_status')=='destroyed':raise ValueError('产业设施已毁坏，不能扩建')
    from .enterprise_rules import MAX_LEVEL
    from .organization_accounts import estate_cost
    if row['level'] >= MAX_LEVEL:
        raise ValueError('产业已达五级上限')
    cost = price(game, maps, row, row['level'] + 1)
    if expected_cost is not None and cost != expected_cost:
        raise ValueError('扩建报价已变化')
    transfer_value(game, cash_ready(game, row), f'background:{row["world"]}', cost, '产业与仓储扩建')
    estate_cost(game, row, cost)
    row['expense'] += cost
    row['level'] += 1
    return cost

