"""Original provincial alliances, negotiated withdrawal and recognition of a crown."""
from . import rules,politics
from .court_affairs import king
from .. import institution_deliberation as council,institution_authority as authority,institution_garrisons as troops
from ..institution_ai.rules import person_reason
from ..economy.ledger import balance,account,transfer_value

OPEN={'raised','marching','contested','capital'}


def war(row):return row.get('asura_military',{}).get('conflict') or {}


def pacts(row):return [c for c in council.book(row)['cases'] if c['kind']=='alliance']


def allies(game,row):
    if war(row).get('status') not in OPEN:return []
    result=[]
    for c in pacts(row):
        r=authority.records(game).get(c['facts'].get('office'))
        if c['stage']=='active' and r and r['controller']==c['subject'] and c['facts'].get('war')==war(row).get('id'):
            result.append(r)
    return result


def belligerent(game,row):return any(row in allies(game,r) for r in rules.offices(game))


def begin(game,row):
    for c in pacts(row):
        r=authority.records(game).get(c['facts']['office'])
        if c['stage']!='open' or not r or r['holder']!=c['subject'] or game.player.age>=c['deadline']:continue
        c['stage']='active';c['facts']['war']=war(row)['id']
        authority.revoke(game,r)


def refund(game,row,c,maps,*,won=False):
    ally=authority.records(game).get(c['facts']['office'])
    if won and ally and ally['controller']==c['subject']:
        authority.fund(game,ally,c['facts']['wallet'],c['amount']);c['paid']=c['amount']
    else:transfer_value(game,c['facts']['wallet'],'player',balance(game,c['facts']['wallet']),'原盟约未履行担保退回原出资人')
    if ally and ally['controller']==c['subject'] and c['stage']=='active':troops.recall(game,maps,ally)
    politics.remember(game,c['subject'],'player',6 if won else -6,'盟约兑现' if won else '原盟约收束',c['id'],settlement=True)
    council.close(row,c,'fulfilled' if won else 'cancelled','原担保按约实拨。' if won else '原未耗担保退回，已耗军费与原撤任保留。')


def finish(game,maps,row):
    for c in list(pacts(row)):refund(game,row,c,maps,won=war(row).get('status')=='won' and c['stage']=='active')


def succession(game,old,new):
    if old==new:return
    for r in rules.offices(game):
        if not r['controller'] or r['controller']==new:continue
        root=council.ensure(r)
        if root['recognition'] is None:root['recognition']=old
        for c in list(root['cases']):
            if c['kind']=='integration':council.close(r,c,'cancelled','原受议王位已经更替。')
        council.open_case(r,'integration',new,r['controller'],game.player.age,facts=dict(previous=old),years=1000)


