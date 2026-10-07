"""Market fee rights: local ownership, earned distributions and reinvestment."""
from .ledger import account, balance, transfer_value

POLICIES = {'reinvest': ('休养生息', 0), 'balanced': ('均衡经营', 25), 'extract': ('提高上缴', 75)}


def recipient(claim):
    return f'organization:{claim["kind"]}:{claim["id"]}'


def active(game, market):
    claim = market.get('control')
    if not claim:
        return False
    owner = game.family if claim['kind'] == 'family' else game.sects.get(claim['id'])
    return bool(owner and owner.id == claim['id'] and not owner.extinct and owner.kind != 'institution'
                and owner.world == market['world'])


def settle_claim(game, market):
    claim = market.get('control')
    if not claim:
        return
    source = f'operator:{market["id"]}'
    income = account(game, source)['income']
    if not active(game, market):
        # A departed/extinct faction cannot remit this world's money remotely.
        claim.update(income_cursor=income, last_year=game.player.age)
        return
    earned = max(0, income - claim['income_cursor'])
    due = earned * POLICIES[claim['policy']][1] // 100
    paid = min(due, balance(game, source))
    transfer_value(game, source, recipient(claim), paid, '当地市场实收手续费上缴控制方')
    claim['income_cursor'] = income
    claim['received'] += paid
    claim['last_year'] = game.player.age
    organization = game.economy_v2.get('organizations', {}).get(recipient(claim))
    if organization:
        organization['income'] += paid


def advance_governance(game):
    for market in game.economy_v2['markets'].values():
        claim = market.get('control')
        if claim and claim['last_year'] < game.player.age:
            settle_claim(game, market)


def assign(game, market, kind, identity, war_id):
    settle_claim(game, market)
    market['control'] = dict(kind=kind, id=identity, since=game.player.age, war_id=war_id,
        policy='balanced', received=0, income_cursor=account(game, f'operator:{market["id"]}')['income'], last_year=game.player.age)
    market['revision'] += 1


def command(game, maps, payload):
    from .state import local_market
    from .enterprise_state import owner_allowed
    market = local_market(game)
    if not market or type(payload.get('revision')) is not int or payload.get('market_id') != market['id'] or payload.get('revision') != market['revision']:
        raise ValueError('本地市场状态已变化，请刷新后办理')
    claim = market.get('control')
    if payload['action'] == 'market_relief':
        amount = payload.get('amount')
        if type(amount) is not int or not 1 <= amount <= 10**9:
            raise ValueError('投入须为 1 至十亿灵石的整数')
        transfer_value(game, 'player', f'operator:{market["id"]}', amount, '出资本地竞争扩产基金')
        if claim:
            claim['income_cursor'] += amount  # Donations are not taxable fee revenue.
    elif payload['action'] == 'market_policy':
        if not claim or not owner_allowed(game, claim['kind'], claim['id'], market['world']):
            raise ValueError('只有本地市场控制方的执掌者可以决定经营方针')
        policy = payload.get('policy')
        if policy not in POLICIES:
            raise ValueError('未知市场方针')
        settle_claim(game, market)  # Old earnings keep the old policy.
        claim['policy'] = policy
    else:
        raise ValueError('未知市场治理操作')
    market['revision'] += 1
