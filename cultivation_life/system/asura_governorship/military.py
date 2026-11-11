"""Asura military charter: orders and resistance over original base garrisons."""
import copy
import sys
from . import rules, politics
from .. import institution_authority as authority, institution_garrisons as troops
from ..institution_ai.rules import person_reason, choose
from ..economy.ledger import balance
from ...relationship_records import find_person

CAPITAL='ten_thousand_battle_city'
OPEN={'raised','marching','contested','capital'}


def config():return rules.config().get('military',{})
def enabled():return rules.enabled() and bool(config().get('enabled'))
def state(row):return row.get('asura_military',{})
def ensure(row):return row.setdefault('asura_military',dict(sequence=0,order=None,conflict=None,last_year=-1,last_battle=-1,service_years=0))
def king_id(game):return rules.court(game).get('court',{}).get('holders',{}).get('5')
def conflict(row):return state(row).get('conflict')
def fighting(row):return bool(conflict(row) and conflict(row)['status'] in OPEN)
def owner(row):return conflict(row)['claimant'] if fighting(row) else row['holder'] or row['controller']
def sites(game):return [CAPITAL]+[c['address']['location_id'] for c in rules.cities(game) if rules.legal_city(game,c)]


def local_office(game,row):
    b=rules.building(game,row)
    return bool(b and b['status']=='intact' and b['owner']==row['owner'] and
        b['address']==dict(world=row['world'],location_id=row['location'],instance_id=None)
        and any(c['id']==row['city_id'] and rules.legal_city(game,c) for c in rules.cities(game)))


def candidates(game,row):
    result=[]
    from ..war.occupancy import busy
    for entry in rules.eligible_people(game,row):
        npc=find_person(game,entry['id']);org=game.sects.get(npc.faction_id)
        if authority.responsibilities(game,npc.id) or org and busy(game,org,exclude_garrison=row['id']):continue
        result.append(dict(entry,rate=config().get('annual_service',1000)*(1+max(0,npc.realm_index-9))))
    return result


def issue(game,row,destination):
    if destination not in sites(game) or destination==row['location']:raise ValueError('请选择有效的异地驻防点')
    root=ensure(row);prior=root['order']
    if prior and prior['status'] in {'issued','delayed','refused','accepted'}:raise ValueError('须先处置当前军令')
    if not authority.effective(game,row,row['holder']) or fighting(row):raise ValueError('没有可受令的合法在任总督')
    if not troops.stationed(game,row,row['location']):raise ValueError('本府没有可实际抽调的驻军')
    root['sequence']+=1
    root['order']=dict(id=f"{row['id']}:order:{root['sequence']}",issuer=king_id(game),recipient=row['holder'],
        destination=destination,issued=game.player.age,deadline=game.player.age+config()['order_years'],
        status='issued',reason='',extensions=0)
    authority.log(game,row,'中央下达调防军令；须由当地总督核验、安排原军出发。')


def answer(game,maps,row,choice):
    order=state(row).get('order')
    if not order or order['status'] not in {'issued','delayed','refused'}:raise ValueError('没有待回应军令')
    if order['issuer']!=king_id(game) or order['recipient']!=row['holder']:raise ValueError('原发令人与受令任职已变化')
    if choice=='comply':
        # Keep one actual local guard where possible; a single guard cannot be
        # simultaneously counted as both the home defence and the marching army.
        units=troops.stationed(game,row,row['location'])
        selected=units[1:] if len(units)>1 else units
        troops.dispatch(game,maps,row,order['destination'],[u['person_id'] for u in selected])
        order.update(status='accepted',reason='原军沿道路调防；留守人数按实减少。')
    elif choice=='delay':
        units=troops.stationed(game,row,row['location'])
        reason='原址只有一名守备，须先安排接防。' if len(units)<=1 else ''
        if not reason:
            try:troops.plan(game,maps,row,order['destination'])
            except ValueError as error:reason=str(error)
        if not reason:raise ValueError('没有可核验的守备、道路或军费缺口')
        if order['extensions']:raise ValueError('本令已缓调一次，须履令或明确拒命')
        order.update(status='delayed',reason=reason,deadline=game.player.age+config()['order_years'],extensions=1)
    elif choice=='refuse':order.update(status='refused',reason='总督具名拒绝中央军令。')
    else:raise ValueError('未知军令回应')
    authority.log(game,row,order['reason'])


