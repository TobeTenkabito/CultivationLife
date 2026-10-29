"""One finite fee distribution for native organizations and addressed branches."""
from ...regional_context import current
from ..economy.ledger import balance, transfer_value
from ..economy.organization_accounts import key
from . import anchors
from .rules import enabled, POLICIES, permits
from .state import snapshot


def adopt(game, market):
    cursors = game.economy_v2.setdefault('organization_sites', {}).setdefault('frontier_fee_cursors', {})
    cursors[market['id']] = dict(fees=market.get('fees', 0), mode=enabled())


def distribute(game, maps=None):
    native = enabled()
    branches = anchors.branches(game)
    if not native and not branches:
        return
    territory = game.intrigue_state.get('territory', {})
    old_cursors = territory.setdefault('fee_cursors', {}) if native else {}
    shared = game.economy_v2.get('organization_sites', {}).get('frontier_fee_cursors', {})
    for market in game.economy_v2.get('markets', {}).values():
        world = market['world']
        if not current(game, world):
            continue
        addressed = any(r['destination'] == world for r in branches)
        actual = market.get('fees', 0)
        if addressed:
            receipt = shared.get(market['id'])
            if not receipt or receipt['mode'] != native:
                adopt(game, market)
                shared = game.economy_v2['organization_sites']['frontier_fee_cursors']
                continue
            previous = receipt['fees']
            receipt['fees'] = actual
            if native:
                old_cursors[market['id']] = actual
        elif native:
            previous = old_cursors.get(market['id'], actual)
            old_cursors[market['id']] = actual
        else:
            continue
        book = snapshot(game, maps, world) if addressed and maps else territory.get('holdings', {}).get(world, {})
        rows = book.get(market['location'], {})
        weights = {}
        for identity, row in rows.items():
            entity = anchors.organization(game, identity)
            foreign = anchors.branch(game, world, identity)
            if not entity or entity.extinct:
                continue
            if not addressed and not foreign and key('sect', identity) not in game.economy_v2.get('organizations', {}):
                continue
            policy = POLICIES.get(row.get('policy')) if permits(row.get('policy'), row['value']) else None
            weights[identity] = row['value'] * (policy['yield_factor'] if policy else 1)
        total = sum(weights.values())
        if not total:
            continue
        operator = f'operator:{market["id"]}'
        pool = min(int(max(0, actual - previous) * .2), balance(game, operator))
        for identity, weight in weights.items():
            paid = int(pool * weight / total)
            foreign = anchors.branch(game, world, identity)
            if foreign:
                if not anchors.operational(game, foreign):
                    continue
                destination = f'heavens-{foreign["id"]}:local'
                transfer_value(game, operator, destination, paid, '当地原手续费按实际影响份额交付异界分驻地')
                foreign['development']['income'] += paid
            elif native:
                entity = anchors.organization(game, identity)
                if entity.world != world or key('sect', identity) not in game.economy_v2.get('organizations', {}):
                    continue
                transfer_value(game, operator, key('sect', identity), paid, '当地采办与商路经营收益按相对影响力分配')
                row = game.economy_v2['organizations'][key('sect', identity)]
                row['income'] += paid
                row['territory_income'] = row.get('territory_income', 0) + paid
                if row.get('history') and row['history'][-1][0] == game.player.age:
                    row['history'][-1][1] += paid
