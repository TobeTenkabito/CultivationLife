"""Evidence, defence, independent review and limited executable accountability."""
import copy
from ..relationship_records import find_person
from ..rules import remove_item
from .court_bureau_rules import state, reason, HOME, COURT, digest, officer_reason
from .court_case_facts import leads, facts, source, relation, restriction
from .faction_geography import person_site
from .economy.ledger import balance, transfer_value, account
from .economy.state import local_market, reprice

STEPS={'accounts':'核验原账与货单','site':'现场查验','hearing':'受理申辩与核对行程'}
VERDICTS={'remedy':'补交后结案','suspend':'停止经办资格五百年','recuse':'回避并交接该项任命','clear':'证据不足／客观阻碍结案'}
DEFENCES={'emergency':'说明有凭据的应急改拨','obstruction':'说明有凭据的客观阻碍','acknowledge':'登记已知事实，暂无补充说明'}

def active(game):return next((c for c in state(game).get('inquiries',[]) if c['status']=='active'),None)

def current_work(game):
    c=active(game)
    return c.get('work') if c else None

def reviewer_reason(game,c,npc,*,assigned=False):
    if not npc or npc.id==c['subject'] or npc.id in c.get('prior_reviewers',[]) or relation(game,npc.id):return '复核人须独立于当事人、原复核人及本人亲属师承'
    if npc.id in state(game).get('staff',{}):return '本司直属属员不得独立复核本司案件'
    if blocked:=restriction(game,npc.id):return blocked
    if blocked:=officer_reason(game,npc,assigned=assigned):return blocked
    if person_site(game,npc)!=HOME:return '复核人须实际在玉京'
    return ''

def work_reason(game):
    c=active(game);w=current_work(game)
    if not c or not w:return '请先选择取证步骤或独立复核人'
    if blocked:=reason(game):return blocked
    if game.player.location_id!=w['location']:return '须亲临本段取证或复核地点'
    if w['key']=='review':
        if blocked:=reviewer_reason(game,c,find_person(game,c['reviewer']),assigned=True):return blocked
    return ''

def finish(game,elapsed):
    c=active(game);w=current_work(game)
    if not w:return
    w['progress']+=elapsed;c['spent']+=elapsed*1000
    transfer_value(game,c['wallet'],'background:celestial',elapsed*1000,'监察实际取证与复核劳务')
    if w['progress']>=w['years']:
        if w['key']=='review':
            c['reviewed']=digest(facts(game,c));c['stage']='execute'
        else:
            c['evidence'][w['key']]=dict(age=game.player.age,facts=copy.deepcopy(facts(game,c)))
            if w['key']=='hearing':
                npc=find_person(game,c['subject'])
                present=c['subject']=='player' or bool(npc and npc.alive and npc.world=='celestial' and person_site(game,npc)==HOME)
                c['evidence'][w['key']]['attendance']='实际到场' if present else '当事人缺席，仅核原记录，不虚构口供'
            c['stage']='decision' if len(c['evidence'])==3 else 'evidence'
        c.pop('work')

def verdict_reason(game,c,key):
    f=facts(game,c)
    if key not in VERDICTS:return '未知裁定'
    if key=='clear' and f['fault']:return '仍有未交代事实，不能直接认定无责'
    if key=='remedy' and (f['owed'] or f.get('difference')):return '须先补交实际短缺；来源未明的账差不能凭空核销'
    if key=='remedy' and c['kind']!='procurement':return '补交结案只适用于采购案'
    if key=='recuse' and c['kind']!='conflict':return '本案不涉及任命回避'
    if key=='suspend' and (not f['fault'] or f.get('missing')):return '没有足够履约事实支持停止经办资格'
    if key in {'suspend','recuse'}:
        identities={c['subject']}
        if c['kind']=='conflict':identities.add(f.get('person'))
        if any(j['status']=='active' and j['person'] in identities for j in state(game).get('jobs',[])):
            return '当事人须先真实返程并交接在办公务，不能借处分瞬移或释放公物'
    return ''

def restitution_reason(game,c):
    f=facts(game,c);row=source(game,c)
    if not f['owed'] or not row:return '没有来源明确的待补实物'
    if game.player.location_id!=row['location']:return '须到原合同交付地点补交'
    held={i.id:i.quantity for i in game.player.inventory}
    if any(held.get(k,0)<n for k,n in f['owed'].items()):return '本人行囊缺少所欠实物；不能用原公款替个人赔补'
    market=local_market(game)
    if not market or any(k not in market['commodities'] for k in f['owed']):return '原交付市场无法接收'
    return ''

def close(game,c,result):
    refund=balance(game,c['wallet']);transfer_value(game,c['wallet'],COURT,refund,'监察余款归还原府库')
    c['refunded_total']=c.get('refunded_total',0)+refund
    c.update(status='closed',stage='closed',closed=game.player.age,result=result,refund=refund)
    c.pop('work',None)

