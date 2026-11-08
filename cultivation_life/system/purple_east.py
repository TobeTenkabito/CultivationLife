"""Four chapters resolve one incident through original industry, court and buildings."""
import copy
from ..building_schema import address
from ..building_rules import ensure_state
from ..models import HistoryRecord
from ..runtime import now_iso
from ..relationship_records import find_person
from .purple_east_rules import (BUILDING,PLANS,PHASES,state,work,original,token,reason,bill,proofs,
    plan_reason,work_reason,begin,finish,start_work,city_id,local)
from .westward_rules import enabled,record
from .yaochi_rules import config
from .yaochi_garden import estate as garden_estate,identity as garden_id
from .yaochi_antiquity import companion_reason,people
from .building_assets import local_rows
from . import building_projects as buildings
from .building_destruction import rebuild
from .economy.enterprise_acquisition import acquire,price
from .economy.enterprise_state import log
from .economy.ledger import balance
from .westward_finance import YAOCHI

def deed_quote(game,maps):
    row=garden_estate(game)
    if row:return dict(cost=0,reason='原药田损毁，须先在原产业页恢复' if row.get('building_status')=='destroyed' else '')
    cost=price(game,maps,dict(id=garden_id(),world='celestial',location=config()['location_id'],kind='farm',level=1))
    return dict(cost=cost,reason='瑶池原府库不足以购买原地块，不登记无来源产业' if balance(game,YAOCHI)<cost else '')

def repair_quote(game):
    row=original(game)
    if not row:return None
    # Prospective testament permission for quotation only. The original record stays
    # background-owned until all real work is done and the original rebuild commits.
    prospective=dict(row,owner=dict(kind='player',id=game.id))
    return buildings.quote(game,'rebuild',prospective)

