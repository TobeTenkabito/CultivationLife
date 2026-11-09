"""Read-only original farm identity shared by contracts, tenders and commands."""
from .yaochi_rules import config
from .westward_rules import record
from .economy.enterprise_state import estates
from .economy.enterprise_rules import recipes
from .economy.resource_access import permits
from .economy.state import commodity_catalog

def identity():return f"celestial:{config()['location_id']}:farm"
def estate(game):return estates(game).get(identity())
def lease(game):return (estate(game) or {}).get('operating_lease')
def root(game):return record(game).get('garden',{})
def choices(game):
    row=estate(game) or dict(world='celestial',location=config()['location_id'],kind='farm')
    catalog=commodity_catalog('celestial')
    return {k:v for k,v in recipes('celestial',catalog).items() if v['kind']=='farm' and permits(row,v) and catalog[v['output']]['tier']<=game.player.realm_index+1}