def command(game,action,target,*,occupied):
    s=state(game);parts=target.split('~',1);identity=parts[0];value=parts[1] if len(parts)>1 else ''
    c=next((c for c in s.get('inquiries',[]) if c['id']==identity),None)
    if action=='case_open':
        if blocked:=reason(game,home=True):raise ValueError(blocked)
        if s.get('office')!='audit' or s.get('leave'):raise ValueError('须在御史台正式在职')
        if occupied:raise ValueError('请先交接本人当前事务')
        row=next((r for r in leads(game) if r['token']==identity),None)
        if not row:raise ValueError('原线索已变化，请刷新')
        if balance(game,COURT)<25000:raise ValueError('原府库不足以承担取证与复核预算')
        sequence=s.get('case_sequence',0)+1;s['case_sequence']=sequence
        c=dict(copy.deepcopy(row),id='inquiry-'+str(sequence),status='active',stage='evidence',
            evidence={},defence='',started=game.player.age,spent=0,reviewer=None,prior_reviewers=[],appealed=False,
            wallet=f'court-bureau:{game.id}:inquiry-{sequence}',budget=25000,funded=25000,refunded_total=0)
        c.pop('token',None);account(game,c['wallet']);transfer_value(game,COURT,c['wallet'],25000,'监察预算原款托管')
        s.setdefault('inquiries',[]).append(c);return '已据原凭据立案；调查不预设有罪。'
    if not c:raise ValueError('没有该案卷')
    if action=='case_resume':
        if blocked:=reason(game,home=True):raise ValueError(blocked)
        if c['status']!='paused' or occupied or s.get('office')!='audit':raise ValueError('须在御史台空出本人事务后续查原案')
        remaining=c['budget']-c['spent']
        if balance(game,COURT)<remaining:raise ValueError('原府库不足以续办剩余调查')
        if c.get('reviewer') and reviewer_reason(game,c,find_person(game,c['reviewer'])):
            c['prior_reviewers'].append(c['reviewer']);c.update(stage='decision',reviewer=None)
            c.pop('work',None);c.pop('reviewed',None)
        transfer_value(game,COURT,c['wallet'],remaining,'原监察案续办剩余预算');c['funded']+=remaining;c['status']='active';c['refund']=0
        c.pop('result',None)
        return '续办原案，已耗年份、证据和工时保留，不另建案卷。'
    if action=='case_appeal':
        if blocked:=reason(game,home=True):raise ValueError(blocked)
        if c['status']=='paused':raise ValueError('须先续查原案，再申请独立复核')
        if c['appealed'] or not c.get('reviewed') or c['stage'] not in {'execute','closed'}:raise ValueError('本案只能在初审完成后申诉一次')
        if active(game) not in (None,c) or (c['status']!='active' and occupied):raise ValueError('请先结束本人当前事务')
        if c['status']=='closed':
            if balance(game,COURT)<5000:raise ValueError('原府库不足以承担复核')
            transfer_value(game,COURT,c['wallet'],5000,'监察申诉复核预算');c['budget']+=5000;c['funded']+=5000
        c['prior_reviewers'].append(c['reviewer']);c.update(status='active',stage='decision',appealed=True,reviewer=None)
        c.pop('reviewed',None);return '申诉已受理，保留原证据和既有赔补；须由另一名独立天官重新复核。'
    if c['status']!='active':raise ValueError('本案已经结案')
    if action=='case_cancel':
        refund=balance(game,c['wallet']);transfer_value(game,c['wallet'],COURT,refund,'暂缓监察，余款退回原府库')
        c['refunded_total']=c.get('refunded_total',0)+refund
        c.update(status='paused',refund=refund,result='暂缓调查，原责任、实物去向和已做工时保留')
        return c['result']
    if blocked:=reason(game):raise ValueError(blocked)
    if action=='case_reassign':
        if game.player.location_id!=HOME or c['stage'] not in {'review','execute'}:raise ValueError('须在玉京办理复核交接')
        if not reviewer_reason(game,c,find_person(game,c.get('reviewer')),assigned=True):raise ValueError('原复核人仍可履职，不得借更换重抽结论')
        c['prior_reviewers'].append(c['reviewer']);c.update(stage='decision',reviewer=None)
        c.pop('work',None);c.pop('reviewed',None);return '失效复核已交接；既有劳务不退，新复核人须重新核满五年。'
    if action=='case_step':
        if c.get('work') or value not in STEPS or value in c['evidence']:raise ValueError('该步骤无效或已有工时正在办理')
        location=c['location'] if value=='site' else HOME
        if game.player.location_id!=location:raise ValueError('须亲临本段取证地点')
        c['work']=dict(key=value,location=location,years=5,progress=0);return '已开始'+STEPS[value]+'，须实际办理五年。'
    if action=='case_defend':
        if value not in DEFENCES or c.get('work') or c['stage'] not in {'evidence','decision'}:raise ValueError('当前不能提交此申辩')
        if game.player.location_id!=HOME:raise ValueError('须在玉京受理申辩')
        f=facts(game,c)
        if value=='emergency' and not f.get('emergency'):raise ValueError('没有原应急短缺与改拨记录支持此说明')
        if value=='obstruction' and not f.get('excused'):raise ValueError('原交接记录没有客观阻碍')
        c['defence']=value;return '申辩已入卷；应急用途不能代替原合同补交，也不凭说明自动免责。'
    if action=='case_propose':
        if c['stage']!='decision' or not c['defence']:raise ValueError('须完成三步取证并登记申辩或当事人说明')
        if blocked:=verdict_reason(game,c,value):raise ValueError(blocked)
        c['proposed']=value;return '拟定'+VERDICTS[value]+'，尚未执行，须独立复核。'
    if action=='case_reviewer':
        if c['stage']!='decision' or not c.get('proposed'):raise ValueError('须先提出有事实支持的处理意见')
        if game.player.location_id!=HOME:raise ValueError('须在玉京当面复核')
        if blocked:=reviewer_reason(game,c,find_person(game,value)):raise ValueError(blocked)
        extra=max(0,5000-balance(game,c['wallet']))
        if balance(game,COURT)<extra:raise ValueError('原府库不足以承担补充复核工时')
        if extra:
            transfer_value(game,COURT,c['wallet'],extra,'失效复核交接后的实际预算补足');c['budget']+=extra;c['funded']+=extra
        c['reviewer']=value;c['work']=dict(key='review',location=HOME,years=5,progress=0)
        c['stage']='review';return '独立天官已接卷，须共同办理五年复核；该原人物暂被占用。'
    if action=='case_restitution':
        if blocked:=restitution_reason(game,c):raise ValueError(blocked)
        row=source(game,c);market=local_market(game)
        for key,n in facts(game,c)['owed'].items():
            remove_item(game.player,key,n);product=market['commodities'][key];product['stock']+=n;reprice(game,market,product)
            row.setdefault('restitution',{})[key]=row.get('restitution',{}).get(key,0)+n
        return '所欠实物已从本人行囊补入原交付市场，凭据保留；没有另发货款。'
    if action=='case_execute':
        if c['stage']!='execute' or game.player.location_id!=HOME:raise ValueError('须完成独立复核并在玉京执行')
        if blocked:=reviewer_reason(game,c,find_person(game,c['reviewer']),assigned=True):raise ValueError(blocked)
        if c.get('reviewed')!=digest(facts(game,c)):raise ValueError('事实已变化，须申诉重新复核后执行')
        key=c['proposed']
        if blocked:=verdict_reason(game,c,key):raise ValueError(blocked)
        restrictions=s.setdefault('restrictions',{})
        if key=='suspend':
            restrictions[c['subject']]=dict(case=c['id'],until=game.player.age+500)
            if c['subject']=='player':s['heads']={k:v for k,v in s.get('heads',{}).items() if v!='player'}
            else:s.get('staff',{}).pop(c['subject'],None)
        elif key=='recuse':s.get('staff',{}).pop(facts(game,c)['person'],None)
        elif restrictions.get(c['subject'],{}).get('case')==c['id']:
            restrictions.pop(c['subject'])
        close(game,c,VERDICTS[key]+'；原官品、七曜和通缉权限仍按原制度。')
        return c['result']
    raise ValueError('未知监察动作')

