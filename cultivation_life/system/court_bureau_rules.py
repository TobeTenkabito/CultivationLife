"""Explicit appointments and real-person authority for the four civil bureaus."""
import hashlib
import json
from fractions import Fraction
from ..content_registry import WORLD_SYSTEMS
from ..relationship_records import find_person
from ..npc_custody import is_free
from ..spatial_people import instance_of
from .earth_temple_rules import reason as actor_reason
from .faction_geography import person_site
from .westward_rules import enabled

OFFICES = {
    'patrol': dict(name='巡天署', mark='巡', title='道路巡检', years=10,
        text='亲赴相邻道路查验；完成巡检后清除该边已登记的地方阻断。'),
    'land': dict(name='司土署', mark='土', title='公共城址复建', years=20,
        text='核验公开城市遗址，原市场采购工料，沿原工程入口复建。私人地产不列入公费工程。'),
    'works': dict(name='天工署', mark='工', title='邻域实货调拨', years=10,
        text='从本地实购标准商品，运抵已知相邻市场补缺；公物与行囊分开保管。'),
    'audit': dict(name='御史台', mark='察', title='公务收支复核', years=5,
        text='核对已归档公务的付款、退回与交付回执；确认结清或标记账差，不能凭空定罪。'),
}
HOME='jade_capital'
COURT='organization:court:heavenly'

def state(game): return game.heavenly_court.get('bureaus',{})
def jobs(game): return state(game).get('jobs',[])
def active(game): return [j for j in jobs(game) if j['status']=='active']
def personal(game): return next((j for j in active(game) if j['person']=='player'),None)
def digest(value): return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:24]

def reason(game, *, home=False, recovery=False):
    blocked=actor_reason(game,recovery=recovery)
    if blocked:return blocked
    if not game.heavenly_court:return '天庭名册尚未建立'
    if home and game.player.location_id!=HOME:return '须亲临玉京仙都办理任职与交接'
    return ''

def officer_reason(game,npc, *, assigned=False):
    if not npc or not is_free(npc) or npc.world!='celestial' or instance_of(game,npc.id):return '须为仙界自由、存活的原人物'
    official=game.heavenly_court.get('officials',{}).get(npc.id)
    if not official or official.get('source')!='npc':return '须在原天官名册中，席位代表文字记录不能派遣'
    if npc.realm_index<9:return '属员须达到真仙境界'
    if not person_site(game,npc):return '原人物地点不明，不能调度'
    if npc.id in game.intrigue_state.get('npc_prisons',{}):return '此人正在拘禁中'
    if any((r.get('npc_id') or r.get('id'))==npc.id for r in game.player.party):return '须先解除同行，再安排公务'
    if not assigned:
        from ..person_assignments import research_assignment
        if research_assignment(game,npc.id):return '此人已有任务占用'
    return ''

def reward(actor,years):
    from .yaochi_rules import commission_reward
    base=commission_reward(actor,dict(reward=400))
    unit=int(WORLD_SYSTEMS['time_units'][str(actor.realm_index)])
    return Fraction(base*6*years,5*40*unit)

def stamp(game):
    p=game.player
    people=[]
    identities=set(game.heavenly_court.get('officials',{}))|{j['offer']['target'] for j in active(game) if j['offer'].get('operation')}
    for identity in sorted(identities):
        n=find_person(game,identity)
        if n:
            people.append([n.id,n.alive,n.realm_index,n.layer,n.wounds,n.world,person_site(game,n),is_free(n),
                n.id in game.intrigue_state.get('npc_prisons',{})])
    return digest([state(game),p.age,p.world,p.location_id,p.realm_index,p.layer,
        game.heavenly_court.get('player_grade'),game.heavenly_court.get('treasury'),game.heavenly_court.get('wanted_ids'),people,
        [(r.get('npc_id') or r.get('id')) for r in p.party]])

def local_officers(game):
    result=[]
    for identity,row in game.heavenly_court.get('officials',{}).items():
        if row.get('source')!='npc':continue
        n=find_person(game,identity)
        if n and n.world=='celestial' and person_site(game,n)==game.player.location_id:
            result.append(dict(id=n.id,name=n.name,realm=n.realm_index,
                department=state(game).get('staff',{}).get(n.id),reason=officer_reason(game,n)))
    return sorted(result,key=lambda r:r['id'])
