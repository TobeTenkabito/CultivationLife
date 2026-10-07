"""Peace transfers title to existing local assets, never their location or stock."""
from .organizations import register
from .market_governance import assign
from .state import ensure_regional_market
from .enterprise_state import owner_allowed, log


def entity(game, identity):
    return game.family if game.family and game.family.id == identity else game.sects.get(identity)


def eligible(game, war, winner, loser):
    rows = [entity(game, identity) for identity in (winner, loser)]
    return war['kind'] == 'sect' and all(row and not row.extinct and row.kind != 'institution'
        and row.world == war['world'] for row in rows)


def transfer(game, maps, war, winner, loser, *, strict=False):
    if not eligible(game, war, winner, loser):
        if strict:
            raise ValueError('产业和市税接管仅适用于同界存续的宗门或家族')
        return '本和约没有可办理的同界经济产权'
    receipts = war.setdefault('economic_transfers', [])
    if any(row['loser'] == loser for row in receipts):
        return '该战败方的经济产权已完成交接'
    victor, defeated = entity(game, winner), entity(game, loser)
    kind = 'family' if victor is game.family else 'sect'
    old_kind = 'family' if defeated is game.family else 'sect'
    register(game, kind, winner, war['world'])
    receipt = dict(year=game.player.age, winner=winner, loser=loser, estates=[], markets=[], fleets=[], released=[])
    for row in game.economy_v2.get('estates', {}).values():
        if (row['world'], row['owner_kind'], row['owner_id']) == (war['world'], old_kind, loser):
            row.update(owner_kind=kind, owner_id=winner, enabled=False, revision=row['revision'] + 1)
            log(row, game.player.age, '战后产权交接；保留原仓储、在制品及矿藏，暂停后续生产')
            receipt['estates'].append(row['id'])
    from ..faction_geography import faction_site
    site = faction_site(defeated)['id']
    ensure_regional_market(game, maps, war['world'], site)
    for market in game.economy_v2['markets'].values():
        claim = market.get('control')
        if market['world'] == war['world'] and ((claim and (claim['kind'], claim['id']) == (old_kind, loser))
                or (not claim and market['location'] == site)):
            assign(game, market, kind, winner, war['id'])
            receipt['markets'].append(market['id'])
    fleets = game.economy_v2.get('transport', {}).get('worlds', {}).get(war['world'], {}).get('fleets', {})
    owned = sum(row['owner_kind'] == kind and row['owner_id'] == winner and row['status'] != 'retired' for row in fleets.values())
    slots = max(0, (1 if kind == 'family' else 2) - owned)
    for row in sorted(fleets.values(), key=lambda row: row['id']):
        if (row['owner_kind'], row['owner_id']) != (old_kind, loser) or row['status'] == 'retired':
            continue
        row.update(trade_order={'mode': 'hold'}, pledged=False, alliance_id='')
        if slots:
            row.update(owner_kind=kind, owner_id=winner, player_controlled=owner_allowed(game, kind, winner, war['world']))
            receipt['fleets'].append(row['id'])
            slots -= 1
        else:
            row.update(owner_kind='independent', owner_id=row['id'], player_controlled=False)
            receipt['released'].append(row['id'])
    receipts.append(receipt)
    return f"接管产业 {len(receipt['estates'])} 处、市税 {len(receipt['markets'])} 处、商队 {len(receipt['fleets'])} 支；超额商队 {len(receipt['released'])} 支转为无势力"
