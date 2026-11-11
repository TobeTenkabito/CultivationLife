"""Asura petitions, patronage and evidenced accountability over base casework."""
from . import rules,politics
from .. import institution_authority as authority,institution_deliberation as council
from ..institution_ai.rules import person_reason
from ..economy.ledger import balance,transfer_value
from ...relationship_records import find_person

CAPITAL='ten_thousand_battle_city'


def king(game):return rules.court(game)['court']['holders'].get('5')


def royal_audience(game):
    if game.player.location_id!=CAPITAL:raise ValueError('须亲赴万战城呈交王庭')
    k=king(game)
    if k!='player' and (not k or person_reason(game,k,'asura',CAPITAL)):raise ValueError('原君主不在王庭或无法听议')
    return k


def local(game,row,*,active=True):
    if not rules.local(game,row) or (not authority.effective(game,row) if active else row['controller']!='player'):
        raise ValueError('须由原总督在本府办理')


def active_case(row,payload,kind=None):
    c=council.find(row,payload.get('case'))
    if kind and c['kind']!=kind:raise ValueError('所选原案类型不符')
    return c


def command(game,row,op,p):
    cfg=rules.config().get('completion',{});amount=p.get('amount',0)
    if type(amount) is not int or not 0<=amount<=10**15:raise ValueError('金额须为有效整数')
    if op=='pressure':
        local(game,row)
        required=sum(u['rate'] for u in row.get('garrison',{}).get('units',[]) if u['phase'] not in {'home','lost'})*30
        from .finance import bill
        if not rules.building(game,row) or rules.building(game,row)['status']!='intact':required+=bill(game,row)['total']
        deficit=max(0,required-balance(game,row['wallet']))
        if not 1<=amount<=deficit:raise ValueError('联合请款须有原工程或三十年守备的实际缺口')
        c=council.open_case(row,'pressure','player',king(game),game.player.age,amount=amount,facts=dict(deficit=deficit))
        eligible=[n['id'] for n in rules.eligible_people(game,row)]
        signatures=council.cosign([dict(key=c['id'],category='supply',urgency=80,budget=0,reason='')],eligible,'supply',0)
        c['participants']+=signatures.get(c['id'],[])[:3]
        if len(c['participants'])<3:raise ValueError('须有至少两名原址自由修士联署，不能虚构派系代表')
        text='原工程与守备缺口已形成具名联合请款，可亲赴王庭呈议。'
    elif op=='pressure_decide':
        c=active_case(row,p,'pressure');k=royal_audience(game)
        if c['subject']!=k:raise ValueError('原受呈君主已更替，须交接旧案')
        if not authority.effective(game,row,c['actor']):raise ValueError('原呈案人的在任授权已经失效')
        if c['deadline']<=game.player.age:raise ValueError('原联合呈案已逾期')
        choice=p.get('choice')
        if k!='player':
            if c['actor']!='player':raise ValueError('须由原呈案人当面交涉')
            choice=council.decide([dict(id='approve',cost=c['amount'],priority=80),dict(id='reject',cost=0,priority=30)],budget=balance(game,row['source'])//10)
        if choice=='approve':
            authority.fund(game,row,row['source'],c['amount']);c['paid']=c['amount']
            for n in c['participants']:politics.remember(game,n,k,3,'具名联合请款已实拨',c['id'])
        elif choice!='reject':raise ValueError('请选择批准或驳回')
        council.close(row,c,'fulfilled' if choice=='approve' else 'rejected','联合呈案已依实际府库裁决。');text=c['result']
    elif op=='patronage':
        identity=p.get('person');n=find_person(game,identity)
        if not n or n.id==king(game) or n.faction_id!=rules.COURT or person_reason(game,n.id,'asura',game.player.location_id):raise ValueError('须与原在场自由廷臣交涉')
        group=p.get('choice')
        if group not in politics.config()['factions']:raise ValueError('请选择原三派中的议政立场')
        previous=[c for c in council.book(row)['history'] if c['kind']=='patronage' and c['subject']==identity]
        alignment=politics.state(game).get('people',{}).get(identity,{}).get('alignment')
        if alignment and game.player.age<alignment['since']+cfg['political_interval']:raise ValueError('此人本轮已经转投，跨府交涉也不刷新冷却')
        if previous and game.player.age<previous[-1]['opened']+cfg['political_interval']:raise ValueError('此人本轮已经交涉，不能反复改押')
        bond=politics.state(game).get('people',{}).get(identity,{}).get('bonds',{}).get('player',0)
        choice=council.decide([dict(id='accept',priority=bond+30,reason='' if bond>=12 else '尚无可信履约'),dict(id='decline',priority=40)],budget=0)
        c=council.open_case(row,'patronage','player',identity,game.player.age,facts=dict(group=group,previous=politics.faction(game,identity)[0]))
        if choice=='accept':
            politics.remember(game,identity,'player',2,'具名转投议政立场',c['id'])
            record=politics.state(game)['people'][identity]
            record['alignment']=dict(group=group,patron='player',since=game.player.age)
        council.close(row,c,'fulfilled' if choice=='accept' else 'rejected','原廷臣接受转投，公职与私人支持仍分别结算。' if choice=='accept' else '原廷臣拒绝转投；没有付款或强改其身份。');text=c['result']
    elif op=='divert':
        local(game,row)
        if amount<1:raise ValueError('须明确拟侵吞的原公款金额')
        c=council.open_case(row,'audit','player','player',game.player.age,amount=amount,facts=dict(cause='diversion',source=row['wallet'],beneficiary=game.id,suspends_authority=True))
        transfer_value(game,row['wallet'],'player',amount,'具名侵吞公款，原转移凭证与追偿责任保留')
        text='已将原公款转入个人；这是可追偿的侵吞，撤任、迁署与停用不会清除责任。'
    elif op=='audit_open':
        if not rules.king(game) or royal_audience(game)!='player':raise ValueError('须由现君在王庭立案')
        if any(c['kind']=='audit' for c in council.book(row)['cases']):raise ValueError('已有原监察案，继续原案调查')
        order=row.get('asura_military',{}).get('order')
        if not order or order['status']!='refused' or order['issuer']!=king(game) or order['recipient']!=row['controller']:raise ValueError('没有当前原任的具名抗命凭据，不能凭空定罪')
        council.open_case(row,'audit','player',row['controller'],game.player.age,facts=dict(cause='order',order=order['id'],issuer=order['issuer'],unjustified=order.get('refusal_evidence',{}).get('unjustified',False)))
        text='原抗命文书立案；守备缺口和申辩将在调查中单独核验。'
    elif op=='investigate':
        c=active_case(row,p,'audit')
        if not rules.local(game,row) or not (rules.king(game) or row['controller']=='player'):raise ValueError('须到原案所在地安排调查')
        if c['stage'] not in {'open','reviewing'}:raise ValueError('原案已经完成调查')
        n=p.get('person')
        if n in {c['subject'],king(game)} or person_reason(game,n,'asura',row['location'],assignment=c['id']):raise ValueError('须选择独立、在场且空闲的原调查人')
        if n not in {entry['id'] for entry in rules.eligible_people(game,row)} and n!=c['reviewer']:raise ValueError('原调查人不具备本地公职资格')
        c.update(reviewer=n,stage='reviewing',last_tick=game.player.age)
        c['facts']['review_source']=row['wallet']
        text='原调查人开始逐年查账；真实在场工时与劳务按原公款支付，失效暂停。'
    elif op=='defend':
        c=active_case(row,p,'audit')
        if not rules.local(game,row):raise ValueError('须在原案所在地申辩')
        if c['stage']!='defence' or c['subject']!='player':raise ValueError('尚未轮到原当事人申辩')
        if p.get('choice') not in {'admit','contest'}:raise ValueError('请选择认领责任或提出异议')
        c['facts']['defence']=p['choice'];c['stage']='proposed';text='具名申辩已附原案，王庭须按实际转账与守备凭据裁断。'
    elif op=='judge':
        c=active_case(row,p,'audit');k=royal_audience(game)
        if c['stage'] not in {'proposed','defence'}:raise ValueError('须先完成原址调查和申辩阶段')
        if c['stage']=='defence' and c['subject']=='player':raise ValueError('须先给予本人实际申辩机会')
        if k=='player' and c['subject']=='player':raise ValueError('不能自行审结本人的追偿责任；可先全额退赔交接')
        verdict(game,row,c)
        text=c['result']
    elif op=='restitute':
        c=active_case(row,p,'audit')
        if c['subject']!='player' or not rules.local(game,row):raise ValueError('须由原欠款人在原址实际退赔')
        due=c['amount']-c['paid']
        if not 1<=amount<=due:raise ValueError('退赔不得超过原未清责任')
        authority.fund(game,row,'player',amount);c['paid']+=amount
        if c['paid']==c['amount']:council.close(row,c,'fulfilled','原款全额退赔；实际调查支出与既有撤任不回滚。')
        text='原款已实际退回本府；剩余责任 '+str(c['amount']-c['paid'])+' 灵石。'
    elif op=='case_cancel':
        c=active_case(row,p)
        if c['kind'] not in {'pressure','patronage'} or c['actor']!='player':raise ValueError('债务、盟约与监察不得用撤案清除')
        council.close(row,c,'cancelled','原呈案人撤回未执行提案。');text=c['result']
    else:raise ValueError('未知王庭议政事务')
    authority.log(game,row,text);return text


def verdict(game,row,c):
    guilty=c['facts']['cause']=='diversion' or c['facts'].get('unjustified',False)
    c.update(stage='judged',result='按真实凭证责令退赔及交接。' if guilty else '原守备缺口成立，撤销不当指控。')
    if guilty:
        if row['status'] in {'active','appointed'} and c['subject'] in (row['holder'],row['nominee']):authority.revoke(game,row)
        if c['amount']==c['paid']:council.close(row,c,'fulfilled',c['result'])
    else:council.close(row,c,'rejected',c['result'])


def advance(game,row):
    cfg=rules.config().get('completion',{})
    k=king(game)
    royal=bool(rules.enabled() and cfg and k not in {None,'player'} and not person_reason(game,k,'asura',CAPITAL))
    for c in list(council.book(row)['cases']):
        if c['kind']!='audit':continue
        if royal and c['stage']=='open' and c['last_tick']<game.player.age:
            candidates=[n for n in rules.eligible_people(game,row) if n['id'] not in {c['subject'],k}
                        and not person_reason(game,n['id'],'asura',row['location'])]
            cost=cfg['investigation_years']*cfg['investigation_wage']
            if candidates and council.decide([dict(id='review',cost=cost,priority=90),dict(id='wait',priority=20)],budget=balance(game,row['source'])//10)=='review':
                c.update(reviewer=candidates[0]['id'],stage='reviewing',last_tick=game.player.age)
                c['facts'].update(review_source=row['source'],review_issuer=k)
                authority.log(game,row,'现君依原财政凭据委派本地原调查人，劳务由实际府库逐年实付。')
        if royal and c['stage']=='defence' and game.player.age>=c['deadline']:
            c['facts']['defence']='逾期未提出申辩';c['stage']='proposed'
        if royal and c['stage']=='proposed':
            verdict(game,row,c);authority.log(game,row,c['result']);continue
        if c['stage']!='reviewing' or c['last_tick']>=game.player.age:continue
        c['last_tick']=game.player.age
        if not rules.enabled() or not cfg:continue
        if person_reason(game,c['reviewer'],'asura',row['location'],assignment=c['id']):continue
        wage=cfg['investigation_wage']
        source=c['facts'].get('review_source',row['wallet'])
        if source not in {row['wallet'],row['source']}:continue
        if source==row['source'] and (not royal or c['facts'].get('review_issuer')!=k):continue
        if balance(game,source)<wage:continue
        transfer_value(game,source,'background:asura',wage,'原调查人实际在场查账劳务')
        c['spent']+=wage;c['progress']+=1
        if c['progress']>=cfg['investigation_years']:
            c['stage']='defence' if c['subject']=='player' else 'proposed'
            c['facts']['defence']='守备与军费原状核验' if c['subject']!='player' else ''