def raise_banner(game,row,claimant):
    if fighting(row) or any(fighting(r) and conflict(r)['claimant']==claimant for r in rules.offices(game)):
        raise ValueError('已有未结束的举兵战局')
    if claimant==king_id(game) or not king_id(game):raise ValueError('当前没有可争夺的在位王权')
    if claimant not in (row['holder'],row['controller']) or not local_office(game,row):raise ValueError('须有原府实际控制及完好府署')
    units=troops.stationed(game,row,row['location'])
    supporters=[u for u in units if politics.state(game).get('people',{}).get(u['person_id'],{}).get('bonds',{}).get(claimant,0)>=config()['support_required']]
    if not supporters:raise ValueError('至少须有一名实际驻军明确支持本人；任命不等于私人效忠')
    if claimant!='player':
        if person_reason(game,claimant,row['world'],row['location']):raise ValueError('举兵者须本人在场且没有其他占用')
        supporters=supporters[:5]
    if balance(game,troops.state(row)['wallet'])<sum(u['rate'] for u in supporters)*config()['reserve_years']:
        raise ValueError('举兵前须备妥原军至少三十年营务经费')
    # Those who did not commit keep their persons and freedom, not a copied army.
    for u in units:
        if u not in supporters:u['phase']='home'
    root=ensure(row);root['sequence']+=1
    root['conflict']=dict(id=f"{row['id']}:rising:{root['sequence']}",claimant=claimant,king=king_id(game),
        status='raised',started=game.player.age,deadline=game.player.age+config()['campaign_years'],
        controlled=[],defeated=False,result='',ended=None)
    if row['status'] in {'active','appointed'}:authority.revoke(game,row)
    if claimant!='player':
        troops.enlist(game,row,claimant,config()['annual_service'],commander=True)
    authority.log(game,row,'公开举兵争夺王位；法定总督授权撤销，原公款、军令与地方责任保留。')


def close(game,maps,row,status,text):
    war=conflict(row)
    war.update(status=status,result=text,ended=game.player.age)
    troops.recall(game,maps,row)
    authority.log(game,row,text+' 原驻军循原路收束，未耗军费归原公账。')