def public(game,maps):
    s=state(game);c=active(game);rows=[]
    if game.player.world!='celestial':
        return dict(leads=[],cases=[],steps=STEPS,defences=DEFENCES,active=None,location=game.player.location_id,home=HOME,
            work_reason='须返回仙界核验原案',notice='跨界情报未核实，请返回仙界查看原案及在场复核人。')
    visible=[c for c in s.get('inquiries',[]) if c['status']!='closed']+[c for c in s.get('inquiries',[]) if c['status']=='closed'][-12:]
    for original in visible:
        row=copy.deepcopy(original);row['facts']=facts(game,original)
        row['place_name']=maps.location('celestial',row['location'])['name'] if maps else '原案发地点'
        row['restitution_reason']=restitution_reason(game,original)
        reviewer=find_person(game,original.get('reviewer')) if original.get('reviewer') else None
        row['reviewer_name']=reviewer.name if reviewer else '尚未指定／原人物已失效'
        row['reviewer_reason']=reviewer_reason(game,original,find_person(game,original.get('reviewer')),assigned=True) if original.get('reviewer') and game.player.location_id==HOME else ''
        row['verdicts']=[dict(id=k,name=v,reason=verdict_reason(game,original,k)) for k,v in VERDICTS.items()]
        row['reviewers']=[dict(id=k,name=n.name,reason=reviewer_reason(game,original,n))
            for k in game.heavenly_court.get('officials',{}) if game.player.location_id==HOME and (n:=find_person(game,k)) and n.world=='celestial' and person_site(game,n)==HOME]
        rows.append(row)
    return dict(leads=leads(game),cases=rows,steps=STEPS,defences=DEFENCES,active=c['id'] if c else None,
        location=game.player.location_id,home=HOME,work_reason=work_reason(game))
