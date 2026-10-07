"""War reparations use existing faction cash and purchased goods."""
from .ledger import account, balance, transfer_value
from .organizations import register
from .state import ensure_state, ensure_regional_market, reprice
from .local_market import quote
from ...rules import add_item


def war_account(game, kind, identity, world):
    ensure_state(game)
    entity = game.family if game.family and game.family.id == identity else game.sects.get(identity)
    if kind == 'sect' and entity:
        owner = 'family' if entity is game.family else 'sect'
        register(game, owner, identity, entity.world)
        return f'organization:{owner}:{identity}'
    key = f'war:{world}:{identity}'
    account(game, key)
    return key


def reparations(game, war, winner, loser, amount):
    source = war_account(game, war['kind'], loser, war['world'])
    destination = war_account(game, war['kind'], winner, war['world'])
    paid = min(amount, balance(game, source))
    transfer_value(game, source, destination, paid, '战败组织支付战争赔款')
    return paid


def supplies(game, maps, war, loser, receive):
    source = war_account(game, war['kind'], loser, war['world'])
    if not receive or game.player.world != war['world']:
        return []
    from ..faction_geography import war_site
    location = war_site(maps, war)['id']
    ensure_regional_market(game, maps, war['world'], location)
    market = game.economy_v2['markets'][f'{war["world"]}:{location}']
    supplied = []
    from ...content_registry import ITEM_CATALOG
    for item, row in market['commodities'].items():
        if row['stock'] < 1:
            continue
        bill = quote(row, 'buy', 1)
        if balance(game, source) < bill['total']:
            continue
        transfer_value(game, source, f'market:{market["id"]}', bill['total'], '战败方采购交付战争资材')
        transfer_value(game, f'market:{market["id"]}', f'operator:{market["id"]}', bill['fee'], '和约资材采购手续费')
        row['stock'] -= 1
        reprice(game, market, row)
        add_item(game.player, item)
        supplied.append(ITEM_CATALOG[item].name)
        if len(supplied) == 3:
            break
    return supplied
