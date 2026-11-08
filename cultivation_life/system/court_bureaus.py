"""Four appointments, bounded jobs and accountable original officer delegation."""
import copy
from fractions import Fraction
from ..models import HistoryRecord
from ..runtime import now_iso
from ..relationship_records import find_person
from .court_bureau_rules import (OFFICES,HOME,COURT,state,jobs,active,personal,reason,
    officer_reason,reward,stamp,local_officers)
from . import court_bureau_projects as projects
from . import court_bureau_runtime as runtime
from .faction_geography import person_site
from .economy.ledger import balance
from .westward_rules import enabled,adopt_merit
from . import court_inspection as inspection
from .court_case_facts import restriction,record_appointment

def find(game,identity):
    return next((j for j in jobs(game) if j['id']==identity),None)

def occupied(game):
    from .westward_activity import occupied as westward_occupied
    if westward_occupied(game):return True
    if any(r['status']=='active' for r in game.yaochi_state.get('westward',{}).get('fair',{}).get('entries',[])):return True
    from .earth_temple_rules import pending
    from .westward_rules import project
    return bool(personal(game) or state(game).get('review') or inspection.active(game) or pending(game) or project(game) or game.yaochi_state.get('job'))

def appointment_reason(game):
    from .immortal_identity_rules import join_reason
    return reason(game,home=True) or join_reason(game) or ('请先交接全部公务及公物' if active(game) or state(game).get('review') or inspection.active(game) else '')

def handover_reason(game,job):
    if job['phase']=='evacuating':return '伤者正在实际转运，抵达后才能交接'
    npc=find_person(game,job['person']) if job['person']!='player' else None
    here=job['origin']
    if job['person']!='player':
        # A lost reference does not return the original cargo to its source.
        here=(person_site(game,npc) if npc else job['home'] if job['phase']=='handover'
            else job['leg']['origin'] if job['phase'] in {'outbound','homeward'} else job['location'])
        if npc and npc.alive and job['phase']!='handover':return '属员须先实际返回再交接'
    return reason(game,recovery=True) or ('须亲临原公物保管地点交接' if game.player.location_id!=here else '')

def promote_reason(game):
    s=state(game);office=s.get('office')
    return (reason(game,home=True) or restriction(game,'player') or ('请先正式任职' if not office else '')
        or ('主管须达到七品' if game.heavenly_court.get('player_grade',9)>7 else '')
        or ('须亲自完成本司两项差事' if s.get('completed',{}).get(office,0)<2 else '')
        or ('本司主管席位已有任职者' if s.get('heads',{}).get(office) not in {None,'player'} else ''))

def proposal(game,maps,offer,person):
    s=state(game);actor=game.player if person=='player' else find_person(game,person)
    blocked=reason(game) or restriction(game,person) or offer['reason']
    if not s.get('office') or s.get('office')!=offer['kind']:blocked=blocked or '须正式任职于本司'
    if s.get('leave'):blocked=blocked or '请先销假再承接新差事'
    travel=0;leg=None;home=None
    if person=='player':
        if occupied(game):blocked=blocked or '请先完成或退出本人已接受的事务'
    else:
        if s.get('heads',{}).get(s.get('office'))!='player' or game.heavenly_court.get('player_grade',9)>7:blocked=blocked or '须为七品及以上的本司主管'
        if s.get('staff',{}).get(person)!=s.get('office'):blocked=blocked or '此人未正式划入本司'
        blocked=blocked or officer_reason(game,actor)
        if not blocked and person_site(game,actor)!=offer['origin']:
            blocked='属员须与本人在原采购地点当面接收案卷与公物'
        if not blocked:
            home=person_site(game,actor)
            try:
                leg=runtime.route(maps,game,actor,home,offer['location'])
                back=runtime.route(maps,game,actor,offer['location'],home)
                travel=leg['years']+back['years']
            except ValueError as error:blocked=str(error)
    if offer.get('operation')=='rescue':
        travel+=offer['evacuation']['years']*(2 if person!='player' else 1)
        if person==offer['target']:blocked=blocked or '伤者不能兼任本案执行者'
        if actor and person!='player':
            try:runtime.route(maps,game,actor,offer['location'],offer['evacuation']['destination'])
            except ValueError as error:blocked=blocked or str(error)
    budget=offer['purchase']+offer['coins']+(offer['years']+travel+(5 if person!='player' else 0))*1000
    if actor and person!='player':
        from .economy.state import local_market
        market=local_market(game)
        if any(market['commodities'][k]['tier']>actor.realm_index+1 for k in offer['materials']):
            blocked=blocked or '属员本人修为不足以承办此阶公物'
    if offer['years']+travel+5>=500:blocked=blocked or '原行程无法在五百年案期内完成'
    if balance(game,COURT)<budget:blocked=blocked or '原天庭府库不足，不能无款承诺'
    value=reward(actor,offer['years']) if actor and actor.realm_index>=9 else Fraction(0)
    return dict(reason=blocked,budget=budget,leg=leg,home=home,reward=str(value),travel=travel)

