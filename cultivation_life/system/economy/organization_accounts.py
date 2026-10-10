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
            produced=0, commodity=None, history=[])
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


