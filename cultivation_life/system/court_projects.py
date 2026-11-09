"""Seven-office project votes, funded delivery and review of actual receipts."""
import copy
import math
from ..content_registry import WORLD_SYSTEMS,ITEM_CATALOG
from ..relationship_records import find_person
from ..runtime import decode_rng,encode_rng,now_iso
from ..models import HistoryRecord
from .court.ballots import player_ballot
from .court_bureau_rules import digest,COURT,reason as actor_reason
from .court_case_facts import restriction
from .court_project_offers import KINDS,offers,validate,deliver
from .court_bureau_projects import reserve,close
from .economy.ledger import balance,transfer_value
from .economy import organizations as finance
from .faction_geography import person_site
from .westward_activity import finish_clock
from .westward_rules import enabled

def state(game):return game.heavenly_court.get('projects',{})
def current(game):return state(game).get('current')
def work(game):return state(game).get('work')

def holders(game):
    court=game.heavenly_court;out=[]
    for office,h in court.get('offices',{}).items():
        if not h or h.get('end_unit',court['unit'])<=court['unit']:continue
        who=h['holder_id'];official=court['officials'].get(who)
        if not official:continue
        if official.get('source')=='npc':
            n=find_person(game,who)
            if not n or not n.alive or n.world!='celestial':continue
        out.append(dict(office=office,holder=who,name=h['holder_name'],source=official.get('source')))
    return out

def reason(game,recovery=False):
    if blocked:=actor_reason(game,recovery=recovery):return blocked
    if recovery:return ''
    if blocked:=restriction(game,'player'):return blocked
    return ''

def authority(game):
    if blocked:=reason(game):return blocked
    if game.heavenly_court.get('open_election'):return '原七曜选举尚待答复，暂缓项目表决'
    if 'player' not in [h['holder'] for h in holders(game)]:return '须经原选举取得在任七曜席位，才能提出或表决项目'
    return ''

def token(game):
    p=game.player
    return digest([state(game),holders(game),p.age,p.world,p.location_id,game.heavenly_court.get('treasury'),
                   game.heavenly_court.get('player_support'),game.pending_event])

def work_reason(game):
    if blocked:=reason(game):return blocked
    r=current(game);w=work(game)
    if not r or not w:return '没有正在办理的议案工序'
    if game.player.age>=r['deadline']:return '项目期限已满，请交接资金与公物'
    if game.player.location_id!=w['location']:return '须亲赴原工序地点，异地或独立空间不计工时'
    if w['stage']=='execute':
        try:validate(game,r['job'])
        except ValueError as error:return str(error)
    return ''

def begin(game):
    if blocked:=work_reason(game):raise ValueError(blocked)
    w=work(game)
    if w['progress']>=w['years']:raise ValueError('本步工时已完成，请提交结果')
    return min(w['years']-w['progress'],current(game)['deadline']-game.player.age)

def finish(game,elapsed,unit):
    w=work(game);r=current(game)
    if w:
        w['progress']=min(w['years'],w['progress']+elapsed)
        if w['stage'] in {'execute','review'}:
            transfer_value(game,r['job']['wallet'],'background:celestial',elapsed*1000,'七曜项目实际工时劳务')
            r['job']['spent']+=elapsed*1000
            if w['stage']=='execute':r['job']['progress']=w['progress']
    return finish_clock(game,elapsed,unit)

def start_work(game,r,stage,location,years):
    from .westward_activity import occupied,other_work
    if occupied(game) or other_work(game):raise ValueError('请先交接本人当前事务')
    state(game)['work']=dict(stage=stage,location=location,years=years,progress=0)

def archive(game,r,cancel=False):
    job=r.get('job')
    if job:
        close(game,job,cancel=cancel)
        game.heavenly_court.setdefault('bureaus',{}).setdefault('jobs',[]).append(job)
        r['job_id']=job['id'];r['receipt']=copy.deepcopy(job['receipt']);r.pop('job')
    missed=cancel and bool(r.get('pledges')) and game.player.age>=r['deadline']
    if missed:game.heavenly_court['player_support']=max(0,game.heavenly_court['player_support']-5)
    elif not cancel:game.heavenly_court['player_support']=min(100,game.heavenly_court['player_support']+3)
    r.update(status='cancelled' if cancel else 'closed',closed=game.player.age,broken_promise=missed)
    state(game).setdefault('history',[]).append(r);state(game).pop('current',None);state(game).pop('work',None)

