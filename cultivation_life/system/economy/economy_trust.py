"""Opt-in resident management; bounded investment from actual retained profit."""
from .enterprise_state import owner_allowed, payer, estates, log
from .ledger import balance, transfer_value


CONFIG = dict(recipe=None, enabled=False, auto_buy=False, auto_sell=False, batches=1,
              buy_limit=10**12, sell_limit=0, sale_quota=1000000, expense_limit=100000, entrusted=False)


def release(row):
    previous = row.pop('trust_config', None)
    row.pop('trust_profit_base', None)
    if previous is not None:
        row.update(CONFIG | previous)
        row['revision'] += 1


def release_all(game):
    for row in estates(game).values():
        release(row)


def prepare(game, row):
    if row.get('building_status')=='destroyed':return False
    active = (game.settings.get('economy_trust', False) and game.player.alive
              and owner_allowed(game, row['owner_kind'], row['owner_id'], row['world']))
    if not active:
        release(row)
        return False
    if 'trust_config' not in row:
        row['trust_config'] = {k: row.get(k, default) for k, default in CONFIG.items()}
        row['trust_profit_base'] = row['income'] - row['expense']
    return True


def grow(game, maps, row, market):
    """One decision per five world years, no year replay or search over maps."""
    if row.get('building_status')=='destroyed':return
    if not game.settings.get('economy_trust') or not game.player.alive or not owner_allowed(game, row['owner_kind'], row['owner_id'], row['world']):
        return
    if row['arrears'] or row['job'] or row['income'] <= row['expense']:
        return
    if game.player.age < game.economy_v2.get('trust_growth_year', -5) + 5:
        return
    if row['kind'] in {'mine', 'hunt'} and not row['reserve']:
        return
    from .enterprise_costs import operating_reserve
    available = max(0, balance(game, payer(row)) - operating_reserve(game, row, market))
    retained = row['income'] - row['expense'] - row.get('trust_profit_base', 0)
    budget = min(available // 3, retained // 3)
    if budget < 1000:
        return
    from .industry import participating_wars
    if row['owner_kind'] in {'sect', 'family'}:
        finance = game.economy_v2['organizations'].get(payer(row), {})
        if finance.get('shortfall') or participating_wars(game, row['owner_id'], row['world']):
            return
    game.economy_v2['trust_growth_year'] = game.player.age
    from .enterprise_acquisition import price, upgrade, acquire
    from .estate_management import plan
    if row['level'] < 5:
        cost = price(game, maps, row, row['level'] + 1)
        if cost <= budget:
            projected = dict(row, level=row['level']+1)
            plan(game, maps, projected, funds=max(0,balance(game,payer(row))-cost), optimize_batches=True)
            if projected.get('auto_buy') and balance(game,payer(row))-cost >= operating_reserve(game,projected,market):
                upgrade(game, maps, row, expected_cost=cost)
                log(row, game.player.age, '经济托管以已实现盈余扩建；保留养护与经营资金')
                return
    for kind in ('farm', 'mine', 'hunt', 'alchemy', 'forge'):
        identity = f'{row["world"]}:{row["location"]}:{kind}'
        existing = estates(game).get(identity)
        if existing and existing.get('building_status')=='destroyed':continue
        if existing and existing['owner_kind'] != 'background':
            continue
        offer = dict(world=row['world'], location=row['location'], kind=kind, level=existing['level'] if existing else 1,
                     reserve=existing['reserve'] if existing else 5000,
                     owner_kind=row['owner_kind'], owner_id=row['owner_id'], recipe=None,
                     stock={}, job=None, enabled=False)
        cost = price(game, maps, existing or offer)
        capital = max(1000, cost // 2) if row['owner_kind'] == 'player' else 0
        if cost + capital > budget:
            continue
        plan(game, maps, offer, funds=capital or budget, optimize_batches=True)
        if not offer.get('auto_buy'):
            continue
        source = payer(row)
        bought = acquire(game, maps, row['world'], row['location'], kind,
                         row['owner_kind'], row['owner_id'], source, game.player.realm_index)
        if capital:
            transfer_value(game, source, payer(bought), capital, '经济托管拨付新产业周转金')
        # Capital investment is distinct from sales; it reduces retained profit
        # available for the next decision instead of creating another balance.
        # Acquisition already books organizational capital expense once.
        # This source estate's net cash flow still bounds its next investment.
        row['expense'] += cost + capital
        log(row, game.player.age, '经济托管购入同地产权，真实扣款并拨付周转金')
        return
