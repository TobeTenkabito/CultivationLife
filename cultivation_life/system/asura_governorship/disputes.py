"""Six provincial disputes over original grants, funds, people and projects."""
import copy
from . import rules, politics
from .finance import bill, actor_for
from .. import institution_authority as authority, institution_petitions as petitions
from ..institution_ai import rules as agendas, runtime
from ..economy.ledger import balance
from ...relationship_records import find_person


def names():return politics.config().get('cases',{})


def qualified(game,row):
    return (authority.effective(game,row,row['holder']) and bool(row['holder'])
            and any(c['id']==row['city_id'] and rules.legal_city(game,c) for c in rules.cities(game)))


def completed(game,row):
    since=row['expires']-rules.config()['term_years']
    works=sum(h['status']=='completed' and h.get('closed',0)>=since for h in agendas.record(game,row['id']).get('history',[]))
    paid=sum(c['kind']=='remittance' and c['status']=='resolved' and c['decision'] in {'pay','half'}
             and c['closed']>=since
             for c in petitions.book(row).get('history',[]))
    return works+paid


def offers(game,row):
    if not politics.enabled() or not qualified(game,row):return []
    result=[];building=rules.building(game,row);cash=balance(game,row['wallet']);reserve=0
    if not building or building['status']=='destroyed':
        try:q=bill(game,row)
        except ValueError:q=None
        if q:
            reserve=q['total']
            if q['reason']=='本府公款不足，须先拨款或资助':
                result.append(('budget',dict(target=row['building_id'],amount=q['total']-cash,total=q['total'],
                    source='原址营造报价与本府公账',description='申请补齐原府署工料预算；拨款不直接完成建筑。')))
    if cash>0:
        result.append(('remittance',dict(amount=max(1,cash//10),reserve=reserve,
            source='原本府公款余额',description='王庭请求上缴本府实款一成；可据未完工程保留必要准备金。')))
    record=agendas.record(game,row['id']);job=record.get('job')
    if job and job.get('blocked'):
        result.append(('performance',dict(target=job['id'],spent=job['spent'],deadline=job['deadline'],
            source='原项目履约回执',description=job['blocked'])))
    if not building or building['status']!='intact':return result
    candidates=rules.eligible_people(game,row)
    if not row['people'] and candidates and not job:
        ordered=sorted(candidates,key=lambda n:(-max(politics.state(game).get('people',{}).get(n['id'],{}).get('bonds',{}).get(row['holder'],0),0),n['id']))
        result.append(('personnel',dict(candidate=ordered[0]['id'],candidate_name=ordered[0]['name'],
            alternative=ordered[1]['id'] if len(ordered)>1 else None,
            alternative_name=ordered[1]['name'] if len(ordered)>1 else None,
            source='原址自由人员名册',description='举荐原人物为地方执事，仍须通过任职与任务占用核验。')))
    result.append(('access',dict(target=building['id'],public=building['public'],
        source='原公署公开使用许可',description='城盟主张开放办事，军府主张限制来客；只调整府署公开权，不改产权。')))
    if 0<row['expires']-game.player.age<=politics.config()['renewal_window']:
        result.append(('tenure',dict(expires=row['expires'],completed=completed(game,row),
            source='原任期与真实履约记录',description='续任须至少一项实际完工或实款上缴；原任期届满前裁定。')))
    return result


def witnesses(game,row,kind,evidence):
    result=[]
    for p in rules.eligible_people(game,row)[:3]:
        group,basis=politics.faction(game,p['id']);choice=politics.preference(game,p['id'],kind,evidence)
        result.append(dict(id=p['id'],name=p['name'],faction=group,choice=choice,reason=politics.config()['factions'][group]['interest']+'；'+basis))
    return result


def observe(game,row):
    now=game.player.age;count=0
    if now<row['appointed'] or any(h['year']>now for h in row['history']):return 0
    for kind,evidence in offers(game,row):
        deadline=now+politics.config()['deadline_years']
        if kind=='tenure':deadline=min(deadline,row['expires'])
        if petitions.open_case(row,kind=kind,period=now//politics.config()['period_years'],now=now,
                deadline=deadline,actor=row['holder'],evidence=evidence,witnesses=witnesses(game,row,kind,evidence)):
            count+=1
    if count:authority.log(game,row,f'根据原账目与人员受理 {count} 项地方事项；提案未移动人物或款物。')
    return count


def invalid(game,row,case):
    if not qualified(game,row) or row['holder']!=case['actor']:return '原任职或城市许可已变化，保留案卷等待交接'
    kind,e=case['kind'],case['evidence'];b=rules.building(game,row)
    if b and (b['owner']!=row['owner'] or b['address']!=dict(world=row['world'],location_id=row['location'],instance_id=None)):
        return '原府署产权或地址已变化，须重新核验职责'
    if kind=='budget':
        if b and b['status']!='destroyed':return '原府署已恢复，不再需要该营造拨款'
        if balance(game,row['wallet'])>=e['total']:return '本府已筹足原申请预算，无须重复拨款'
    elif kind=='personnel':
        if row['people']:return '原执事职位已有人任职'
    elif kind=='performance':
        job=agendas.record(game,row['id']).get('job')
        if not job or job['id']!=e['target']:return '原项目已结项或交接，不再处置旧任务'
    elif kind=='tenure' and row['expires']!=e['expires']:return '原任期已经变更，不得重复续任'
    if kind not in {'budget','remittance','performance'} and (not b or b['status']!='intact' or b['owner']!=row['owner']):
        return '原府署不可用或产权改变，须先恢复办事条件'
    return ''


def choices(game,row,case,*,spending_limit=None):
    kind,e=case['kind'],case['evidence'];cash=balance(game,row['wallet']);common=invalid(game,row,case)
    if game.player.age<case['opened']:common='历史补算不得提前裁定尚未提出的原案'
    def choice(identity,name,reason='',cost=0,priority=50):
        return dict(id=identity,name=name,reason=common or reason,cost=cost,priority=priority)
    if kind in {'budget','tenure'}:
        if case['status']=='open':
            options=[choice('submit','呈交王庭',priority=90)]
            if kind=='tenure':options.append(choice('retire','按期交接辞任',priority=10))
            return options
        amount=min(e['amount'],max(0,e['total']-cash)) if kind=='budget' else 0
        if kind=='budget' and spending_limit is not None:amount=min(amount,spending_limit)
        reason=('王庭原府库不足或本期拨款额度已用尽' if amount<1 or balance(game,rules.SOURCE)<amount else '') if kind=='budget' else ('尚无实际完工或实款上缴凭据' if completed(game,row)<1 else '')
        return [choice('approve',f'批准拨款 {amount:,}' if kind=='budget' else '批准续任',reason,amount,90),
                choice('reject','驳回请示',priority=10)]
    if kind=='remittance':
        # Re-evaluate the original construction reserve; the saved claim is not a purse.
        reserve=e['reserve'];b=rules.building(game,row)
        if b and b['status']=='intact':reserve=0
        return [choice(k,label,'实款不足或将侵占原工程准备金' if cash-n<reserve or cash<n else '',n,score)
                for k,label,n,score in [('pay','照额上缴',e['amount'],60),('half','折半实缴',max(1,e['amount']//2),55)]]+[choice('retain','保留本府准备金',priority=50)]
    if kind=='personnel':
        available={p['id'] for p in rules.eligible_people(game,row)}
        options=[choice('appoint','任用 '+e['candidate_name'],'' if e['candidate'] in available else '原人选已离场、受拘束或被占用',priority=80)]
        if e.get('alternative'):options.append(choice('alternative','改任 '+e['alternative_name'],'' if e['alternative'] in available else '原备选已不具备资格',priority=70))
        return options+[choice('decline','暂缓任用',priority=10)]
    if kind=='performance':return [choice('continue','保留原任务与截止年',priority=60),choice('cancel','交接项目并退原余款',priority=65)]
    if kind=='access':return [choice('open','向公众开放',priority=65),choice('restrict','限原任职人办事',priority=60)]
    raise ValueError('未知地方争议类型')


def finish(game,row,case,decision,status,result,actor):
    petitions.close(row,case,now=game.player.age,status=status,decision=decision,result=result)
    politics.outcome(game,row,case,decision,actor=actor)
    authority.log(game,row,f'{names().get(case["kind"],case["kind"])}：{result}')


def resolve(game,row,case,decision,actor,*,spending_limit=None):
    option=next((o for o in choices(game,row,case,spending_limit=spending_limit) if o['id']==decision),None)
    if not option:raise ValueError('当前案卷没有这项裁决')
    if option['reason']:raise ValueError(option['reason'])
    kind,e=case['kind'],case['evidence']
    if decision=='submit':
        petitions.submit(row,case)
        authority.log(game,row,'原案已具名呈交王庭；期限、原款和原任务保持。')
        return
    result='';status='resolved'
    if decision=='reject':status='rejected';result='王庭驳回本次请示，未扣款，原职责与期限继续。'
    elif kind=='budget':
        authority.fund(game,row,rules.SOURCE,option['cost']);case['evidence']['paid']=option['cost']
        remaining=max(0,e['total']-balance(game,row['wallet']))
        result=f'原王庭实拨 {option["cost"]:,} 灵石进入本府；原申请尚待筹 {remaining:,}，工程另行营造。'
    elif kind=='remittance':
        if decision!='retain':authority.remit(game,row,option['cost'])
        result=f'本次实际上缴 {option["cost"]:,} 灵石，余款留原本府。'
    elif kind=='personnel':
        if decision!='decline':
            person=e['candidate'] if decision=='appoint' else e['alternative']
            authority.set_staff(game,row,person);politics.appointment(game,person,actor,'staff',case['id'])
            result='原人物受任，后续预算、占用与履约沿原机构系统。'
        else:result='暂缓任用，原人选保持自由，不预占名额。'
    elif kind=='performance':
        agenda=agendas.record(game,row['id'])
        if decision=='cancel':runtime.close(game,None,agenda,agenda['job'],'cancelled','地方争议依法交接，已耗工时保留，原余款退本府。')
        result='原项目交接，未耗原款退回本府。' if decision=='cancel' else '保留原任务，未清除阻碍、补工时或延长截止年。'
    elif kind=='access':
        from ..building_projects import set_public
        set_public(game,rules.building(game,row),decision=='open',actor=actor_for(row))
        result='原府署已向公众开放。' if decision=='open' else '原府署停止公开访问，原任职许可与王庭产权保留。'
    elif kind=='tenure':
        if decision=='retire':authority.relinquish(game,row,actor);result='原任已交接，公产、公款及案卷留府。'
        else:row['expires']+=rules.config()['term_years'];result=f'原任期续至 {row["expires"]} 年，公款及责任未重置。'
    finish(game,row,case,decision,status,result,actor)


def command(game,row,payload):
    action=payload.get('operation');identity=payload.get('case');decision=payload.get('choice')
    if not isinstance(action,str) or any(v is not None and not isinstance(v,str) for v in (identity,decision)):
        raise ValueError('地方议事请求格式无效')
    local=rules.local(game,row)
    mine=local and authority.effective(game,row)
    capital=game.player.location_id=='ten_thousand_battle_city'
    if action=='observe':
        if not politics.enabled() or not mine:raise ValueError('须由在任总督于原址受理')
        observe(game,row);return
    if action=='withdraw':
        case=next((c for c in petitions.book(row).get('active',[]) if c['id']==identity),None)
        if not case or not local or 'player' not in (row['holder'],row['controller'],row['nominee']):
            raise ValueError('须由原任在原址交接原案')
        finish(game,row,case,'withdraw','withdrawn','原任撤回原案；承诺与已耗款物保留履历。','player');return
    if not politics.enabled():raise ValueError('修罗DLC停用，仅可交接原案')
    case=petitions.find(row,identity,game.player.age)
    central=case['status']=='submitted' and case['kind'] in {'budget','tenure'}
    if action=='endorse':
        if not ((central and capital) or mine):raise ValueError('须亲临原案议事机关担保')
        if decision not in {o['id'] for o in choices(game,row,case)}:raise ValueError('担保须指明当前实际裁决')
        petitions.endorse(row,case,'player',decision);return
    if action!='resolve' or not ((central and capital and rules.king(game)) or (not central and mine)):
        raise ValueError('没有此案的当前裁决权限')
    resolve(game,row,case,decision,'player')


def advance(game,row):
    now=game.player.age
    if now<row['appointed'] or any(h['year']>now for h in row['history']):return
    if not petitions.book(row) and not (politics.enabled() and qualified(game,row)):return
    book=petitions.ensure(row)
    if book.get('last_tick',-1)>=now:return
    book['last_tick']=now
    for case in list(petitions.book(row).get('active',[])):
        if now>=case['deadline']:
            finish(game,row,case,'expire','expired','原案逾期归档，未自动付钱、续任或虚构交付。',case['actor'])
        elif case['kind']=='performance':
            job=agendas.record(game,row['id']).get('job')
            if not job or job['id']!=case['evidence']['target']:
                finish(game,row,case,'obsolete','obsolete','原项目已结项或依法交接，旧案归档，不重复退款或追罚。',case['actor'])
        elif case['kind']=='budget':
            building=rules.building(game,row)
            if (building and building['status']=='intact') or balance(game,row['wallet'])>=case['evidence']['total']:
                finish(game,row,case,'obsolete','obsolete','原工程或资金缺口已解决，旧请款归档，不再重复拨款或追罚。',case['actor'])
    if not politics.enabled():return
    from ...regional_context import historical
    if (row['holder']=='player' and qualified(game,row) and rules.local(game,row)
            and not historical(game) and not game.pending_event and not game.active_trial
            and not game.map_journey and not game.guixu_state.get('player_session') and not game.trial_site_state.get('active')):
        observe(game,row)
    if row['holder'] and row['holder']!='player' and qualified(game,row):
        if not agendas.person_reason(game,row['holder'],row['world'],row['location']):
            observe(game,row)
            for case in list(petitions.book(row).get('active',[])):
                if case['status']!='open':continue
                decision=petitions.choose(choices(game,row,case),budget=balance(game,row['wallet'])//10,
                    preferred=politics.preference(game,row['holder'],case['kind'],case['evidence']))
                if decision:resolve(game,row,case,decision,row['holder'])
    king=rules.court(game)['court']['holders'].get('5')
    if not king or king=='player' or agendas.person_reason(game,king,'asura','ten_thousand_battle_city'):return
    # Every approval debits the same treasury; subsequent proposals see its new balance.
    for case in list(petitions.book(row).get('active',[])):
        if case['status']!='submitted':continue
        budget=int(balance(game,rules.SOURCE)*politics.config()['npc_budget_fraction'])
        decision=petitions.choose(choices(game,row,case,spending_limit=budget),budget=budget,
            preferred=politics.preference(game,king,case['kind'],case['evidence']))
        if decision:resolve(game,row,case,decision,king,spending_limit=budget)


def public(game,row):
    local=rules.local(game,row);mine='player' in (row['holder'],row['nominee'],row['controller'])
    capital=game.player.location_id=='ten_thousand_battle_city'
    known=local and mine;central=capital and rules.court(game).get('joined')
    if not (known or central):return None
    active=[]
    for case in petitions.book(row).get('active',[]):
        submitted=case['status']=='submitted' and case['kind'] in {'budget','tenure'}
        if not known and not submitted:continue
        item=copy.deepcopy(case)
        item.update(name=names().get(case['kind'],case['kind']),can_decide=politics.enabled() and
            ((submitted and capital and rules.king(game)) or (not submitted and known and authority.effective(game,row))),
            can_endorse=politics.enabled() and not case['pledge'] and now_valid(game,case)
                and not (case['kind'] in {'budget','tenure'} and case['status']=='open'),
            can_withdraw=known,choices=choices(game,row,case) if politics.enabled() else [])
        if not now_valid(game,case):
            item.update(can_decide=False,can_endorse=False)
        active.append(item)
    return dict(active=active,history=copy.deepcopy(petitions.book(row).get('history',[])[-6:]) if known else [],
                can_observe=politics.enabled() and known and authority.effective(game,row))


def now_valid(game,case):return game.player.age<case['deadline']
