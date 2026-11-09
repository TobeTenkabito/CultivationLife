"""DLC project agenda uses base prioritization; all spending still requires seven-office votes."""
import copy
from .institution_ai.rules import proposals,person_reason
from .court_bureau_rules import HOME
from .court_project_offers import offers
from .westward_rules import enabled
from ..regional_context import ordinary_year,region,historical
from ..relationship_records import find_person
from .economy.ledger import balance
from .court_bureau_rules import COURT

POLICIES={'balanced':'均衡施政','repair':'司土修缮','procurement':'天工补缺','training':'公共修持','service':'地方护民'}

def state(game):return game.heavenly_court.get('projects',{})

def advance(game,maps):
    if not enabled() or not ordinary_year(game) or (region(game) or game.player.world)!='celestial':return
    if historical(game):return
    # The original project catalog is a local information authority. No remote live target discovery.
    if game.player.world!='celestial' or game.player.location_id!=HOME:return
    now=game.player.age;s=state(game)
    if now//25<=s.get('agenda_observed',-1):return
    persons=[i for i,o in game.heavenly_court.get('officials',{}).items() if o.get('source')=='npc' and not person_reason(game,i,'celestial',HOME)]
    if not persons:return
    # Personal training quotes copy their player calculator. A calendar proxy is not
    # a Player value; current-year observations read the same original local game.
    rows=offers(getattr(game,'_game',game),maps)
    if not rows:return
    s=game.heavenly_court.setdefault('projects',{});s['agenda_observed']=now//25
    candidates=[dict(r,category=r['policy'],urgency=90 if r['policy']=='repair' else 60) for r in rows if not r['reason'] and r['key'] not in s.get('used',{})]
    results=[]
    for p in proposals(candidates,sorted(persons),s.get('priority','balanced'),balance(game,COURT),now):
        who=p['proposer'];offer=next(o for o in candidates if o['key']==p['key'])
        results.append(dict(key=offer['key'],policy=offer['policy'],target=offer['target'],name=offer['name'],person=who,
            proposer=find_person(game,who).name,observed=now,budget=offer['budget'],reason=offer['benefit']))
    s['npc_proposals']=results

def configure(game,value):
    parts=value.split(':')
    if len(parts)!=3 or parts[0] not in POLICIES:raise ValueError('施政授权无效')
    try:cap=int(parts[1]);batch=int(parts[2])
    except ValueError:raise ValueError('预算与采购批量须为整数') from None
    if not 0<=cap<=10**15 or not 1<=batch<=20:raise ValueError('单项预算或采购批量超出范围')
    s=game.heavenly_court.setdefault('projects',{})
    if s.get('current') and s['current']['status'] not in {'draft','rejected'}:raise ValueError('已拨款项目不能撤改预算')
    if s.get('current'):raise ValueError('请先交接当前草案，再调整下一批施政计划')
    s.update(priority=parts[0],project_cap=cap,batch_limit=batch)
    return '下一批施政优先序、单项预算上限和实货批量已登记；每案仍须原七曜听议表决。'

def public(game):
    s=state(game)
    return dict(priority=s.get('priority','balanced'),cap=s.get('project_cap',0),batch=s.get('batch_limit',20),
        proposals=copy.deepcopy(s.get('npc_proposals',[])) if game.player.location_id==HOME else [])