def command(deps,game,action,target,amount):
    expected,_,value=target.partition('|')
    if type(amount) is not int or amount!=1 or expected!=token(game):raise ValueError('紫气案卷已变化，请刷新后继续')
    if blocked:=reason(game,recovery=action=='purple_pause'):raise ValueError(blocked)
    s=state(game)
    if action=='purple_start':
        if s:raise ValueError('此界异象已有唯一案卷，换身份或重返不能重新开案')
        from .westward_activity import occupied,other_work
        if occupied(game) or other_work(game):raise ValueError('请先交接本人已接受的事务')
        city=next((r for r in local_rows(game) if r['id']==city_id()),None)
        if not city or city['status']!='intact':raise ValueError('原瑶池聚落不可用，须先恢复当地城市')
        deed=deed_quote(game,deps.maps)
        if deed['reason']:raise ValueError(deed['reason'])
        farm=garden_estate(game)
        if not farm:farm=acquire(game,deps.maps,'celestial',config()['location_id'],'farm','yaochi','yaochi',YAOCHI,game.player.realm_index,expected_cost=deed['cost'])
        if BUILDING in ensure_state(game)['records']:raise ValueError('原仙府已存在而案卷缺失，拒绝重建或覆盖')
        s=game.yaochi_state.setdefault('westward',{}).setdefault('purple_east',{})
        s.update(phase='survey',started=game.player.age,city=city['id'],estate=farm['id'],
            garden_baseline=[r['wallet'] for r in record(game).get('garden',{}).get('receipts',[])],
            disruption_until=game.player.age+20,recorded_identity=None)
        from .immortal_identity_rules import primary
        s['recorded_identity']=primary(game)
        ensure_state(game)['records'][BUILDING]=dict(id=BUILDING,name='紫宸古仙府',type='artificiality',subtype='cave',
            level=1,status='destroyed',quality='professional',invested=0,address=address(game),
            owner=dict(kind='background',id=BUILDING),users=[],public=False,
            description='紫气异象中的原址空府。公议后实付重建，原封藏不另造可流通货币。')
        buildings.persist(game,city)['civic_disruption_until']=s['disruption_until']
        farm['public_water_until']=max(game.player.age,farm.get('public_water_until',0))+10
        if farm.get('job'):farm['job']['finish']+=10
        farm['revision']+=1;log(farm,game.player.age,'紫宸异象：导流十年，暂停新投产，在制延期十年，原养护照常')
        start_work(game,'survey',5)
        summary='紫气现世：原聚落发展事务受扰至二十年后，原药田导流十年。先实际勘察五年，同一案卷向三途开放。'
    elif not s:raise ValueError('请先登记唯一异象案卷')
    elif action=='purple_work':
        begin(game);return deps.advance(game.id,'purple_work',1)
    elif action=='purple_pause':
        if not work(game):raise ValueError('当前没有本人主线工时')
        s['paused_work']=s.pop('work');summary='暂停本人主线工时，保留已付工料与实际进度；异象期限照常，协作者解除临时占用。'
    elif action=='purple_resume':
        saved=s.get('paused_work')
        if not saved:raise ValueError('没有暂停的主线工序')
        if saved.get('companion'):
            if blocked:=companion_reason(game,find_person(game,saved['companion'])):raise ValueError(blocked)
        start_work(game,saved['kind'],saved['years'],saved.get('companion'));s['work']['progress']=saved['progress'];s.pop('paused_work')
        summary='从原进度继续，已耗年份与工料不重付。'
    elif action=='purple_replan':
        if s['phase'] not in {'hearing','implementation'} or not s.get('plan') or work(game):raise ValueError('须先暂停已定议工序，再申请重新定议')
        row=original(game)
        if not row or row['status']!='destroyed' or row['owner']!=dict(kind='background',id=BUILDING):raise ValueError('原仙府权属已变，不得重开定议')
        for key in ('plan','companion','evidence','paused_work'):s.pop(key,None)
        s['phase']='hearing'
        summary='已撤回原方案并解除协作者占用。已耗整理工时与工料不退还；原调查、护持和真实履约回执保留，可另选方案重新定议。'
    elif action=='purple_mitigate':
        if s['phase']!='dispute' or s.get('mitigation') or s.get('paused_work'):raise ValueError('当前不能重选疏导方案')
        if value not in {'canal','wait'}:raise ValueError('请选择实付疏导或轮值安置')
        start_work(game,value,5 if value=='canal' else 15)
        if value=='canal':buildings.pay(game,bill(game,'canal'),'紫气异象原址导流')
        summary='已接受五年实付疏导。' if value=='canal' else '已接受十五年原址轮值安置；不另征用原药田或生成安置奖励。'
    elif action=='purple_civic':
        if s['phase']!='hearing' or s.get('civic_done') or s.get('paused_work'):raise ValueError('当前不能重复接受护持')
        start_work(game,'civic',10);summary='公开参与地方护持，实际十年，不要求地仙身份，不叠发香火或公务报酬。'
    elif action=='purple_plan':
        if s['phase']!='hearing' or s.get('paused_work'):raise ValueError('须完成前两章并结清暂停工序')
        key,_,companion=value.partition('~')
        if key not in PLANS:raise ValueError('未知资源使用方案')
        if blocked:=plan_reason(game,key):raise ValueError(blocked)
        evidence=proofs(game)
        if not any(evidence[k] for k in ('fair','council','garden','civic')):raise ValueError('须先提交本案护持、仙会获奖、原仙圃供货或公共修持的真实成果')
        if key=='shared':
            if blocked:=companion_reason(game,find_person(game,companion)):raise ValueError(blocked)
        start_work(game,'hearing',5);s.update(plan=key,companion=companion if key=='shared' else None,evidence=evidence)
        summary='瑶池定议：按真实成果登记'+PLANS[key]['name']+'，五年公开质询，不支付虚构好感奖励。'
    elif action=='purple_build':
        if s['phase']!='implementation' or s.get('paused_work'):raise ValueError('尚未取得定议方案，或仍有暂停工序')
        row=original(game)
        if row['status']!='destroyed' or row['owner']!=dict(kind='background',id=BUILDING):raise ValueError('原仙府权属或状态失效')
        if s.get('companion'):
            if blocked:=companion_reason(game,find_person(game,s['companion'])):raise ValueError(blocked)
        start_work(game,'build',PLANS[s['plan']]['years'],s.get('companion'))
        buildings.pay(game,bill(game,'build'),'紫宸原址整理实付工料')
        summary='实付整理工料并开工；建筑本体须在完工时沿原营造价格重建，不能预支免费仙府。'
    elif action=='purple_submit':
        if blocked:=work_reason(game):raise ValueError(blocked)
        w=work(game)
        if w['progress']<w['years']:raise ValueError('本步实际工时尚未完成')
        kind=w['kind']
        if kind=='survey':s['phase']='dispute';summary='原府、聚落与药田事实已核对；选择修渠疏导或轮值安置，原物资不复制。'
        elif kind in {'canal','wait'}:
            row=game.building_state['records'].get(s['city'])
            if not row:raise ValueError('原聚落记录失效，不能覆盖另一座城市')
            if row.get('civic_disruption_until')==s['disruption_until']:row['civic_disruption_until']=min(game.player.age,s['disruption_until'])
            s.update(phase='hearing',mitigation=kind);summary='地方影响已处理。可用公开护持或既有玩法的真实成果参与瑶池定议。'
        elif kind=='civic':s['civic_done']=True;summary='十年地方护持已完成，可作为本案定议依据，不兑换第二份香火或报酬。'
        elif kind=='hearing':s['phase']='implementation';summary='定议通过，按约定权属与使用者实施；原七曜公共修持回执仍独立有效。'
        elif kind=='build':
            q=repair_quote(game)
            if q['reason']:raise ValueError(q['reason'])
            row=original(game);row['owner']=dict(kind='player',id=game.id)
            rebuild(game,row,None)
            plan=s['plan']
            if plan=='guard':buildings.set_public(game,row,True)
            elif plan=='public':row.update(owner=dict(kind='background',id='organization:court:heavenly'),public=True)
            elif plan=='yaochi':row.update(owner=dict(kind='background',id=YAOCHI),users=[dict(kind='player',id=game.id)])
            else:row['users']=[dict(kind='npc',id=s['companion'])]
            s.update(phase='complete',completed=game.player.age,receipt=dict(building_id=BUILDING,plan=plan,coins=q['coins'],users=copy.deepcopy(row['users']),owner=copy.deepcopy(row['owner'])))
            summary='紫气东来：'+PLANS[plan]['name']+'已落实到原仙府权属与使用权。原药田照常生产，已得个人成长保留；不能换身份重领奖或重建另一份仙府。'
        else:raise ValueError('未知主线工序')
        s.pop('work')
    else:raise ValueError('未知紫气主线操作')
    s['last_result']=summary
    game.history.append(HistoryRecord('SYS_PURPLE_EAST',1,game.player.age,'紫气东来',action,'completed',summary,{},['yaochi','story']))
    game.updated_at=now_iso();deps.store.save(game);return deps.present(game)

def public(game,maps):
    if game.player.world!='celestial' or game.guixu_state.get('player_session') or not (enabled() or state(game)):return None
    s=state(game);here=local(game);w=work(game)
    return dict(enabled=enabled(),token=token(game),reason=reason(game),recovery_reason=reason(game,True),
        state=copy.deepcopy(s),phase_name=PHASES.get(s.get('phase'),'紫气东来 · 共用主线'),work_reason=work_reason(game),
        site=config()['location_id'],proofs=proofs(game),deed=deed_quote(game,maps) if here and not s else None,
        plans=[dict(id=k,**v,reason=plan_reason(game,k)) for k,v in PLANS.items()],
        bill=bill(game,'canal'),build_bill=bill(game,'build'),repair=repair_quote(game) if here and s.get('phase')=='implementation' else None,
        candidates=[dict(id=n.id,name=n.name) for n in people(game)] if here else [])
