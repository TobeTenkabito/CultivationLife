"""Paid industrial capacity, physical war supply, and observable supplier shares."""
from .ledger import balance, transfer_value
from .local_market import quote
from .state import ensure_regional_market, reprice


def participating_wars(game, identity, world):
    return [w for w in game.wars if w.get('kind') == 'sect' and w.get('world') == world
            and w.get('status') in {'active', 'peace_ready'}
            and identity in {w.get('attacker_id'), w.get('defender_id'),
                *(r['id'] for side in ('attacker', 'defender') for r in w.get('coalitions', {}).get(side, []))}]


def supplier_delivery(market, owner, quantity, *, game=None, item=None):
    suppliers = market.setdefault('suppliers', {})
    suppliers[owner] = suppliers.get(owner, 0.) + quantity
    if game is not None and item is not None:
        from .market_power import record_trade
        record_trade(game, market, item, owner, 'sell', quantity)


def settle_industry(game, maps, entity, row, years):
    from ..faction_geography import faction_site
    world, site = entity.world, faction_site(entity)['id']
    ensure_regional_market(game, maps, world, site)
    market = game.economy_v2['markets'][f'{world}:{site}']
    source = f'organization:{row["kind"]}:{entity.id}'
    wars = participating_wars(game, entity.id, world)
    level = row.get('industry_level', 0)
    due = round(100 * (level + 1) * years) if level else 0
    paid = min(due, balance(game, source))
    transfer_value(game, source, f'background:{world}', paid, '组织产业原料与设备养护')
    row['expense'] += paid
    row['industry_utilization'] = paid / due if due else 1.
    row['war_funding'] = 1.
    if not wars:
        return
    # Battlefield logistics now owns all military procurement. Do not charge
    # these organizations a second time through the old annual supply sink.
    # The production histogram excludes deployed and research-occupied people;
    # don't charge a second blanket utilization penalty for the same workers.
