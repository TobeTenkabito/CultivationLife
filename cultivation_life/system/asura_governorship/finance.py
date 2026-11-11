"""Original public-building quote, usable by a present NPC governor as well."""
from . import rules
from .. import building_projects
from ..institution_ai import procurement
from ..institution_ai.buildings import BuildingActor
from ..economy.ledger import balance


def actor_for(row):
    return (BuildingActor(row['world'],row['location'],row['owner']['kind'],row['owner']['id'],row['holder'],None)
            if row['holder'] and row['holder']!='player' else None)


def bill(game,row):
    target=rules.building(game,row) or rules.shell(row)
    market=game.economy_v2.get('markets',{}).get(row['world']+':'+row['location'])
    quoted=building_projects.quote(game,'rebuild',target,payer=row['wallet'],stock={},actor=actor_for(row))
    reason=quoted['reason'] if quoted['reason']!='灵石或筑城材料不足' else ''
    try:purchase=procurement.cost(market,quoted['materials'])
    except ValueError as error:purchase=0;reason=str(error)
    total=quoted['coins']+purchase
    if not reason and balance(game,row['wallet'])<total:reason='本府公款不足，须先拨款或资助'
    return dict(quoted,purchase=purchase,total=total,reason=reason)
