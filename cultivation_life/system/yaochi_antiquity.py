"""Three finite ruins on ordinary celestial roads; no pocket-world copies."""
import copy
from ..building_rules import ensure_state
from ..content_registry import ITEM_CATALOG
from ..economy_content import material_id
from ..models import HistoryRecord
from ..rules import add_item,remove_item
from ..runtime import now_iso
from ..relationship_records import find_person
from ..npc_custody import is_free
from ..person_assignments import research_assignment
from ..spatial_people import instance_of
from .faction_geography import person_site
from .earth_temple_rules import reason as actor_reason
from .court_bureau_rules import digest
from .westward_rules import record,enabled
from .westward_activity import finish_clock
from .yaochi_rules import config
from . import building_projects as buildings
from .building_destruction import rebuild

SITES={
    'archive':dict(name='栖霞遗府',location='expanse_celestial_9',realm=9,years=15,
        text='旧府残碑记着封藏次序。先拓录外壁，再决定循阵入室，或请同道合校。',
        choice='取出封存铁料，或保留藏室、承接原址修复。',item='triple_forged_god_demon_iron'),
    'forge':dict(name='玄炉别府',location='expanse_celestial_11',realm=10,years=20,
        text='炉道已冷，余热仍沿断裂导槽回流。前府拓片指出可以逐段导流。',
        choice='拆取炉心合金，或保全炉室、修作静修洞府。',item='yin_yang_hespring_steel'),
    'observatory':dict(name='问星仙府',location='expanse_celestial_15',realm=11,years=30,
        text='星台的三层刻盘失去校准。前府留下的方位记录能辨别真假星位。',
        choice='收取星台银髓，或保全观星静室、承接原址修复。',item='primordial_taiyi_silver')}

def state(game):return record(game).get('antiquity',{})
def current(game):return state(game).get('active')
def records(game):return state(game).get('sites',{})
def building_id(key):return 'antiquity:celestial:'+key
def token(game):
    return digest([state(game),game.player.age,game.player.world,game.player.location_id,
        game.player.realm_index,game.pending_event,[(i.id,i.quantity) for i in game.player.inventory],
        [game.building_state.get('records',{}).get(building_id(k)) for k in SITES]])

def companion_reason(game,n,entry=None):
    if not n or not is_free(n) or n.world!='celestial' or instance_of(game,n.id):return '同道须存活、自由且身处仙界普通地点'
    if n.id in game.intrigue_state.get('npc_prisons',{}):return '同道正在拘管中'
    if person_site(game,n)!=game.player.location_id:return '须与同道在遗府当面合作'
    if n.realm_index<game.player.realm_index:return '同道境界须不低于本人，才能分担解禁'
    if any((r.get('npc_id') or r.get('id'))==n.id for r in game.player.party):return '须先解除同行，避免重复占用'
    held=research_assignment(game,n.id)
    if held and (not entry or held['id']!=entry['id']):return '同道已有其他任务'
    return ''

def people(game):
    return [n for key in sorted(set(game.world_npcs)|set(game.notable_npcs))
            if (n:=find_person(game,key)) and not companion_reason(game,n)]

def opening_bill(game,cooperative=False):
    key=material_id('celestial',4,'ore_conduct');count=4 if cooperative else 8
    held={i.id:i.quantity for i in game.player.inventory}
    return dict(coins=2000,materials={key:count},material_name=ITEM_CATALOG[key].name,count=count,held=held.get(key,0),
        reason='解禁阵材或灵石不足' if held.get('spirit_stone',0)<2000 or held.get(key,0)<count else '')

def work_reason(game):
    if blocked:=actor_reason(game):return blocked
    r=current(game)
    if not r:return '没有在办的访古行程'
    if game.player.realm_index<SITES[r['key']]['realm']:return '当前境界不足以继续办理此府，可原址交接后返回'
    location=config()['location_id'] if r['phase']=='return' else SITES[r['key']]['location']
    if game.player.location_id!=location:return '须沿原地图亲赴'+('瑶池归档' if r['phase']=='return' else SITES[r['key']]['name'])
    if r.get('companion') and r['phase']=='opening':
        if blocked:=companion_reason(game,find_person(game,r['companion']),r):return blocked
    return ''

