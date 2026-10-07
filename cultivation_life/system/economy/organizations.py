"""Organization finance: existing treasuries, real local production, yearly welfare.

Politics may use action units; money uses the shared elapsed-year clock. Adoption
does not pay historical income, create NPCs, or touch the simulation RNG.
"""
import hashlib

from ...content_registry import ITEM_CATALOG, WORLD_SYSTEMS
from .ledger import account, balance, transfer_value
from .state import ensure_state, ensure_regional_market, reprice
from .local_market import quote


def key(kind, identity):
    return f'organization:{kind}:{identity}' if kind != 'yaochi' else 'institution:celestial:yaochi'


def faction_record(game, kind, identity):
    # This is the old authoritative treasury, also when the politics DLC is off.
    record = game.intrigue_state.setdefault('factions', {}).setdefault(f'{kind}:{identity}', dict(
        kind=kind, id=identity, controller_id=None, positions={}, guests=[], prison=[],
        member_contribution={}, unrest=0., fear=0., resources=0, policy='balance'))
    record.setdefault('resources', 0)
    return record


def register(game, kind, identity, world):
    ensure_state(game)
    if world not in game.economy_v2['worlds']:
        raise ValueError('组织财政必须属于已知主界面')
    address = key(kind, identity)
    rows = game.economy_v2.setdefault('organizations', {})
    if kind in {'sect', 'family'}:
        faction_record(game, kind, identity)
    if address not in rows:
        if kind == 'yaochi':
            account(game, address)
        rows[address] = dict(kind=kind, identity=identity, world=world,
            last_year=max(game.player.age, game.economy_v2['last_year']),
            income=0, expense=0, shortfall=0, benefit_paid=0, benefit_due=0,
            produced=0, commodity=None, history=[])
        # A finite transfer funds institutions without a pre-existing treasury.
        if kind == 'yaochi':
            pay(game, f'background:{world}', address, 2000000, '瑶池设立采购周转金')
    elif rows[address]['world'] != world:
        # The existing faction migration owns its treasury. No goods or accrued
        # production work are transported by this fiscal address reconciliation.
        rows[address].update(world=world, production_credit=0,
            last_year=max(game.player.age, game.economy_v2['last_year']))
    return rows[address]


def ensure_organizations(game):
    ensure_state(game)
    adopted = 'organizations' not in game.economy_v2
    before = len(game.economy_v2.setdefault('organizations', {}))
    for entity in [*game.sects.values(), *([game.family] if game.family else [])]:
        if entity.extinct or entity.kind == 'institution' or entity.world not in game.economy_v2['worlds']:
            continue
        kind = 'family' if entity is game.family else 'sect'
        if (entity is not game.family and entity.world != game.player.world
                and key(kind, entity.id) not in game.economy_v2.get('organizations', {})):
            continue  # Adopt a region on first visit; previously visited regions keep running.
        register(game, kind, entity.id, entity.world)
    if game.heavenly_court:
        register(game, 'court', 'heavenly', 'celestial')
    for world in game.upper_institutions:
        if world in WORLD_SYSTEMS['upper_institutions']['worlds']:
            register(game, 'upper', world, world)
    if game.player.world == 'celestial':
        register(game, 'yaochi', 'yaochi', 'celestial')
    return adopted or before != len(game.economy_v2['organizations'])


def pay(game, source, destination, amount, reason):
    paid = min(max(0, int(amount)), balance(game, source))
    transfer_value(game, source, destination, paid, reason)
    return paid


def procure(game, source, world, amount, reason, *, partial=False):
    """Pay aggregate craftsmen for non-standard goods/services before granting."""
    ensure_state(game)
    amount = max(0, int(amount))
    if not partial and balance(game, source) < amount:
        raise ValueError('组织府库不足，无法支付本次资材或修炼供养')
    return pay(game, source, f'background:{world}', amount, reason)


def _entity(game, row):
    if row['kind'] == 'family':
        return game.family if game.family and game.family.id == row['identity'] else None
    return game.sects.get(row['identity'])


