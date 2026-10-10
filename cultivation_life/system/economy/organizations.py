"""Organization finance: existing treasuries, real local production, yearly welfare.

Politics may use action units; money uses the shared elapsed-year clock. Adoption
does not pay historical income, create NPCs, or touch the simulation RNG.
"""
import hashlib

from ...content_registry import ITEM_CATALOG, WORLD_SYSTEMS
from ...economy_content import BASE_PRICES
from .ledger import account, balance, transfer_value
from .state import ensure_state, ensure_regional_market, reprice, commodity_catalog
from .local_market import quote
from .organization_accounts import key, faction_record, register, pay, procure


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


def _entity(game, row):
    if row['kind'] == 'family':
        return game.family if game.family and game.family.id == row['identity'] else None
    return game.sects.get(row['identity'])


def produce(game, maps, entity, row, *, years=1, extra=False):
    from .organization_production import produce as produce_portfolio
    return produce_portfolio(game, maps, entity, row, years=years, extra=extra)


def settle_faction(game, maps, row, years):
    entity = _entity(game, row)
    if not entity or entity.extinct:
        return
    # A relocated faction retains its one treasury. Output uses its real site.
    if row['world'] != entity.world:
        row['production_credit'] = 0
        row['demand_credit'] = {}
        row['cultivation_support']={};row['maintenance_support']={};row['breakthrough_support']={};row['longevity_support']={};row['supply_budget_credit']=0
        row['world'] = entity.world
    source, world = key(row['kind'], entity.id), entity.world
    from .industry import settle_industry
    settle_industry(game, maps, entity, row, years)
    row['income'] += produce(game, maps, entity, row, years=years)
    freight = f'transport:{world}:{entity.id}'
    if freight in game.economy_v2['accounts']:
        row['income'] += pay(game, freight, source, balance(game, freight), '传送阵货运收入归属府库')
    due = row.get('expected_upkeep', 0) * years
    carried_debt = 0
    child_care = 0
    if row['kind'] == 'family':
        child_care = sum(c.get('alive', True) and c.get('world') == world and c.get('age', 0) < 8 for c in game.player.offspring) * 15 * years
        carried_debt = int(game.family_state.get('debt',0))
    # Services keep the old authoritative treasury; supplies are goods, not a
    # second service debit. Optional supplies may use only this interval's
    # welfare envelope, leaving three years of basic maintenance intact.
    service_due = int(due*.65)+carried_debt+child_care
    from ..organization_heritage import allowance_account
    allowance_account(game,entity)
    paid=min(service_due,balance(game,source))
    study_paid=int(paid*.15)
    pay(game,source,f'study:{row["kind"]}:{entity.id}',study_paid,'门人日常劳务所得留作研习津贴')
    procure(game,source,world,paid-study_paid,'组织基本养护与日常劳务',partial=True)
    row['expense'] += paid
    row['shortfall'] = service_due - paid
    if row['kind'] == 'family':
        game.family_state['debt'] = service_due - paid
        from ..family_membership import player_kin,wage
        if entity is game.family and not player_kin(game,entity) and game.player.alive and game.player.world==world:
            amount=wage(world,game.player.realm_index)*years
            actual=pay(game,source,'player',amount,'外姓修士年度供养')
            row['benefit_due'],row['benefit_paid']=amount,actual
            row['expense']+=actual
    from .organization_consumption import consume
    market = game.economy_v2['markets'][f'{world}:{entity.location_id}']
    reserve = int(row.get('expected_upkeep', 0)*.65*3)
    # Save actual surplus for rare high-grade goods. A low service-price cap
    # must not make a perfectly funded organization unable to buy one artifact.
    rank=max((int(r) for r in row.get('workforce',{})),default=1)
    cap=min(10**12,max(int(row.get('expected_upkeep',0)*.35*100),BASE_PRICES[max(1,rank)-1]*36))
    envelope=int(due*.35)+int(max(0,row['income']-row['expense'])*.25)
    allowance=min(cap,row.get('supply_budget_credit',0)+envelope)
    budget=min(allowance,max(0,balance(game,source)-reserve))
    supplies=consume(game,market,entity,row,years,budget)
    row['expense']+=supplies
    row['supply_budget_credit']=max(0,min(allowance-supplies,max(0,balance(game,source)-reserve)))
    from .depot import advance as advance_depot
    advance_depot(game, maps, entity, row)
    from .estate_management import invest_surplus
    invest_surplus(game, maps, entity, row)
    # Depot purchases and investments spend the same treasury after welfare.
    # Keep the saved allowance bounded by the final available cash as well.
    row['supply_budget_credit']=min(row['supply_budget_credit'],max(0,balance(game,source)-reserve))


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
    from .enterprise_operations import advance_estates
    advance_estates(game, maps)
    from .market_governance import advance_governance
    advance_governance(game)


def public_finance(game, kind, identity):
    """Read-only and same-world; no adoption, settlement, or remote live data."""
    address = key(kind, identity)
    row = game.economy_v2.get('organizations', {}).get(address)
    if not row or row['world'] != game.player.world:
        return None
    return {k: row[k] for k in ('last_year', 'income', 'expense', 'shortfall', 'benefit_paid', 'benefit_due', 'produced')} | dict(
        balance=balance(game, address), product=ITEM_CATALOG[row['commodity']].name if row['commodity'] else None,
        industry_level=row.get('industry_level', 0), war_funding=row.get('war_funding', 1.),
        workforce=dict(row.get('workforce', {})), labor_capacity=row.get('labor_capacity', 0),
        expected_upkeep=row.get('expected_upkeep', 0), supply_coverage=row.get('supply_coverage',1),
        supply_expense=row.get('supply_expense',0),supplies_consumed=row.get('supplies_consumed',0))


def welfare(game, entity):
    row = register(game, 'sect', entity.id, entity.world)
    if row.get('welfare_year', -1) >= game.player.age:
        return 0.
    row['welfare_year'] = game.player.age
    due = max(25, WORLD_SYSTEMS['world_profiles'][entity.world]['tier'] * 100)
    source=key('sect',entity.id)
    reserve=int(row.get('expected_upkeep',0)*.65*3)
    paid=pay(game,source,f'background:{entity.world}',min(due,max(0,balance(game,source)-reserve)),'宗门年度修炼福利采购')
    row['benefit_due'], row['benefit_paid'] = due, paid
    row['expense'] += paid
    return paid / due
