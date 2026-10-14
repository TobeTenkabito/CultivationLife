"""Original organizational treasuries and shared paid transfer operations."""
from ...content_registry import WORLD_SYSTEMS
from .state import ensure_state
from .ledger import account, balance, transfer_value


def key(kind, identity):
    return f'organization:{kind}:{identity}' if kind != 'yaochi' else 'institution:celestial:yaochi'


def faction_record(game, kind, identity):
    # This is the old authoritative treasury, also when the politics DLC is off.
    canonical=game.economy_v2.get('organization_aliases',{}).get(key(kind,identity))
    if canonical: _,kind,identity=canonical.split(':',2)
    record = game.intrigue_state.setdefault('factions', {}).setdefault(f'{kind}:{identity}', dict(
        kind=kind, id=identity, controller_id=None, positions={}, guests=[], prison=[],
        member_contribution={}, unrest=0., fear=0., resources=0, policy='balance'))
    record.setdefault('resources', 0)
    return record


def register(game, kind, identity, world):
    ensure_state(game)
    canonical=game.economy_v2.get('organization_aliases',{}).get(key(kind,identity))
    if canonical: _,kind,identity=canonical.split(':',2)
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
            produced=0, commodity=None, history=[], settlement_years=0, turnover=0)
        # A finite transfer funds institutions without a pre-existing treasury.
        if kind == 'yaochi':
            pay(game, f'background:{world}', address, 2000000, '瑶池设立采购周转金')
    elif rows[address]['world'] != world:
        # The existing faction migration owns its treasury. No goods or accrued
        # production work are transported by this fiscal address reconciliation.
        rows[address].update(world=world, production_credit=0,
            demand_credit={},cultivation_support={},maintenance_support={},breakthrough_support={},longevity_support={},supply_budget_credit=0,
            last_year=max(game.player.age, game.economy_v2['last_year']))
    return rows[address]


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


def operating_services(game, row, surplus):
    """Scale optional services to new earnings and protect existing reserves."""
    source = key(row['kind'], row['identity'])
    reserve = int(row.get('expected_upkeep', 0)*.65*3)
    due = max(0,surplus)*40//100
    paid = procure(game,source,row['world'],
        min(due,max(0,balance(game,source)-reserve)),
        '经营盈余用于阵法运转、共用设施与事务劳务',partial=True)
    row['operating_due'] = row.get('operating_due',0)+due
    row['operating_paid'] = row.get('operating_paid',0)+paid
    row['expense'] += paid
    return paid


def _estate_finance(game, estate):
    if estate['owner_kind'] not in {'sect','family'}:
        return None
    aliases=game.economy_v2.get('organization_aliases',{})
    address=key(estate['owner_kind'],estate['owner_id'])
    address=aliases.get(address,address)
    row=game.economy_v2.get('organizations',{}).get(address)
    if row is not None and 'estate_cost_credit' not in row:
        # Adopt only already-paid, unrecovered costs, never historical profit.
        # One aggregate credit per original treasury also handles transfers
        # between its own estates without attributing costs to individual goods.
        owned=(e for e in game.economy_v2.get('estates',{}).values()
               if aliases.get(key(e['owner_kind'],e['owner_id']),key(e['owner_kind'],e['owner_id']))==address)
        row['estate_cost_credit']=max(0,sum(e['expense']-e['income'] for e in owned))
    return row


def estate_cost(game, estate, amount):
    """Call before increasing the estate's expense; only actual paid costs count."""
    row=_estate_finance(game,estate)
    if row is not None:
        row['estate_cost_credit']+=amount


def prepare_ownership_change(game, estate, kind, identity):
    """Adopt each treasury's own costs before the incoming deed changes owner.

    The estate retains its full history, but those old payments are not costs
    paid by the recipient. Canonical aliases still share the original credit.
    Only actual ownership changes call this, never queries or annual scans.
    """
    previous = _estate_finance(game, estate) if estate.get('owner_kind') in {'sect', 'family'} else None
    recipient = _estate_finance(game, dict(owner_kind=kind, owner_id=identity))
    return previous, recipient


def estate_sale(game, estate, receipt, gross=0):
    """Recover paid inputs/maintenance first, then service new operating profit."""
    row=_estate_finance(game,estate)
    if row is None:
        return 0
    book_turnover(game, row, gross)
    surplus=max(0,receipt-row['estate_cost_credit'])
    row['estate_cost_credit']=max(0,row['estate_cost_credit']-receipt)
    if not surplus:
        return 0
    if not current_period(game, row):
        row['pending_income'] = row.get('pending_income', 0) + surplus
        return 0  # Optional services run once when this actual interval settles.
    row['income']+=surplus
    paid=operating_services(game,row,surplus)
    reserve=int(row.get('expected_upkeep',0)*.65*3)
    row['supply_budget_credit']=min(10**12,max(0,balance(game,key(row['kind'],row['identity']))-reserve),
        row.get('supply_budget_credit',0)+int((surplus-paid)*.40))
    if row['history'] and row['history'][-1][0]==game.player.age:
        row['history'][-1][1:]=[row['income'],row['expense']]
    return paid


def estate_purchase(game, estate, gross):
    row = _estate_finance(game, estate)
    if row is not None:
        book_turnover(game, row, gross)


def current_period(game, row):
    return row['last_year'] == game.player.age and bool(row.get('settlement_years'))


def book_turnover(game, row, gross):
    field = 'turnover' if current_period(game, row) else 'pending_turnover'
    row[field] = row.get(field, 0) + gross


def book_expense(game, row, amount):
    field = 'expense' if current_period(game, row) else 'pending_expense'
    row[field] = row.get(field, 0) + amount


def book_income(game, row, amount):
    field = 'income' if current_period(game, row) else 'pending_income'
    row[field] = row.get(field, 0) + amount


def caravan_dividend(game, fleet, amount):
    """Caravans settle before organizations: carry only the real paid dividend."""
    if fleet.get('owner_kind') not in {'sect', 'family'} or not amount:
        return
    address = key(fleet['owner_kind'], fleet['owner_id'])
    address = game.economy_v2.get('organization_aliases', {}).get(address, address)
    row = game.economy_v2.get('organizations', {}).get(address)
    if row is not None:
        row['pending_income'] = row.get('pending_income', 0) + amount