def command(deps,game,action,target,amount):
    expected,_,value=target.partition('|')
    if type(amount) is not int or amount!=1 or expected!=token(game):raise ValueError('项目议政记录已变化，请刷新后重试')
    recovery=action=='council_cancel'
    if blocked:=reason(game,recovery):raise ValueError(blocked)
    r=current(game)
    if action=='council_strategy':
        if blocked:=authority(game):raise ValueError(blocked)
        from .court_strategy import configure
        summary=configure(game,value)
    elif action=='council_propose':
        if blocked:=authority(game):raise ValueError(blocked)
        if r:raise ValueError('请先结清当前议案')
        offer=next((o for o in offers(game,deps.maps) if o['token']==value),None)
        if not offer or offer['reason']:raise ValueError(offer['reason'] if offer else '原目标或报价已变化，请刷新')
        if offer['key'] in state(game).get('used',{}):raise ValueError('同一期原项目已提案，不能重复拨款')
        s=game.heavenly_court.setdefault('projects',{})
        number=s.get('sequence',0)+1
        r=dict(id='council-'+str(number),offer=copy.deepcopy(offer),status='draft',started=game.player.age,
            deadline=game.player.age+500,pledges={},attempts=[],job=None)
        suggestion=next((p for p in s.get('npc_proposals',[]) if p['key']==offer['key']),None)
        if suggestion:r['npc_proposal']=copy.deepcopy(suggestion)
        start_work(game,r,'prepare',game.player.location_id,5)
        s.update(sequence=number,current=r);s.setdefault('used',{})[offer['key']]=r['id']
        summary='已登记具体受益对象与预算，须实际五年听议；通过前不占用工程本金。'
    elif not r:raise ValueError('没有当前议案')
    elif action=='council_work':
        begin(game);return deps.advance(game.id,'council_work',1)
    elif action=='council_contact':
        if blocked:=authority(game):raise ValueError(blocked)
        if r['status']!='draft':raise ValueError('仅表决前可以接触代表')
        if len(r['pledges'])>=2 or value in r['pledges']:raise ValueError('本案至多向两名在任代表作出承诺，不能重复购买支持')
        h=next((h for h in holders(game) if h['holder']==value and value!='player'),None)
        if not h:raise ValueError('此人不是在任七曜；49选举席位不参加项目表决')
        if h['source']=='npc':
            from ..npc_custody import is_free
            n=find_person(game,value)
            if not is_free(n) or person_site(game,n)!=game.player.location_id:raise ValueError('须与原星君在同一地点当面协商')
        # A named institutional office without an NPC receives a written undertaking, never a synthetic person.
        transfer_value(game,'player','background:celestial',200,'项目会商文书费用')
        r['pledges'][value]=dict(name=h['name'],promise='二百五十年内交付并公开原收支回执',age=game.player.age)
        r['deadline']=min(r['deadline'],r['started']+250)
        summary='承诺本案缩短至二百五十年并公开账目；代表仍按原支持度表决，不保证赞成。'
    elif action=='council_vote':
        if blocked:=authority(game):raise ValueError(blocked)
        w=work(game)
        if r['status']!='draft' or not w or w['stage']!='prepare' or w['progress']<5:raise ValueError('须完成五年实际听议后才能表决')
        if game.player.location_id!=r['offer']['origin']:raise ValueError('须回原提案地点表决')
        if game.player.age>=r['deadline']:raise ValueError('本案已逾期，请交接')
        offered=next((o for o in offers(game,deps.maps) if o['policy']==r['offer']['policy'] and o['target']==r['offer']['target']),None)
        if not offered or offered['reason']:raise ValueError('原受益对象或采购供给已失效，请修改方案或交接')
        if value!=offered['token']:raise ValueError('表决预算报价已变化，请刷新后按当前预算表决')
        if offered['materials']!=r['offer']['materials'] or offered.get('before')!=r['offer'].get('before') or offered.get('building_token')!=r['offer'].get('building_token'):raise ValueError('原项目内容已变化，请修改方案重新听议')
        cost=math.ceil(WORLD_SYSTEMS['heavenly_court'].get('policy_treasury_cost',0))
        if balance(game,COURT)<offered['budget']+cost:raise ValueError('原天庭府库不足以承担表决及足额项目预算')
        finance.procure(game,COURT,'celestial',cost,'七曜项目公开表决支出')
        rng=decode_rng(game.seed,game.rng_state)
        ballot=player_ballot(game.heavenly_court,[h['holder'] for h in holders(game)],rng,pledges=r['pledges'])
        game.rng_state=encode_rng(rng);r['attempts'].append(dict(age=game.player.age,**ballot));state(game).pop('work',None)
        if ballot['passed']:
            offer=copy.deepcopy(offered);r['offer']=offer
            job=dict(id=r['id'],kind=offer['kind'],name=KINDS[offer['policy']]+' · '+offer['name'],person='player',
                origin=offer['origin'],location=offer['location'],offer=offer,status='active',phase='work',years=offer['years'],
                progress=0,started=r['started'],deadline=r['deadline'],wallet='court-bureau:'+game.id+':'+r['id'],
                budget=offer['budget'],spent=0,reward='0',home=offer['origin'])
            reserve(game,job,offer,job['budget']);r.update(job=job,status='approved')
        else:r['status']='rejected'
        summary=f"在任七曜{ballot['yes']}票赞成、{ballot['no']}票反对，"+('通过。本金已实付托管，工料已从原市场采购。' if ballot['passed'] else '否决。可调整具体目标重新听议，不能立即重投。')
    elif action=='council_revise':
        if blocked:=authority(game):raise ValueError(blocked)
        if game.player.age>=r['deadline']:raise ValueError('原案已逾期，请交接后另期提案')
        if r['status'] not in {'draft','rejected'}:raise ValueError('拨款后不能更改受益对象或承诺')
        offered=next((o for o in offers(game,deps.maps) if o['token']==value and o['policy']==r['offer']['policy']),None)
        if not offered or offered['reason']:raise ValueError('须选择同类有效项目重新报价')
        if offered['key']!=r['offer']['key'] and offered['key'] in state(game).get('used',{}):raise ValueError('该项目本期已经提案')
        state(game).pop('work',None)
        start_work(game,r,'prepare',game.player.location_id,5)
        state(game).setdefault('used',{})[offered['key']]=r['id'];r.update(offer=copy.deepcopy(offered),status='draft',pledges={})
        summary='已调整并重新公示方案；此前表决与费用保留，再完成五年听议。原截止期限不延长。'
    elif action=='council_public':
        if r['status']!='approved' or r['offer']['policy']!='service':raise ValueError('须先取得本庙服务协议决议')
        from .earth_temple_rules import temple
        from .building_projects import set_public
        row=temple(game,r['offer']['target'])
        if not row:raise ValueError('原庙已经失效')
        set_public(game,row,True);summary='原庙已开放公共使用，产权与具名许可保留。须另完成原护民庙务才能验收。'
    elif action in {'council_execute','council_review'}:
        if game.player.age>=r['deadline']:raise ValueError('原案已逾期，请交接')
        stage='execute' if action=='council_execute' else 'review'
        if r['status']!=('approved' if stage=='execute' else 'executed'):raise ValueError('当前阶段不能开始此工序')
        location=r['offer']['location'] if stage=='execute' else r['offer']['origin']
        if game.player.location_id!=location:raise ValueError('须实际到达执行现场或原提案地复核')
        if stage=='execute':validate(game,r['job'])
        start_work(game,r,stage,location,r['offer']['years'] if stage=='execute' else 5)
        summary='开始原址实际履约。' if stage=='execute' else '开始五年收支与履约复核。'
    elif action=='council_finish':
        if blocked:=work_reason(game):raise ValueError(blocked)
        w=work(game)
        if w['progress']<w['years'] or w['stage']=='prepare':raise ValueError('实际工时未满或尚待表决')
        if w['stage']=='execute':
            result=deliver(game,r['job']);r['job'].update(result=result,delivered=True);r['status']='executed'
            state(game).pop('work',None);summary=result+' 须回原提案地点复核结项。'
        else:
            archive(game,r);summary='原回执已公开并移交诸司履历，未耗款退回原府库；履约支持度增加3，不给本人另发钱货或功德。'
    elif action=='council_cancel':
        if r.get('job') and game.player.location_id!=r['offer']['origin']:raise ValueError('须沿原地图返回原提案地交接公物与余款')
        archive(game,r,True);summary='原款及余货已交接；已耗工料与表决费不退。逾期承诺扣5支持，原逾期回执进入现有监察线索。'
    else:raise ValueError('未知项目议政操作')
    deps._sync_player_court_identity(game)
    s=game.heavenly_court.setdefault('projects',{});s['last_result']=summary
    game.history.append(HistoryRecord('SYS_COURT_PROJECT',1,game.player.age,'七曜项目议政',action,'completed',summary,{},['court','politics']))
    game.updated_at=now_iso();deps.store.save(game);return deps.present(game)