def award(deps,game,job):
    s=state(game);total=Fraction(job['reward'])
    if job['person']!='player':
        official=game.heavenly_court['officials'][job['person']]
        official['service_merit']=str(Fraction(official.get('service_merit','0'))+total*9/10)
        total/=10
    prior=Fraction(s.get('merit_remainder','0'));whole=int(prior+total)
    s['merit_remainder']=str(prior+total-whole)
    adopt_merit(game)
    if whole:deps._add_court_merit(game,whole)
    if job['person']=='player':
        done=s.setdefault('completed',{});done[job['kind']]=done.get(job['kind'],0)+1
    return f'本次本人功德权益{float(total):g}，合并余量后入账{whole}。'

def command(deps,game,action,token,amount):
    if type(amount) is not int or amount!=1:raise ValueError('职司每次办理一项')
    parts=token.split('|',1) if isinstance(token,str) else []
    if not parts or parts[0]!=stamp(game):raise ValueError('职司记录已变化，请刷新后重试')
    target=parts[1] if len(parts)>1 else ''
    recovery=action in {'bureau_recall','bureau_handover','bureau_resign','bureau_release','bureau_cancel_review','bureau_case_cancel','bureau_abort_rescue'}
    if blocked:=reason(game,recovery=recovery):raise ValueError(blocked)
    s=state(game)
    if action.startswith('bureau_case_'):
        summary=inspection.command(game,action.removeprefix('bureau_'),target,occupied=occupied(game))
    elif action in {'bureau_fight','bureau_evacuate','bureau_divert','bureau_abort_rescue'}:
        identity,value=target.split('~',1) if '~' in target else (target,'')
        job=find(game,identity)
        if not job or job['status']!='active':raise ValueError('没有该在办公务')
        from . import court_enforcement as enforcement
        if game.player.age>=job['deadline'] and not recovery:raise ValueError('公务已逾期，请办理交接')
        if action=='bureau_abort_rescue':summary=enforcement.abort(game,deps.maps,job)
        elif action=='bureau_fight':summary=enforcement.fight(deps,game,job,value)
        elif action=='bureau_evacuate':summary=enforcement.evacuate(game,deps.maps,job)
        else:summary=projects.divert(game,job)
    elif action=='bureau_join':
        if target not in OFFICES:raise ValueError('未知职司')
        if blocked:=appointment_reason(game):raise ValueError(blocked)
        s=game.heavenly_court.setdefault('bureaus',{})
        if s.get('office')==target:raise ValueError('已在此司任职')
        old=s.get('office')
        s['staff']={k:v for k,v in s.get('staff',{}).items() if v!=old}
        if old:s.setdefault('heads',{}).pop(old,None)
        s.update(office=target,leave=False,appointed=game.player.age)
        summary='正式入职'+OFFICES[target]['name']+'；原官品、七曜和考核资历保留，旧司属员已交接。'
    elif action in {'bureau_resign','bureau_leave','bureau_resume','bureau_promote','bureau_appoint','bureau_release'}:
        if blocked:=reason(game,home=True,recovery=recovery):raise ValueError(blocked)
        if not s.get('office'):raise ValueError('尚未正式入职')
        office=s['office']
        if action=='bureau_promote':
            if blocked:=promote_reason(game):raise ValueError(blocked)
            s.setdefault('heads',{})[office]='player';summary='受任本司主管，最多调度两名正式属员。'
        elif action=='bureau_appoint':
            if blocked:=restriction(game,'player') or restriction(game,target):raise ValueError(blocked)
            if s.get('heads',{}).get(office)!='player' or game.heavenly_court['player_grade']>7:raise ValueError('须为本司七品及以上主管')
            staff=s.setdefault('staff',{})
            if target in staff or len(staff)>=2:raise ValueError('属员已任职或两席已满')
            npc=find_person(game,target)
            if blocked:=officer_reason(game,npc):raise ValueError(blocked)
            if person_site(game,npc)!=HOME:raise ValueError('须与原天官在玉京当面办理任命')
            staff[target]=office;record_appointment(game,npc,office);summary=npc.name+'正式划入本司，仍为原人物。'
        elif action=='bureau_release':
            if target not in s.get('staff',{}):raise ValueError('此人不是本司属员')
            if any(j['person']==target for j in active(game)):raise ValueError('须先返回并交接该属员的公务')
            s['staff'].pop(target);summary='解除本司任命，原人物及既得公务资历保留。'
        elif action=='bureau_resign':
            if active(game) or s.get('review') or inspection.active(game):raise ValueError('须先交接全部公务与公物')
            s.update(office=None,staff={});s.setdefault('heads',{}).pop(office,None);summary='已交接离任；原官品及七曜身份不变。'
        else:
            s['leave']=action=='bureau_leave';summary='请假期间不接新差事，旧承诺仍须完成或交接。' if s['leave'] else '已销假，可按原资格承接差事。'
    elif action=='bureau_accept':
        offered,person=target.split('~',1) if '~' in target else ('','')
        offer=next((o for o in projects.offers(game,deps.maps,s.get('office')) if o['token']==offered),None)
        if not offer:raise ValueError('原对象或采购报价已变化，请刷新后重试')
        plan=proposal(game,deps.maps,offer,person)
        if plan['reason']:raise ValueError(plan['reason'])
        if len(active(game))>=3:raise ValueError('本人一案及两名属员的在办名额已满')
        sequence=s.get('sequence',0)+1;s['sequence']=sequence;identity=f'bureau-{sequence}'
        job=dict(id=identity,kind=s['office'],person=person,name=offer['name'],origin=offer['origin'],location=offer['location'],
            place_name=deps.maps.location('celestial',offer['location'])['name'],offer=copy.deepcopy(offer),status='active',phase='work',
            years=offer['years'],progress=0,started=game.player.age,last_year=game.player.age,deadline=game.player.age+500,
            wallet='court-bureau:'+game.id+':'+identity,budget=plan['budget'],reward=plan['reward'],spent=0,home=plan['home'])
        if person!='player' and plan['leg']['origin']!=plan['leg']['destination']:job.update(phase='outbound',leg=plan['leg'])
        projects.reserve(game,job,offer,plan['budget'])
        s.setdefault('jobs',[]).append(job);s.setdefault('accepted',{})[offer['key']]=identity
        summary='已落实原府库预算与实际采购。'+('本人须亲赴现场履约。' if person=='player' else '原属员按实际道路与年度办理，不能同时同行、培养或再派遣。')
    elif action=='bureau_work':
        runtime.begin_work(game);return deps.advance(game.id,'court_service',1)
    elif action=='bureau_review':
        job=find(game,target)
        if not job or job['status']!='active' or job['phase']!='ready' or job['person']=='player':raise ValueError('须选择属员已完成的待验公务')
        if occupied(game):raise ValueError('请先结束本人当前事务')
        if game.player.age>=job['deadline']:raise ValueError('公务已逾期，请办理交接')
        if game.player.location_id!=job['location']:raise ValueError('须亲临交付地点复核')
        s['review']=dict(job=job['id'],progress=0,years=5);summary='开始5年实际核验；未完成前不领取主管功德。'
    elif action=='bureau_cancel_review':
        if not s.get('review'):raise ValueError('没有正在复核的公务')
        s.pop('review');summary='退出本人复核，属员案卷仍待验收，已耗年份不返还。'
    elif action=='bureau_claim':
        job=find(game,target)
        if not job or job['status']!='active' or job['phase']!='ready' or job.get('delivered'):raise ValueError('公务未完成或已交付')
        if game.player.age>=job['deadline']:raise ValueError('公务已逾期，请办理交接，不补发报酬')
        if job['person']!='player':
            review=s.get('review',{})
            if review.get('job')!=job['id'] or review['progress']<5:raise ValueError('须完成本人5年实际复核')
            npc=find_person(game,job['person'])
            if officer_reason(game,npc,assigned=True) or person_site(game,npc)!=job['location']:raise ValueError('原属员已离开交付现场或失去资格')
        elif job['progress']<job['years']:raise ValueError('实际公务工时不足')
        job['result']=projects.deliver(game,job);job['delivered']=True
        summary=job['result']+' '+award(deps,game,job)
        s.pop('review',None)
        if job['person']=='player':projects.close(game,job)
        else:runtime.recall(game,deps.maps,job)
    elif action in {'bureau_recall','bureau_handover'}:
        job=find(game,target)
        if not job or job['status']!='active':raise ValueError('没有该在办公务')
        if action=='bureau_recall' and job['person']!='player':
            runtime.recall(game,deps.maps,job);summary='已安排循原道路返程，未耗经费和公物随案保留，须当面交接。'
        else:
            if blocked:=handover_reason(game,job):raise ValueError(blocked)
            projects.close(game,job,cancel=not job.get('delivered'));s.pop('review',None)
            summary='未耗款退回原府库，剩余实物移交当地原市场；已耗费用不退，未完成不发功德。'
    else:raise ValueError('未知职司操作')
    s['last_result']=summary
    game.history.append(HistoryRecord('SYS_COURT_BUREAU',1,game.player.age,'天庭职司',action,'completed',summary,{},['court','bureau']))
    game.updated_at=now_iso();deps.store.save(game)
    return deps.present(game)