def command(game,maps,row,payload,*,combat=None):
    op=payload.get('operation');target=payload.get('destination');person=payload.get('person')
    if not isinstance(op,str) or target is not None and not isinstance(target,str):raise ValueError('军令请求格式无效')
    if not enabled() and op not in {'recall','standdown','cancel_order'}:raise ValueError('修罗军政停用，仅开放撤军与交接')
    if maps is None:raise ValueError('缺少原地图路线服务')
    local=rules.local(game,row);central=rules.king(game) and game.player.location_id==CAPITAL
    controlled=owner(row)=='player'
    if op in {'order','cancel_order','press'}:
        if not central:raise ValueError('须由现任修罗王在王庭签发军令')
        if op=='order':issue(game,row,target)
        else:
            order=state(row).get('order')
            if not order or order['issuer']!='player' or order['status'] not in {'issued','delayed','refused','accepted'}:raise ValueError('原军令已失效或结案')
            if op=='cancel_order':order.update(status='cancelled',reason='中央撤销调防要求；已出发部众须另行召回。')
            else:
                if order['status']!='refused':raise ValueError('须先核实具名抗命，缓调不能直接当作谋反')
                order.update(status='enforced',reason='中央撤销任职并责令交接，原部将分别决定去留。')
                if row['status'] in {'active','appointed'}:authority.revoke(game,row)
                authority.log(game,row,order['reason'])
        return '军令已留档；人员尚须实际执行。'
    if op=='abdicate':
        if not central or not fighting(row) or conflict(row)['king']!='player':raise ValueError('须由被争位的现君在王庭办理退位')
        if not troops.stationed(game,row,CAPITAL):raise ValueError('举兵方尚未抵达王庭，不能完成王权交接')
        from .military_combat import enthrone
        return enthrone(game,maps,row,m=sys.modules[__name__])
    if op in {'assault','claim','pacify'}:
        from .military_combat import battle
        return battle(game,maps,row,op,combat,m=sys.modules[__name__])
    if op=='recall' and central:
        if fighting(row):raise ValueError('抗命部众须先议和或讨伐，不能用中央按钮直接搬回')
        troops.recall(game,maps,row);return '原部众开始循原路归返；未耗军费待收束后退回。'
    if op=='standdown' and controlled and fighting(row):
        close(game,maps,row,'withdrawn','撤回夺位主张；原任职已失效，不恢复官职或退回已耗军费。')
        return conflict(row)['result']
    if not controlled or not local:raise ValueError('须由原指挥人在总督府原址办理')
    ensure(row)
    if op in {'enlist','provision','dispatch'} and not local_office(game,row):raise ValueError('府署产权、地址或设施失效')
    if op=='enlist':
        if not authority.effective(game,row) or fighting(row):raise ValueError('举兵或撤任后不能以公职强征人员')
        candidate=next((n for n in candidates(game,row) if n['id']==person),None)
        if not candidate:raise ValueError('此人不是当前自由、在场且可征募的原人物')
        troops.enlist(game,row,person,candidate['rate'],capacity=config()['capacity'])
        politics.appointment(game,person,'player','staff',row['id'])
    elif op=='provision':
        if not (authority.effective(game,row) or fighting(row)):raise ValueError('撤任后只允许归返交接，不再动用公款扩军')
        troops.provision(game,row,payload.get('amount'))
    elif op=='dispatch':
        if not (authority.effective(game,row) or fighting(row)):raise ValueError('撤任后只能撤军交接')
        if target not in sites(game):raise ValueError('目的地没有本界军政道路许可')
        troops.dispatch(game,maps,row,target)
        if fighting(row):
            war=conflict(row);war['status']='marching'
            war['deadline']=max(war['deadline'],game.player.age+max(u['years'] for u in troops.active(row))+config()['campaign_years'])
    elif op=='recall':troops.recall(game,maps,row)
    elif op=='respond':
        if not authority.effective(game,row):raise ValueError('已失去受令任职')
        answer(game,maps,row,payload.get('choice'))
    elif op=='rebel':raise_banner(game,row,'player')
    elif op=='standdown':
        if not fighting(row):raise ValueError('没有待收束的举兵战局')
        close(game,maps,row,'withdrawn','撤回夺位主张；原任职已失效，不恢复官职或退回已耗军费。')
    else:raise ValueError('未知军政事务')
    authority.log(game,row,config()['operations'].get(op,op)+'：原人、原款与道路按实登记。')
    return row['history'][-1]['text']