def command(game,maps,row,op,p):
    amount=p.get('amount',0)
    if type(amount) is not int or not 0<=amount<=10**15:raise ValueError('担保或和议金额无效')
    if op=='ally':
        if not authority.effective(game,row):raise ValueError('须由在任原总督缔约')
        other=authority.records(game).get(p.get('target'))
        if not other or other not in rules.offices(game) or other is row or not authority.effective(game,other,other['holder']):raise ValueError('请选择另一个实际在任的原总督')
        n=other['holder']
        if n=='player' or not rules.local(game,other) or person_reason(game,n,'asura',other['location']):raise ValueError('须亲赴对方府署与原总督当面交涉')
        if any(c['subject']==n for r in rules.offices(game) for c in pacts(r)):raise ValueError('此人已有未结盟约，不能重复出借同一军队')
        rate=sum(u['rate'] for u in troops.active(other))
        if not rate or amount<rate*30:raise ValueError('盟约须有原部众，且预付至少三十年营务等值的个人担保')
        bond=politics.state(game).get('people',{}).get(n,{}).get('bonds',{}).get('player',0)
        refused=other.get('asura_military',{}).get('order',{} ) or {}
        selected=council.decide([dict(id='accept',priority=bond+30,reason='' if bond>=12 or refused.get('status')=='refused' else '尚无可信共同主张'),dict(id='refuse',priority=40)],budget=0)
        if selected!='accept':raise ValueError('原总督拒绝盟约，须先建立可信履约与共同主张')
        c=council.open_case(row,'alliance','player',n,game.player.age,amount=amount,facts=dict(office=other['id'],war=''),years=500)
        wallet='institution-pact:'+c['id'];account(game,wallet);c['facts']['wallet']=wallet
        transfer_value(game,'player',wallet,amount,'具名盟约个人担保预存，不能先领战后收益')
    elif op in {'ally_march','ally_break'}:
        c=council.find(row,p.get('case'))
        if c['kind']!='alliance' or c['actor']!='player':raise ValueError('不是本人的原盟约')
        if op=='ally_break':refund(game,row,c,maps)
        else:
            other=authority.records(game).get(c['facts']['office'])
            if other not in allies(game,row):raise ValueError('须先正式举兵并启用原盟约')
            if not rules.local(game,row):raise ValueError('须在原指挥府署签发具名协同军令')
            troops.dispatch(game,maps,other,'ten_thousand_battle_city')
    elif op=='negotiate':
        w=war(row)
        if w.get('status') not in OPEN:raise ValueError('没有待议和的原战局')
        if w['claimant']=='player':
            if game.player.location_id!='ten_thousand_battle_city' or person_reason(game,w['king'],'asura',game.player.location_id):raise ValueError('须与原君主实际会面')
            if amount<rules.config()['completion']['peace_payment']:raise ValueError('和议须承担约定的实际战后赔款')
            transfer_value(game,'player',row['source'],amount,'原举兵者履行议和赔款，旧案债务另计')
        elif king(game)=='player':
            if person_reason(game,w['claimant'],'asura',game.player.location_id,assignment='garrison:'+row['id']):raise ValueError('须与原举兵者实际会面')
            if council.decide([dict(id='submit',priority=70 if troops.state(row).get('shortfall') or w.get('defeated') else 20),dict(id='resist',priority=40)],budget=0)!='submit':raise ValueError('对方仍有实际抵抗意愿，拒绝归降')
        else:raise ValueError('只有原争位双方可以议和')
        end(game,maps,row,'withdrawn','具名议和完成，原军循路撤回；旧债、撤任与公产责任分别保留。')
    elif op=='integrate':
        if not rules.king(game) or not rules.local(game,row):raise ValueError('须由新君亲赴原府交涉')
        c=council.find(row,p.get('case'))
        if c['kind']!='integration' or c['actor']!='player' or c['subject']!=row['controller']:raise ValueError('原君主或地方控制人已变更')
        n=c['subject']
        if person_reason(game,n,'asura',row['location']):raise ValueError('原总督尚未归返或无法交涉')
        if war(row).get('status') in OPEN or belligerent(game,row):raise ValueError('须先议和或结束实际交战')
        bond=politics.state(game).get('people',{}).get(n,{}).get('bonds',{}).get('player',0)
        if amount<rules.config()['completion']['integration_grant']:raise ValueError('须落实约定的地方安置经费')
        if council.decide([dict(id='accept',priority=50+bond),dict(id='refuse',priority=40)],budget=0)!='accept':raise ValueError('原总督拒绝承认，须先改善实际关系')
        authority.fund(game,row,row['source'],amount)
        council.ensure(row)['recognition']='player'
        council.close(row,c,'fulfilled','地方承认唯一新君，原人原职与独立公账保留；撤任者仍须依法重新赴任。')
    else:raise ValueError('未知盟约与战后事务')
    text='具名交涉已按原人、原军与原账户结算。';authority.log(game,row,text);return text


def advance(game,maps,row):
    for c in list(council.book(row)['cases']):
        if c['kind']=='integration' and c['subject']!=row['controller']:
            council.close(row,c,'cancelled','原控制人已完成交接，停止要求离任者承认新君。')
    for c in list(pacts(row)):
        other=authority.records(game).get(c['facts']['office'])
        if c['stage']=='open' and (not other or other['holder']!=c['subject'] or game.player.age>=c['deadline'] or not rules.enabled()):refund(game,row,c,maps)


def end(game,maps,row,status,text):
    war(row).update(status=status,result=text,ended=game.player.age)
    troops.recall(game,maps,row)
    finish(game,maps,row)
    authority.log(game,row,text+' 原驻军循原路收束，未耗军费归原公账。')
