"""Base retainer roster, original-person occupancy, paid service and return ledger."""
from . import military_movement as movement
from .economy.ledger import account, balance, transfer_value
from ..relationship_records import find_person


def state(scope):return scope.get('garrison',{})
def active(scope):return [u for u in state(scope).get('units',[]) if u['phase'] not in {'home','lost'}]
def stationed(game,scope,location):
    return [u for u in active(scope) if u['phase']=='stationed' and u['destination']==location
            and movement.valid(game,u,scope['world'])]


def ensure(game,scope):
    key='garrison:'+scope['id'];account(game,key)
    return scope.setdefault('garrison',dict(wallet=key,units=[],paid=0,spent=0,returned=0,last_year=game.player.age,shortfall=0))


def enlist(game,scope,identity,rate,*,capacity=6,commander=False):
    from .institution_ai.rules import person_reason
    from .institution_authority import responsibilities
    if type(rate) is not int or rate<=0:raise ValueError('军饷标准无效')
    if len(active(scope))>=capacity:raise ValueError('本府驻军名额已满')
    if any(identity in roster for war in game.wars if war.get('status') in {'active','peace_ready','withdrawing'}
           for roster in war.get('roster',{}).values()):
        raise ValueError('原人物仍在旧战役名册，不能重复驻防')
    if reason:=person_reason(game,identity,scope['world'],scope['location']):raise ValueError(reason)
    duties=responsibilities(game,identity)
    if duties and not (commander and duties==[scope] and scope['controller']==identity):
        raise ValueError('此人已有原任职或属员责任')
    n=find_person(game,identity)
    from .war.occupancy import busy
    org=game.sects.get(n.faction_id)
    if org and busy(game,org,exclude_garrison=scope['id']):raise ValueError('原组织尚未完全闲置，不能拆分重复出征')
    root=ensure(game,scope)
    root['units']=[u for u in root['units'] if u['phase'] not in {'home','lost'}]
    root['units'].append(dict(person_id=identity,origin=scope['location'],destination=scope['location'],
        home=scope['location'],route=[scope['location']],years=0,remaining=0,phase='stationed',
        last_year=game.player.age,rate=rate,organization=n.faction_id))


def provision(game,scope,amount):
    if type(amount) is not int or not 1<=amount<=10**15:raise ValueError('军费须为有效正整数')
    if any(u['phase']!='stationed' or u['destination']!=scope['location'] for u in active(scope)):
        raise ValueError('随军原款须在府署驻地交付，不得远程补给')
    root=ensure(game,scope)
    transfer_value(game,scope['wallet'],root['wallet'],amount,'原地方公款实拨随军营务经费')
    root['paid']+=amount


def plan(game,maps,scope,destination,identities=None):
    units=active(scope)
    selected=units if identities is None else [u for u in units if u['person_id'] in identities]
    if not selected or identities is not None and len(selected)!=len(set(identities)):
        raise ValueError('须选择原驻军中的有效人员')
    if any(u['phase']!='stationed' or not movement.valid(game,u,scope['world']) for u in selected):
        raise ValueError('驻军仍在行军、归返或原人物已失效')
    origins={u['destination'] for u in selected}
    if len(origins)!=1:raise ValueError('须先在同一驻地集结')
    journeys=movement.routes(maps,[find_person(game,u['person_id']) for u in selected],destination,next(iter(origins)))
    if all(j['years']==0 for j in journeys):raise ValueError('驻军已经在目的地')
    # Both outbound and return service are prepaid from original public cash.
    required=sum(u['rate']*(2*j['years']+10) for u,j in zip(selected,journeys))
    if balance(game,state(scope)['wallet'])<required:raise ValueError('随军经费不足以负担去返行程与十年驻防')
    return selected,journeys,required


def dispatch(game,maps,scope,destination,identities=None):
    units,journeys,_=plan(game,maps,scope,destination,identities)
    for unit,journey in zip(units,journeys):unit.update(journey,last_year=game.player.age)


def recall(game,maps,scope,identities=None):
    selected=None if identities is None else set(identities)
    for unit in active(scope):
        if selected is None or unit['person_id'] in selected:
            movement.recall(game,maps,unit,scope['world'])


def advance(game,maps,scope):
    from ..regional_context import task_active,region
    root=state(scope)
    if not root or (region(game) or game.player.world)!=scope['world'] or not task_active(game,scope['world']) or game.player.age<=root['last_year']:return
    root['last_year']=game.player.age
    due=0
    for unit in active(scope):
        if game.player.age>unit['last_year'] and movement.valid(game,unit,scope['world']):due+=unit['rate']
        movement.advance(game,unit,scope['world'])
    paid=min(due,balance(game,root['wallet']))
    if paid:
        target='background:'+scope['world'];account(game,target)
        transfer_value(game,root['wallet'],target,paid,'实际驻军年份营务服务，实耗不退款')
        root['spent']+=paid
    root['shortfall']=root['shortfall']+1 if paid<due else 0
    if root['shortfall']>=3:recall(game,maps,scope)
    if not active(scope):
        remaining=balance(game,root['wallet'])
        transfer_value(game,root['wallet'],scope['wallet'],remaining,'原驻军归返或失去执行资格，未耗原款退回原公账')
        root['returned']+=remaining


def advance_all(game,maps):
    from ..regional_context import ordinary_year
    if not ordinary_year(game):return
    for scope in game.economy_v2.get('administrations',{}).values():advance(game,maps,scope)