def advance(game,maps,row):
    if game.player.age<row['appointed'] or any(h['year']>game.player.age for h in row['history']):return
    root=state(row)
    if root and game.player.age<=root['last_year']:return
    if (enabled() and authority.effective(game,row,row['holder']) and row['holder'] not in {None,'player'}
            and local_office(game,row) and not person_reason(game,row['holder'],row['world'],row['location'])):
        # Content provides the defence need; the shared base chooser enforces
        # the original public budget. One original person per bounded review.
        if game.player.age%config()['bond_years']==0 and len(troops.active(row))<3:
            offers=[dict(key=n['id'],category='defence',urgency=70,budget=n['rate']*config()['reserve_years'],reason='',rate=n['rate'])
                    for n in candidates(game,row)]
            selected=choose(offers,'balanced',balance(game,row['wallet'])//10)
            if selected and not any(u['destination']!=row['location'] or u['phase']!='stationed' for u in troops.active(row)):
                troops.enlist(game,row,selected['key'],selected['rate'])
                troops.provision(game,row,selected['budget'])
                politics.appointment(game,selected['key'],row['holder'],'staff',row['id'])
                root=ensure(row)
                authority.log(game,row,'总督按原预算征募当地自由修士并支付三十年营务；未生成新兵。')
    if root:root['last_year']=game.player.age
    troops.advance(game,maps,row)
    if not root:return
    if enabled() and troops.active(row) and troops.state(row).get('spent',0)>0 and not troops.state(row).get('shortfall'):
        root['service_years']+=1
        if root['service_years']%config()['bond_years']==0:
            for unit in troops.active(row):
                politics.remember(game,unit['person_id'],owner(row),1,'原军饷与共同驻防履约',row['id'])
    war=conflict(row)
    if fighting(row):
        if not enabled() and war['claimant']!='player':
            close(game,maps,row,'withdrawn','专属军政停用，原举兵者停止新攻势并撤回，已耗军费和撤任后果保留。');return
        claimant=find_person(game,war['claimant']) if war['claimant']!='player' else game.player
        from ...npc_custody import is_free
        free=(not game.player.imprisonment and not game.player.ghost_captor) if war['claimant']=='player' else bool(claimant and is_free(claimant))
        if not claimant or not claimant.alive or not free or king_id(game)!=war['king']:
            close(game,maps,row,'ended','原争位主体或王位已变化，停止沿旧案争位。');return
        if game.player.age>=war['deadline'] or not troops.active(row):
            close(game,maps,row,'withdrawn','战局期限或实际军力不足，结束举兵并办理归返。');return
        if enabled() and war['claimant']!='player':
            if troops.stationed(game,row,row['location']) and war['status']=='raised':
                try:
                    troops.dispatch(game,maps,row,CAPITAL)
                    war['status']='marching'
                    war['deadline']=max(war['deadline'],game.player.age+max(u['years'] for u in troops.active(row))+config()['campaign_years'])
                except ValueError:pass
            elif troops.stationed(game,row,CAPITAL) and CAPITAL not in war['controlled']:
                from .military_combat import skirmish
                try:skirmish(game,maps,row,CAPITAL,sys.modules[__name__])
                except ValueError:pass
            elif troops.stationed(game,row,CAPITAL):
                from .military_combat import npc_claim
                try:npc_claim(game,maps,row,sys.modules[__name__])
                except ValueError:pass
    if (row['status']=='handover' and row['controller'] not in {None,'player'}
            and not fighting(row) and not troops.active(row)
            and not person_reason(game,row['controller'],row['world'],row['location'])):
        authority.relinquish(game,row,row['controller'])
        if root['order'] and root['order']['status']=='enforced':
            root['order'].update(status='fulfilled',reason='原军完成归返，原任完成地方交接。')
    # An NPC king asks for actual relief only when the capital lacks available
    # guards and this province can spare a real second retainer. No view tick.
    sovereign=king_id(game)
    royal_here=bool(sovereign and sovereign!='player' and not person_reason(game,sovereign,'asura',CAPITAL))
    if enabled() and royal_here and not fighting(row):
        from ..asura_court_finance import people
        guards=len({n.id for n in people(game).values() if n.id!=sovereign and not person_reason(game,n.id,'asura',CAPITAL)}
                   | {u['person_id'] for scope in rules.offices(game) for u in troops.stationed(game,scope,CAPITAL)})
        pending=root['order'] and root['order']['status'] in {'issued','delayed','refused','accepted','enforced'}
        if not pending and guards<2 and len(troops.stationed(game,row,row['location']))>=2 and game.player.age%100==0:
            if authority.effective(game,row,row['holder']):issue(game,row,CAPITAL)
        order=root['order']
        if (order and order['issuer']==sovereign and order['recipient']==row['holder']
                and order['status']=='refused' and game.player.age>=order['deadline']+config()['order_years']):
            offers=[dict(key='cancel',category='defence',budget=0,urgency=90 if guards>=2 else 30,reason=''),
                    dict(key='enforce',category='defence',budget=0,urgency=70,
                         reason='' if len(troops.stationed(game,row,row['location']))>=2 else '原址守备不足')]
            decision=choose(offers,'balanced',0,allow_zero=True)['key']
            if decision=='enforce' and row['status']=='active':
                order.update(status='enforced',reason='现君核实具名拒命后撤任追责，原军须实际交接。')
                authority.revoke(game,row)
            else:order.update(status='cancelled',reason='现君核实守备需求，撤销本次调防要求。')
            authority.log(game,row,order['reason'])
    order=root['order']
    if not order:return
    if order['status'] in {'issued','delayed','refused','accepted'} and (order['issuer']!=king_id(game) or order['recipient']!=row['holder']):
        order.update(status='obsolete',reason='原发令或受令任职变化，旧令不再产生新行动。');return
    if order['status']=='accepted' and troops.stationed(game,row,order['destination']):
        order.update(status='fulfilled',reason='原部众已实际抵达，调防履行完成。');authority.log(game,row,order['reason']);return
    if not enabled():
        if (row['status']=='handover' and row['controller'] not in {None,'player'} and not troops.active(row)
                and not person_reason(game,row['controller'],row['world'],row['location'])):
            authority.relinquish(game,row,row['controller'])
            order.update(status='fulfilled',reason='停用后完成原撤军与地方交接，不恢复公职或已耗军费。')
        return
    if order['status']=='enforced' and row['controller'] not in {None,'player'} and not fighting(row):
        if not person_reason(game,row['controller'],row['world'],row['location']):
            try:raise_banner(game,row,row['controller'])
            except ValueError:
                troops.recall(game,maps,row)
                if not troops.active(row):
                    authority.relinquish(game,row,row['controller'])
                    order.update(status='fulfilled',reason='原任完成撤军与地方交接，既有军费按实结清。')
        return
    if row['holder'] not in {None,'player'} and order['status'] in {'issued','delayed'} and not person_reason(game,row['holder'],row['world'],row['location']):
        offers=[]
        for choice in ('comply','delay','refuse'):
            reason=''
            if choice=='comply':
                try:troops.plan(game,maps,row,order['destination'])
                except ValueError as error:reason=str(error)
            if choice=='delay' and order['extensions']:reason='已经缓调'
            priority={'comply':80,'delay':50,'refuse':10}[choice]
            if len(troops.stationed(game,row,row['location']))<=1 and choice=='delay':priority=90
            offers.append(dict(key=choice,category='military',urgency=priority,budget=0,reason=reason))
        selected=choose(offers,'balanced',0,allow_zero=True)
        if selected:
            try:answer(game,maps,row,selected['key'])
            except ValueError:pass
    if order['status'] in {'issued','delayed'} and game.player.age>=order['deadline']:
        order.update(status='refused',reason='原军令到期未履行；中央仍须区分事实并明确处置。')


def public(game,row):
    mine=owner(row)=='player';royal=rules.king(game);central=royal and game.player.location_id==CAPITAL
    local=rules.local(game,row)
    if not (mine or central or royal and local):return None
    root=state(row);roster=[]
    places={CAPITAL:'万战城 · 王庭',**{c['address']['location_id']:c['name'] for c in rules.cities(game)}}
    for u in troops.active(row):
        npc=find_person(game,u['person_id'])
        roster.append(dict(id=u['person_id'],name=npc.name if npc else '原人失联',phase=u['phase'],
            destination=u['destination'],destination_name=places.get(u['destination'],u['destination']),remaining=u['remaining'],rate=u['rate'],
            supporting=mine and politics.state(game).get('people',{}).get(u['person_id'],{}).get('bonds',{}).get(owner(row),0)>=config().get('support_required',12)))
    funds=troops.state(row)
    return dict(enabled=enabled(),local=local,mine=mine,central=central,units=roster,
        balance=balance(game,funds['wallet']) if funds else 0,spent=funds.get('spent',0),shortfall=funds.get('shortfall',0),
        order=copy.deepcopy(root.get('order')),conflict=copy.deepcopy(root.get('conflict')),
        candidates=candidates(game,row) if mine and local and enabled() else [],
        destinations=[dict(id=p,name=places.get(p,p)) for p in sites(game)],operations={'recall':'召回原军','standdown':'撤回举兵并归返','cancel_order':'撤销军令',**config().get('operations',{})},current_location=game.player.location_id)
