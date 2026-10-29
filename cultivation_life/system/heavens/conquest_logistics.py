"""Finite original field cash and stock, carried home before any refund."""
from ..war import logistics, requirements, supply
from ..economy import depot
from ..economy.ledger import account, balance, transfer_value
from ..economy.state import ensure_regional_market
from ..economy.basket_trade import sale
from . import outpost_runtime as base
from .outpost_definitions import ENDPOINTS
from .conquest_definitions import WAR_BUDGET


def initialize(deps, game, row, war):
    war['logistics'] = dict(version=1, round=0, intel={}, actions={}, sides={})
    for side in ('attacker', 'defender'):
        account(game, logistics.wallet(war, side))
        war['logistics']['sides'][side] = dict(world=war['world'], location=war['location_id'], distance=0,
            mobilized=0, spent=0, purchased=0, destroyed=0, transport_loss=0, coverage=1., contributions={}, items={}, consumed_items={}, cross_realm=False,
            stationing_year=game.player.age, stationing_credit=0., stationing_paid=0, stationing_shortfall=0, mobilization_paid=0)
        if side == 'attacker':
            amount, origin, owner = WAR_BUDGET, base.wallet(row), row['owner_id']
        else:
            entity = deps.outpost_owner(game, war['defender_id'])
            from ..economy.organizations import register
            register(game, depot.owner_kind(game, entity), entity.id, entity.world)
            origin, owner = depot.treasury(game, entity), entity.id
            amount = min(WAR_BUDGET, balance(game, origin))
        transfer_value(game, origin, logistics.wallet(war, side), amount, '原地组织实付有限出征军费，未到场不得参战')
        state = war['logistics']['sides'][side]
        state.update(mobilized=amount, contributions={owner: amount})
    ensure_regional_market(game, deps.outpost_maps(), war['world'], war['location_id'])


def pending(war):
    return any(any(n for n in side['items'].values()) for side in war.get('logistics', {}).get('sides', {}).values())


def refund(deps, game, row, war):
    """Only actual local return makes original military assets accessible."""
    for side in ('attacker', 'defender'):
        journeys = war['journeys'][side]
        if any(j['phase'] not in {'home', 'lost'} for j in journeys):
            continue
        state = war['logistics']['sides'][side]
        source = logistics.wallet(war, side)
        entity = deps.outpost_owner(game, war[f'{side}_id'])
        alive = any(j['phase'] == 'home' for j in journeys)
        location = ENDPOINTS[row['destination']] if side == 'attacker' else war['location_id']
        destination = base.wallet(row) if side == 'attacker' else depot.treasury(game, entity) if entity and not entity.extinct else f'background:{war["world"]}'
        if not alive:
            state['items'] = {}
            destination = f'background:{war["world"]}'
        else:
            # Original goods are sold to the real local dealer, never turned
            # into a newly minted cash refund or copied to the home world.
            ensure_regional_market(game, deps.outpost_maps(), war['world'], location)
            market = game.economy_v2['markets'][f'{war["world"]}:{location}']
            for item, quantity in list(state['items'].items()):
                if quantity and item in market['commodities']:
                    count, _ = sale(game, market, source, item, quantity, '原军需实际归返后当地交割')
                    state['items'][item] -= count
        state['location'] = location
        transfer_value(game, source, destination, balance(game, source), '原军队实际归返，军费与真实售货款结清')
    war['logistics']['refunded'] = all(j['phase'] in {'home', 'lost'} for rows in war['journeys'].values() for j in rows)