def public(game,maps):
    if not game.heavenly_court or not (enabled() or state(game)):return dict(available=False)
    s=state(game);office=s.get('office');offered=projects.offers(game,maps,office) if office else []
    actors=['player',*[k for k,v in s.get('staff',{}).items() if v==office]]
    for row in offered:row['executors']=[dict(id=k,name='本人' if k=='player' else (find_person(game,k).name if find_person(game,k) else '原人物已失效'),**proposal(game,maps,row,k)) for k in actors]
    staff=[]
    for identity,department in s.get('staff',{}).items():
        npc=find_person(game,identity);official=game.heavenly_court.get('officials',{}).get(identity,{})
        place=person_site(game,npc) if npc else None;place_name='位置不明'
        if maps and npc and place:
            try:place_name=maps.location(npc.world,place)['name']
            except ValueError:pass
        staff.append(dict(id=identity,name=npc.name if npc else '原人物已失效',office=department,
            location=place,location_name=place_name,merit=official.get('service_merit','0'),reason=officer_reason(game,npc)))
    rows=copy.deepcopy(active(game))
    for job in rows:
        job['remaining_cash']=balance(game,job['wallet']);job['person_name']='本人' if job['person']=='player' else (find_person(game,job['person']).name if find_person(game,job['person']) else '原人物已失效')
        job['expired']=game.player.age>=job['deadline']
        job['site_reason']='须亲临'+job['place_name']+'办理' if game.player.location_id!=job['location'] else ''
        job['handover_reason']=handover_reason(game,job)
        job['diversion_reason']=projects.diversion_reason(game,job)
        if job['offer'].get('operation'):
            from .court_enforcement import action_reason,abort_reason
            job['operation_reason']=action_reason(game,job)
            job['abort_reason']=abort_reason(game,maps,job)
    return dict(available=True,token=stamp(game),reason=reason(game),home_reason=reason(game,home=True),recovery_reason=reason(game,recovery=True),
        recovery_home_reason=reason(game,home=True,recovery=True),
        inspection=inspection.public(game,maps),restriction=restriction(game,'player'),
        office=office,offices=[dict(id=k,**v) for k,v in OFFICES.items()],leave=s.get('leave',False),
        supervisor=s.get('heads',{}).get(office)=='player',promote_reason=promote_reason(game),join_reason=appointment_reason(game),
        completed=s.get('completed',{}),remainder=s.get('merit_remainder','0'),staff=staff,candidates=local_officers(game),
        offers=offered,jobs=rows,review=copy.deepcopy(s.get('review')),work_reason=runtime.work_reason(game),
        history=[dict(id=j['id'],name=j['name'],receipt=j.get('receipt'),audited=j.get('audited')) for j in jobs(game) if j['status']=='closed'][-12:],
        last_result=s.get('last_result'),treasury=balance(game,COURT))