def begin(game):
    if blocked:=work_reason(game):raise ValueError(blocked)
    r=current(game)
    if r['phase'] not in {'survey','opening','restoring'} or r['progress']>=r['years']:raise ValueError('本步已完成，请作下一步抉择')
    return r['years']-r['progress']

def finish(game,elapsed,unit):
    r=current(game)
    if r:r['progress']=min(r['years'],r['progress']+elapsed)
    return finish_clock(game,elapsed,unit)

def commit(deps,game,action,summary):
    state(game)['last_result']=summary
    game.history.append(HistoryRecord('SYS_ANTIQUITY',1,game.player.age,'仙府访古',action,'completed',summary,{},['yaochi','antiquity']))
    game.updated_at=now_iso();deps.store.save(game);return deps.present(game)

def command(deps,game,action,target,amount):
    expected,_,value=target.partition('|')
    if type(amount) is not int or amount!=1 or expected!=token(game):raise ValueError('访古记录已变化，请刷新后重试')
    recovery=action in {'antiquity_abandon','antiquity_return','antiquity_release'}
    if blocked:=actor_reason(game,recovery=recovery):raise ValueError(blocked)
    r=current(game)
    if action=='antiquity_start':
        from .westward_activity import other_work,occupied
        if occupied(game) or other_work(game):raise ValueError('请先交接本人在办事务')
        spec=SITES.get(value)
        if not spec or game.player.realm_index<spec['realm']:raise ValueError('尚未达到此府要求的境界')
        if value in records(game):raise ValueError('原遗府已登记，不能重开或重复取藏')
        prior=list(SITES).index(value)
        if prior and not records(game).get(list(SITES)[prior-1],{}).get('returned'):raise ValueError('须先完成前府归档，取得后续线索')
        if game.player.location_id!=spec['location']:raise ValueError('须亲赴遗府所在地调查')
        s=game.yaochi_state.setdefault('westward',{}).setdefault('antiquity',{})
        r=dict(id=building_id(value),key=value,phase='survey',started=game.player.age,years=5,progress=0,companion=None)
        s['active']=r;s.setdefault('sites',{})[value]=dict(started=game.player.age,returned=False)
        # A single explicitly authored, empty ruined building; no NPC or inventory clone.
        ensure_state(game)['records'].setdefault(r['id'],dict(id=r['id'],name=spec['name'],type='artificiality',subtype='cave',
            level=1,status='destroyed',quality='professional',invested=0,address=dict(world='celestial',instance_id=None,location_id=spec['location']),
            owner=dict(kind='background',id=r['id']),users=[],public=False))
        summary='已登记原址与五年拓碑调查；往返均沿原地图。'
    elif action=='antiquity_work':
        begin(game);return deps.advance(game.id,'antiquity_work',1)
    elif not r:raise ValueError('没有在办的访古行程')
    elif action=='antiquity_release':
        if game.player.location_id!=SITES[r['key']]['location']:raise ValueError('须返回原合作地点交接')
        if not r.get('companion'):raise ValueError('没有合作人')
        r['companion']=None;r['phase']='survey';r.update(progress=5,years=5)
        summary='解除合作；已付阵材和工时不退，可另选完整解禁方案。'
    elif action=='antiquity_abandon':
        if r['phase']=='return':raise ValueError('已完成取舍，须回瑶池归档')
        if game.player.location_id!=SITES[r['key']]['location']:raise ValueError('须回原遗址交接，不远程撤销合作')
        records(game)[r['key']].update(result='放弃取藏，旧址保留',returned=False)
        r.update(phase='return',companion=None)
        summary='放弃本次取藏，已耗工料不退；须回瑶池归档已有线索，原址不重开。'
    elif action=='antiquity_return':
        if r['phase']!='return' or game.player.location_id!=config()['location_id']:raise ValueError('须完成取舍并实际返回瑶池归档')
        records(game)[r['key']].update(returned=True,closed=game.player.age)
        state(game)['active']=None;summary='已将原址与所得分配归档，后续线索保留。'
    else:
        if blocked:=work_reason(game):raise ValueError(blocked)
        spec=SITES[r['key']]
        if action=='antiquity_open':
            if r['phase']!='survey' or r['progress']<5:raise ValueError('须完成原址调查')
            mode,_,identity=value.partition('~')
            if mode not in {'study','cooperate'}:raise ValueError('请选择独自解阵或合作解阵')
            if mode=='cooperate':
                if blocked:=companion_reason(game,find_person(game,identity)):raise ValueError(blocked)
            bill=opening_bill(game,mode=='cooperate');materials=bill['materials']
            buildings.pay(game,bill,'访古解禁实付阵材')
            r.update(phase='opening',progress=0,years=spec['years'] if mode=='study' else (spec['years']+1)//2,
                mode=mode,companion=identity if mode=='cooperate' else None,paid=materials)
            summary='已付阵材。'+('约定本人取半份封藏，另半份由合作方捐入当地市场；保全静室则双方取得使用权。' if mode=='cooperate' else '独自研读完整禁制，所得由本人取舍。')
        elif action=='antiquity_choose':
            if r['phase']!='opening' or r['progress']<r['years']:raise ValueError('解禁工时未满')
            if value not in {'salvage','preserve'}:raise ValueError('请选择取藏或保全静室')
            if value=='salvage':
                add_item(game.player,spec['item'],2 if r.get('companion') else 4)
                if r.get('companion'):
                    from .economy.state import local_market,reprice
                    market=local_market(game);product=market['commodities'].get(spec['item']) if market else None
                    if not product:raise ValueError('当地市场无法接收合作方约定寄售的材料')
                    product['stock']+=2;reprice(game,market,product)
                r.update(phase='return',companion=None)
                summary='一次性封藏已按约分配；合作份额按事先约定进入当地市场，静室保持遗址。'
            else:
                building=game.building_state['records'][r['id']]
                # The authored testament grants title only after choosing to preserve the empty ruin.
                building['owner']=dict(kind='player',id=game.id)
                if r.get('companion'):building['users'].append(dict(kind='npc',id=r['companion']))
                r.update(phase='restoring',years=10,progress=0,companion=None)
                summary='承接原空置遗府，放弃封藏；须完成十年整理并自费按原报价重建，才能用于原洞府聚气。'
            records(game)[r['key']].update(choice=value,result=summary)
        elif action=='antiquity_rebuild':
            if r['phase']!='restoring' or r['progress']<r['years']:raise ValueError('须完成十年原址整理')
            row=game.building_state['records'][r['id']]
            rebuild(game,row,None);r['phase']='return';summary='沿原营造价格实付重建；可在原建筑页设为聚气洞府，仍须回瑶池归档。'
        else:raise ValueError('未知访古操作')
    return commit(deps,game,action,summary)

def public(game,maps):
    if game.player.world!='celestial' or game.guixu_state.get('player_session'):return None
    r=copy.deepcopy(current(game));local=not r or game.player.location_id==SITES[r['key']]['location']
    candidates=people(game) if local else []
    return dict(enabled=enabled(),token=token(game),reason=actor_reason(game),recovery_reason=actor_reason(game,recovery=True),
        work_reason=work_reason(game),active=r,last_result=state(game).get('last_result'),
        sites=[dict(id=k,**s,place=maps.location('celestial',s['location'])['name'],reward=ITEM_CATALOG[s['item']].name,
                    record=copy.deepcopy(records(game).get(k)),local=game.player.location_id==s['location']) for k,s in SITES.items()],
        candidates=[dict(id=n.id,name=n.name) for n in candidates],
        opening=opening_bill(game),cooperative=opening_bill(game,True),
        repair=buildings.quote(game,'rebuild',game.building_state['records'][r['id']]) if r and local and r['phase']=='restoring' else None)
