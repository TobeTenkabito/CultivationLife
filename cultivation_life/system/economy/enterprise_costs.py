"""Shared carrying budgets and estimates; these calculations never debit cash."""
import math

from .enterprise_rules import title_cost
from .enterprise_state import payer
from .basket_trade import quote


def maintenance_breakdown(row, market):
    """Fixed facilities cost money even idle; prepaid work occupies storage too."""
    site = math.ceil(title_cost(row['world'], row['kind'], row['level'])*.002)
    value = sum(n*market['commodities'][k]['price']
                for k,n in row['stock'].items() if k in market['commodities'])
    job = row.get('job')
    if job and job['item'] in market['commodities']:
        value += job['quantity']*market['commodities'][job['item']]['price']
    return dict(site=site, storage=math.ceil(value*.002))


def annual_maintenance(row, market):
    return sum(maintenance_breakdown(row, market).values())


def operating_reserve(game, row, market):
    reserve = max(row.get('reserve_cash',100), annual_maintenance(row,market)*3)
    if row['owner_kind'] in {'sect','family'}:
        org = game.economy_v2.get('organizations',{}).get(payer(row),{})
        reserve += math.ceil(org.get('expected_upkeep',0)*.65*3)
    return reserve


def production_cost(row, market, recipe, batches=1):
    """Replacement-input and carrying estimate, never a second actual debit."""
    count = batches*recipe['quantity']
    wage = max(1, math.ceil(market['commodities'][recipe['output']]['price']*count*recipe['labor']))
    inputs = sum(quote(market['commodities'][k], 'buy', q*batches)['total']
                 for k,q in recipe['inputs'].items())
    # A funded batch reserves output space until completion. Estimate the same
    # carrying costs used by settlement, including existing unsold holdings.
    planned = dict(row, job=dict(item=recipe['output'], quantity=count))
    return wage + inputs + annual_maintenance(planned, market)*recipe['years']
