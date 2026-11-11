"""Asura charter choices over base appointments, money, arrays and handover."""
from . import rules
from .court_affairs import royal_audience,king,local
from .. import institution_deliberation as council,institution_mandates as mandates,institution_garrisons as troops,institution_authority as authority,institution_arrays as arrays


def recognized(game,row):return council.book(row)['recognition'] in (None,king(game))


def command(game,maps,row,op,p):
    central=rules.king(game) and game.player.location_id=='ten_thousand_battle_city'
    mandate=council.book(row)['mandate']
    if op in {'charter','central_enlist','central_pay'}:
        if not central or not recognized(game,row):raise ValueError('须由已获本府承认的现君在王庭办理')
        if not authority.effective(game,row,row['holder']):raise ValueError('本府没有有效在任授权')
        if op=='charter':
            choice=p.get('choice','').split(':')
            if len(choice)!=2:raise ValueError('请选择供养与任将组合')
            mandates.configure(row,*choice)
        elif op=='central_pay':
            if mandate['funding']!='central':raise ValueError('本府现由地方供养')
            troops.provision(game,row,p.get('amount'),source=row['source'])
        else:
            if mandate['appointments']!='central':raise ValueError('本府现由地方任将')
            from .military_people import candidates
            n=next((n for n in candidates(game,row) if n['id']==p.get('person')),None)
            if not n:raise ValueError('所选原人不在本府或已有其他占用')
            troops.enlist(game,row,n['id'],n['rate'])
    elif op in {'relief','relief_send','relief_finish','relief_cancel'}:
        if op!='relief_cancel' and not authority.effective(game,row,row['holder']):raise ValueError('任职已失效，仅可收束接防')
        if op=='relief_cancel' and row['controller']=='player' and rules.local(game,row):pass
        elif mandate['appointments']=='central':
            if not central or not recognized(game,row):raise ValueError('轮调须由中央任将机关办理')
        else:local(game,row)
        if op=='relief':
            from .military_people import candidates
            n=next((n for n in candidates(game,row) if n['id']==p.get('person')),None)
            if not n:raise ValueError('接防者须为原府实际空闲修士')
            mandates.relief(game,row,p.get('target'),n['id'],'player',n['rate'])
        elif op=='relief_finish':mandates.finish_relief(game,maps,row)
        else:
            r=council.book(row)['rotation']
            if not r or r['stage']!='awaiting':raise ValueError('没有待交接轮调')
            if op=='relief_cancel':
                troops.recall(game,maps,row,[r['incoming']]);r['stage']='cancelled'
            else:
                old=next((u for u in troops.active(row) if u['person_id']==r['outgoing']),None)
                if not old or old['phase']!='stationed':raise ValueError('原守将尚未就位')
                troops.dispatch(game,maps,row,old['destination'],[r['incoming']])
    elif op=='move_request':
        if not authority.effective(game,row):raise ValueError('须由在任原总督申请迁署')
        k=royal_audience(game);mandates.move_ready(game,row)
        city=next((c for c in rules.cities(game) if c['id']==p.get('destination') and rules.legal_city(game,c)),None)
        if not city or city['id']==row['city_id'] or any(r['city_id']==city['id'] for r in rules.offices(game)):raise ValueError('新址须有原设府许可且未设另一府署')
        council.ensure(row)['relocation']=dict(city=city['id'],location=city['address']['location_id'],requested=game.player.age,deadline=game.player.age+100,stage='approved',issuer=k,holder='player')
    elif op=='move_complete':
        permit=council.book(row)['relocation']
        if not permit or permit['stage']!='approved' or permit['issuer']!=king(game) or permit['holder']!='player' or permit['deadline']<=game.player.age or not authority.effective(game,row):raise ValueError('原迁署许可或任职已失效')
        city=next((c for c in rules.cities(game) if c['id']==permit['city'] and rules.legal_city(game,c)),None)
        if not city:raise ValueError('新址原许可失效')
        mandates.relocate(game,row,city,'office:'+row['id']+':'+city['id'])
        row['name']=city['name']+'总督府';permit['stage']='completed'
    elif op in {'guard_bind','guard_repair'}:
        local(game,row)
        if not rules.building(game,row) or rules.building(game,row)['status']!='intact':raise ValueError('须先修复原府署')
        if op=='guard_bind':arrays.bind(game,row,p.get('target'))
        else:arrays.maintain(game,row,p.get('target'))
    else:raise ValueError('未知军权或府署事务')
    text='原军权、阵位与迁署凭据已登记；人员沿原路执行，款物按原账结清。'
    authority.log(game,row,text);return text