def produce(game, maps, entity, row, *, years=1, extra=False):
    """Produce against local dealer orders; unsold output is never fabricated.

    No interregional supply is credited. Each sold unit is added once to the
    producing site's stock; all other regions still require merchant caravans.
    """
    from ..faction_geography import faction_site
    from ...npc_custody import is_free
    world, location = entity.world, faction_site(entity)['id']
    ensure_regional_market(game, maps, world, location)
    market = game.economy_v2['markets'][f'{world}:{location}']
    native = {k: v for k, v in market['commodities'].items() if not v.get('imported')}
    minimum_tier = min((v['tier'] for v in native.values()), default=0)
    goods = sorted(k for k, v in native.items() if v['tier'] == minimum_tier)
    if not goods:
        return 0
    index = int.from_bytes(hashlib.sha256(entity.id.encode()).digest()[:4], 'big') % len(goods)
    item = goods[index]
    product = market['commodities'][item]
    members = [n for n in entity.npcs if is_free(n) and n.world == world]
    capacity = sum(max(5, n.realm_index ** 4 * 10) for n in members)
    if extra:
        capacity = max(20, capacity // 4) if members else 0
    capacity *= min(1000, game.economy_v2['worlds'][world]['scale'])
    capacity *= (1 + row.get('industry_level', 0) * .25) * row.get('industry_utilization', 1.)
    credit = row.get('production_credit', 0) if row.get('commodity') == item else 0
    # Expensive upper-world goods may require several years of work. Keep a
    # bounded work-in-progress value, never manufacture unsold inventory.
    credit = min(credit + capacity * years, product['reference'] * min(1000000, product['target'] * 2))
    row['production_credit'] = credit
    quantity = min(1000000, int(credit / max(1, product['reference'])),
                   max(0, int(product['target'] * 2 - product['stock'])))
    dealer = f'market:{market["id"]}'
    low, high = 0, quantity
    while low < high:
        middle = (low + high + 1) // 2
        if quote(product, 'sell', middle)['gross'] <= balance(game, dealer):
            low = middle
        else:
            high = middle - 1
    row['commodity'] = item
    if not low:
        return 0
    sale = quote(product, 'sell', low)
    transfer_value(game, dealer, key(row['kind'], entity.id), sale['total'], '组织驻地产出销售')
    transfer_value(game, dealer, f'operator:{market["id"]}', sale['fee'], '组织产出交易手续费')
    product['stock'] += low
    product['production'] += low
    product['volume'] += low
    market['turnover'] += sale['gross']
    market['fees'] += sale['fee']
    reprice(game, market, product)
    row['produced'] += low
    from .industry import supplier_delivery
    supplier_delivery(market, key(row['kind'], entity.id), low)
    row['production_credit'] = max(0, credit - low * product['reference'])
    return sale['total']


def settle_faction(game, maps, row, years):
    entity = _entity(game, row)
    if not entity or entity.extinct:
        return
    # A relocated faction retains its one treasury. Output uses its real site.
    if row['world'] != entity.world:
        row['production_credit'] = 0
        row['world'] = entity.world
    source, world = key(row['kind'], entity.id), entity.world
    from .industry import settle_industry
    settle_industry(game, maps, entity, row, years)
    row['income'] += produce(game, maps, entity, row, years=years)
    freight = f'transport:{world}:{entity.id}'
    if freight in game.economy_v2['accounts']:
        row['income'] += pay(game, freight, source, balance(game, freight), '传送阵货运收入归属府库')
    from ...npc_custody import is_free
    members = [n for n in entity.npcs if is_free(n) and n.world == world]
    due = sum(25 * WORLD_SYSTEMS['world_profiles'][world]['tier'] + n.realm_index ** 2 * 12 for n in members) * years
    if row['kind'] == 'family':
        due += sum(c.get('alive', True) and c.get('world') == world and c.get('age', 0) < 8 for c in game.player.offspring) * 15 * years
        due += int(game.family_state.get('debt', 0))
    paid = procure(game, source, world, due, '组织日常养护与成员供养', partial=True)
    row['expense'] += paid
    row['shortfall'] = due - paid
    if row['kind'] == 'family':
        game.family_state['debt'] = due - paid


def settle_institution(game, row, years):
    kind, world = row['kind'], row['world']
    source = key(kind, row['identity'])
    multiplier, wages = 1., 0
    state = None
    if kind == 'upper':
        state = game.upper_institutions[row['identity']]
        cfg = WORLD_SYSTEMS['upper_institutions']
        policy = next(p for p in cfg['worlds'][world]['policies'] if p['id'] == state['policy'])
        annual_income = cfg['unit_income'] / 100
        if world == 'asura' and state.get('court'):
            from ..asura_court_finance import benefits
            benefit = benefits(game, state)
            multiplier = benefit['revenue'] * policy.get('revenue', 1)
            wages = int(benefit['wages'] * years / 100)
    elif kind == 'court':
        state = game.heavenly_court
        annual_income = WORLD_SYSTEMS['heavenly_court']['base_treasury_income']
        for decree in state.get('active_decrees', []):
            multiplier *= decree.get('income_multiplier', 1.)
        multiplier *= .95 if state.get('laws', {}).get('wide_domain') else 1
        multiplier *= 1.05 if state.get('laws', {}).get('traveling_palace') else 1
    else:
        annual_income = 20000
    scale = game.economy_v2['worlds'][world]['scale']
    row['income'] = pay(game, f'background:{world}', source,
        int(annual_income * multiplier * scale * years + 1e-7), '机构税赋与经营收入（背景部门实付）')
    row['expense'] = procure(game, source, world, wages, '机构官员供养', partial=True)
    row['shortfall'] = wages - row['expense']
    p = game.player
    if not p.alive or p.world != world or p.realm_index < 9:
        return
    if kind == 'upper' and state['joined']:
        rank = int(state['seat_active']) if world == 'nether' else state['rank']
        amount = int((100 + rank * 100) * policy['income'] * years)
    elif kind == 'court':
        amount = int(WORLD_SYSTEMS['heavenly_court']['grade_stipends'][str(state['player_grade'])] * years / 100)
    else:
        return
    paid = pay(game, source, 'player', amount, '机构年度俸禄')
    row['expense'] += paid
    row['benefit_due'], row['benefit_paid'] = amount, paid
    if kind == 'court':
        state['stipend_total'] = state.get('stipend_total', 0) + paid


def advance_organizations(game, maps):
    ensure_organizations(game)
    for row in game.economy_v2['organizations'].values():
        years = game.player.age - row['last_year']
        if years <= 0:
            continue
        row.update(income=0, expense=0, shortfall=0, produced=0, benefit_due=0, benefit_paid=0)
        if row['kind'] in {'sect', 'family'}:
            settle_faction(game, maps, row, years)
        else:
            settle_institution(game, row, years)
        row['last_year'] = game.player.age
        row['history'].append([game.player.age, row['income'], row['expense']])
        del row['history'][:-12]


def public_finance(game, kind, identity):
    """Read-only and same-world; no adoption, settlement, or remote live data."""
    address = key(kind, identity)
    row = game.economy_v2.get('organizations', {}).get(address)
    if not row or row['world'] != game.player.world:
        return None
    return {k: row[k] for k in ('last_year', 'income', 'expense', 'shortfall', 'benefit_paid', 'benefit_due', 'produced')} | dict(
        balance=balance(game, address), product=ITEM_CATALOG[row['commodity']].name if row['commodity'] else None,
        industry_level=row.get('industry_level', 0), war_funding=row.get('war_funding', 1.))


def welfare(game, entity):
    row = register(game, 'sect', entity.id, entity.world)
    if row.get('welfare_year', -1) >= game.player.age:
        return 0.
    row['welfare_year'] = game.player.age
    due = max(25, WORLD_SYSTEMS['world_profiles'][entity.world]['tier'] * 100)
    paid = procure(game, key('sect', entity.id), entity.world, due, '宗门年度修炼福利采购', partial=True)
    row['benefit_due'], row['benefit_paid'] = due, paid
    row['expense'] += paid
    return paid / due
