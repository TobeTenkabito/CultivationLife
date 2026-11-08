"""One authored celestial incident, factual progress and original asset quotes."""
from ..building_schema import address
from ..building_rules import initial_rows
from ..content_registry import ITEM_CATALOG
from ..economy_content import material_id
from ..relationship_records import find_person
from .court_bureau_rules import digest
from .earth_temple_rules import reason as actor_reason
from .westward_rules import record,enabled
from .yaochi_rules import config
from .yaochi_garden import estate as garden_estate
from .yaochi_antiquity import companion_reason
from . import building_projects as buildings

BUILDING='purple-east:celestial:cloud-palace'
PLANS={
    'guard':dict(name='守土济民',years=30,text='本人承接原仙府，并向当地居民开放；取得原产权，后续公开与私人使用仍按原建筑权限办理。'),
    'public':dict(name='公共修持',years=20,text='原仙府转交天庭作公共静室；须已有真实公共修持议案的交付回执，不给本人拨款或加修为。'),
    'yaochi':dict(name='瑶池承办',years=20,text='原仙府转交瑶池并保留本人具名使用权；须以原仙圃合同证明供货，经营款、保证金及期限照常。'),
    'shared':dict(name='同道共修',years=15,text='本人承担原工程，与一名同境以上原同道共同整理，双方获得使用权；对方实际在场并被占用。'),
}
PHASES={'survey':'一 · 紫气现世','dispute':'二 · 利益分歧','hearing':'三 · 瑶池定议',
        'implementation':'四 · 落地与后果','complete':'紫气东来 · 已归档'}

def state(game):return record(game).get('purple_east',{})
def work(game):return state(game).get('work')
def original(game):return game.building_state.get('records',{}).get(BUILDING)
def local(game):return game.player.location_id==config()['location_id']

def token(game):
    return digest([state(game),game.updated_at,game.player.age,address(game),original(game),game.pending_event,
                   [(i.id,i.quantity) for i in game.player.inventory],game.yaochi_state.get('merit')])

def reason(game,recovery=False):
    return actor_reason(game,recovery=recovery) or ('' if local(game) else '须沿原地图亲赴瑶池西麓；异地不推进调查、听议或工程')

def bill(game,kind):
    materials={material_id('celestial',4,'ore_conduct'):2 if kind=='canal' else 4}
    coins=2000 if kind=='canal' else 5000
    held={i.id:i.quantity for i in game.player.inventory}
    return dict(coins=coins,materials=materials,reason='疏导灵石或导灵阵材不足' if held.get('spirit_stone',0)<coins or any(held.get(k,0)<n for k,n in materials.items()) else '',
        recipe=[dict(name=ITEM_CATALOG[k].name,needed=n,held=held.get(k,0)) for k,n in materials.items()])

def proofs(game):
    s=state(game);start=s.get('started',game.player.age)
    fair=next((r for r in record(game).get('fair',{}).get('entries',[]) if r.get('closed',-1)>=start and r['status']=='won'),None)
    council=next((r for r in reversed(game.heavenly_court.get('projects',{}).get('history',[]))
        if r.get('closed',-1)>=start and r['status']=='closed' and r['offer']['policy']=='training'),None)
    delivery=any(r.get('delivered') and r.get('closed',-1)>=start and r['wallet'] not in s.get('garden_baseline',[])
        for r in record(game).get('garden',{}).get('receipts',[]))
    return dict(fair=fair['id'] if fair else None,council=council['id'] if council else None,garden=delivery,
        civic=bool(s.get('civic_done')),investigation=s.get('mitigation'))

def plan_reason(game,key):
    p=proofs(game)
    if key=='public' and not p['council']:return '须先通过原七曜表决并完成一项公共修持项目；不以功德替代投票'
    if key=='yaochi' and not p['garden']:return '须在本案登记后新完成原仙圃实物供货合同'
    if key=='guard' and not p['civic']:return '须完成本案公开护持与居民安置工时'
    return ''

def work_reason(game):
    if blocked:=reason(game):return blocked
    w=work(game)
    if not w:return '没有正在办理的主线工序'
    row=original(game)
    if not row:return '原仙府记录失效，不能重建另一份仙府'
    if w['kind']=='build':
        if row['owner']!=dict(kind='background',id=BUILDING) or row['status']!='destroyed':return '原仙府产权或损毁状态已经变化，请原址核验'
        n=w.get('companion')
        if n:
            if blocked:=companion_reason(game,find_person(game,n),dict(id=BUILDING)):return blocked
    return ''

def begin(game):
    if blocked:=work_reason(game):raise ValueError(blocked)
    w=work(game)
    if w['progress']>=w['years']:raise ValueError('实际工时已完成，请提交本步结果')
    return w['years']-w['progress']

def finish(game,elapsed,unit):
    from .westward_activity import finish_clock
    w=work(game)
    if w:w['progress']=min(w['years'],w['progress']+elapsed)
    return finish_clock(game,elapsed,unit)

def start_work(game,kind,years,companion=None):
    from .westward_activity import occupied,other_work
    if occupied(game) or other_work(game):raise ValueError('请先交接本人在办事务，再接受主线工时')
    state(game)['work']=dict(kind=kind,years=years,progress=0,companion=companion)

def city_id():
    place=dict(world='celestial',instance_id=None,location_id=config()['location_id'])
    return next((r['id'] for r in initial_rows(place) if r['type']=='city'),None)