def public(game,maps):
    from .court_strategy import public as strategy_public
    if game.player.world!='celestial' or game.guixu_state.get('player_session'):return None
    rows=offers(game,maps) if enabled() else []
    for row in rows:
        row['policy_name']=KINDS[row['policy']];row['place']=maps.location('celestial',row['location'])['name']
        row['goods']=[dict(name=ITEM_CATALOG[k].name,quantity=n) for k,n in row['materials'].items()]
        if row['key'] in state(game).get('used',{}):row['used']=True
    r=current(game)
    vote_offer=next((o for o in rows if r and o['policy']==r['offer']['policy'] and o['target']==r['offer']['target']),None)
    execute_reason=reason(game)
    if r and r['status']=='approved' and not execute_reason:
        try:validate(game,r['job'])
        except ValueError as error:execute_reason=str(error)
    review_reason=reason(game) or ('须回原提案地点复核' if r and game.player.location_id!=r['offer']['origin'] else '')
    return dict(strategy=strategy_public(game),enabled=enabled(),token=token(game),reason=reason(game),authority=authority(game),recovery_reason=reason(game,True),vote_offer=vote_offer,
        treasury=balance(game,COURT),current=copy.deepcopy(current(game)),work=copy.deepcopy(work(game)),work_reason=work_reason(game),
        execute_reason=execute_reason,review_reason=review_reason,
        offers=rows,holders=holders(game),history=copy.deepcopy(state(game).get('history',[])[-6:]),last_result=state(game).get('last_result'))
