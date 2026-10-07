"""Observed commodity concentration and paid local competitive supply."""
import math
from ...content_registry import MARKET_SETTINGS
from .ledger import account, balance, transfer_value


def owner_key(row):
    kind, identity = row['owner_kind'], row['owner_id']
    if kind == 'player':
        return 'player'
    if kind == 'alliance':
        return f'alliance:{row["world"]}:{identity}'
    return f'organization:{kind}:{identity}'


def normalize(game, party):
    if party.startswith('estate:'):
        row = game.economy_v2.get('estates', {}).get(party[7:])
        return owner_key(row) if row else 'background'
    if party.startswith('caravan:'):
        identity = party[8:]
        row = game.economy_v2.get('transport', {}).get('worlds', {}).get(identity.split(':')[0], {}).get('fleets', {}).get(identity)
        if not row:
            return 'background'
        if row['owner_kind'] == 'independent':
            return 'player' if row.get('player_controlled') else 'background'
        return owner_key(row)
    return party


def record_trade(game, market, item, party, side, quantity):
    if quantity <= 0:
        return
    party = normalize(game, party)
    row = market.setdefault('competition', {}).setdefault(item, dict(buyers={}, sellers={}, pressure=0.,
        dominant=None, invested=0, added=0, history=[]))
    rows = row['buyers' if side == 'buy' else 'sellers']
    rows[party] = min(10**9, rows.get(party, 0.) + quantity)
    # Aggregate the smallest observations, retaining at most sixteen actors.
    while len(rows) > 16:
        key = min((k for k in rows if k != 'background'), key=lambda k: rows[k])
        rows['background'] = min(10**9, rows.get('background', 0.) + rows.pop(key))


def holdings(game, market, item):
    result = {}
    for estate in game.economy_v2.get('estates', {}).values():
        if (estate['world'], estate['location']) != (market['world'], market['location']) or estate['owner_kind'] == 'background':
            continue
        quantity = estate['stock'].get(item, 0)
        if quantity:
            key = owner_key(estate)
            result[key] = result.get(key, 0) + quantity
    return result


def indicators(game, market, item, data):
    product = market['commodities'][item]
    stocks = holdings(game, market, item)
    background = product['target'] * MARKET_SETTINGS['economy_v2']['annual_consumption'] * 5
    supply = sum(data['sellers'].values()) + (0 if product.get('imported') else background)
    demand = sum(data['buyers'].values()) + background
    total_stock = sum(stocks.values()) + product['stock']
    actors = (set(stocks) | set(data['buyers']) | set(data['sellers'])) - {'background'}
    rows = []
    for actor in actors:
        sufficient = max(stocks.get(actor, 0), data['buyers'].get(actor, 0), data['sellers'].get(actor, 0)) >= product['target'] * .25
        shares = dict(supply=data['sellers'].get(actor, 0) / max(1, supply),
                      purchase=data['buyers'].get(actor, 0) / max(1, demand),
                      storage=stocks.get(actor, 0) / max(1, total_stock))
        rows.append(dict(owner=actor, **shares, power=max(shares.values()) if sufficient else 0.))
    return sorted(rows, key=lambda r: (-r['power'], r['owner']))


def settle(game, market, years):
    """One bounded response per observed interval, never a remote goods copy."""
    for estate in game.economy_v2.get('estates', {}).values():
        if (estate['world'], estate['location']) == (market['world'], market['location']):
            for item in estate['stock']:
                if item in market['commodities'] and item not in market.get('competition', {}):
                    record_trade(game, market, item, 'background', 'sell', .01)
    extra = {}
    for item, row in market.get('competition', {}).items():
        product = market['commodities'][item]
        actors = indicators(game, market, item, row)
        leader = actors[0] if actors else None
        tight = product['stock'] < product['target'] * .6
        dominant = leader and leader['power'] >= .6
        row['dominant'] = leader['owner'] if dominant else None
        row['pressure'] = min(100., row['pressure'] + 16 * min(years, 5)) if dominant and tight else max(0., row['pressure'] - 12 * years)
        if row['pressure'] >= 32 and tight and not product.get('imported'):
            # Public workshops respond with paid local labor/material services.
            unit_cost = max(1, math.ceil(product['reference'] * .45))
            budget = f'operator:{market["id"]}'
            quantity = min(1000000, math.ceil(product['target'] * .35 * min(years, 5)), balance(game, budget) // unit_cost)
            if quantity:
                receiver = f'competition:{market["id"]}'
                account(game, receiver)
                transfer_value(game, budget, receiver, quantity * unit_cost, '本地竞争扩产支付工料')
                extra[item] = quantity
                row['invested'] += quantity * unit_cost
                row['added'] += quantity
                row['history'].append([game.player.age, f'公营作坊扩产 {quantity} 件，实付 {quantity * unit_cost} 灵石'])
                del row['history'][:-8]
        for side in ('buyers', 'sellers'):
            row[side] = {k:v * math.exp(-.2 * years) for k,v in row[side].items() if v * math.exp(-.2 * years) >= .01}
    return extra


def rival_targets(game, world):
    candidates = [m for m in game.economy_v2['markets'].values() if m['world'] == world
                  and any(r['pressure'] >= 32 for r in m.get('competition', {}).values())]
    return [m['location'] for m in sorted(candidates, key=lambda m: -max(r['pressure'] for r in m['competition'].values()))[:3]]
