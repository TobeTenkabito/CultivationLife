"""Three bounded competitions using real combat, arrays and delivered goods."""
import copy
from ..content_registry import ITEM_CATALOG
from ..models import HistoryRecord
from ..runtime import decode_rng,encode_rng,now_iso
from ..rules import remove_item
from ..relationship_records import find_person
from .yaochi_fair_rules import NAMES,state,entries,active,cycle,reason,people,work_reason
from .westward_rules import record
from .westward_finance import YAOCHI
from .yaochi_rules import spend,config
from .economy.ledger import account,balance,transfer_value
from .economy.state import local_market,reprice
from .economy.local_market import quote
from .economy.enterprise_rules import recipes
from .economy.resource_access import permits
from .economy.state import commodity_catalog
from .court_bureau_rules import digest

def token(game):
    p=game.player
    return digest([p.age,p.world,p.location_id,p.realm_index,p.layer,p.hp,p.mp,game.pending_event,
        state(game),game.yaochi_state.get('merit',0),[(n.id,n.realm_index,n.layer,n.wounds) for n in people(game)]])

def bundle(game):
    market=local_market(game)
    if not market:return {}
    crops=recipes('celestial',commodity_catalog('celestial'))
    site=dict(world='celestial',location=config()['location_id'],kind='farm')
    ids=[r['output'] for r in crops.values() if r['kind']=='farm' and permits(site,r) and r['output'] in market['commodities']
         and market['commodities'][r['output']]['tier']<=game.player.realm_index+1]
    ids=sorted(set(ids),key=lambda k:(market['commodities'][k]['reference'],k))[:2]
    return {key:4 for key in ids} if len(ids)==2 else {}

def begin(game):
    if blocked:=work_reason(game):raise ValueError(blocked)
    r=active(game)
    if r['progress']>=r['years']:raise ValueError('筹备已经完成，请参赛或交付')
    return min(r['years']-r['progress'],r['deadline']-game.player.age)

def finish(game,elapsed,unit):
    r=active(game)
    if r:r['progress']=min(r['years'],r['progress']+elapsed)
    s=game.yaochi_state.setdefault('westward',{})
    count,s['settlement_years']=divmod(s.get('settlement_years',0)+elapsed,unit)
    return count

def settle(game,r,success,summary):
    if success:
        transfer_value(game,r['wallet'],'player',r['prize'],'仙会本届一次性奖金')
        state(game)['priority']=dict(cycle=r['cycle'],until=(r['cycle']+2)*500,used=False)
    transfer_value(game,r['wallet'],YAOCHI,balance(game,r['wallet']),'仙会余款退回瑶池原府库')
    r.update(status='won' if success else 'closed',result=summary,closed=game.player.age)

def command(deps,game,action,target,amount):
    if type(amount) is not int or amount!=1:raise ValueError('每次办理一项仙会事务')
    expected,_,value=target.partition('|')
    if expected!=token(game):raise ValueError('仙会状态已变化，请刷新后再操作')
    recovery=action=='fair_cancel'
    if blocked:=reason(game,recovery):raise ValueError(blocked)
    r=active(game)
    if action=='fair_join':
        kind,_,opponent=value.partition('~')
        if kind not in NAMES:raise ValueError('未知赛事')
        if r:raise ValueError('请先完成或退出当前赛事')
        if any(e['cycle']==cycle(game) and e['kind']==kind for e in entries(game)):raise ValueError('同届每项只可报名一次，退赛不重开')
        deadline=min(game.player.age+50,(cycle(game)+1)*500)
        if deadline-game.player.age<=5:raise ValueError('本届余下时间不足筹备与参赛，请等下一届')
        if kind!='supply':
            npc=next((n for n in people(game) if n.id==opponent and n.realm_index==game.player.realm_index),None)
            if not npc:raise ValueError('须选择当面、自由且同境界的原参会人')
        materials=bundle(game) if kind=='supply' else {}
        if kind=='supply' and not materials:raise ValueError('本地没有完整的会办材料目录')
        market=local_market(game)
        goods_value=sum(quote(market['commodities'][k],'sell',n)['total'] for k,n in materials.items())
        prize=10000;reserved=prize+goods_value
        if balance(game,YAOCHI)<reserved:raise ValueError('瑶池原府库不足，不能发布无款赛事')
        spend(game,20)
        s=game.yaochi_state.setdefault('westward',{}).setdefault('fair',{})
        r=dict(id=f"fair-{cycle(game)}-{kind}",cycle=cycle(game),kind=kind,realm=game.player.realm_index,
            opponent=opponent if kind!='supply' else None,status='active',started=game.player.age,deadline=deadline,
            years=5,progress=0,materials=materials,goods_value=goods_value,prize=prize,
            wallet=f'fair:{game.id}:{cycle(game)}:{kind}')
        account(game,r['wallet']);transfer_value(game,YAOCHI,r['wallet'],reserved,'仙会奖金与会办采购原款托管')
        s.setdefault('entries',[]).append(r);summary='已报名'+NAMES[kind]+'；实际筹备五年，同届不能重报。'
    elif action=='fair_work':
        begin(game);return deps.advance(game.id,'yaochi_fair',1)
    elif action=='fair_cancel':
        if not r:raise ValueError('没有在办赛事')
        summary='退赛归档；报名功勋及已耗年份不退，同届不重开。';settle(game,r,False,summary)
    elif action in {'fair_fight','fair_deliver'}:
        if blocked:=work_reason(game):raise ValueError(blocked)
        if r['progress']<r['years']:raise ValueError('须完成五年实际筹备')
        if action=='fair_deliver':
            if r['kind']!='supply':raise ValueError('该项不是资材会办')
            held={i.id:i.quantity for i in game.player.inventory}
            if any(held.get(k,0)<n for k,n in r['materials'].items()):raise ValueError('会办材料尚未齐备，可从原产业提货或市场采购')
            market=local_market(game)
            if not market or any(k not in market['commodities'] for k in r['materials']):raise ValueError('原接收市场失效')
            for k,n in r['materials'].items():
                remove_item(game.player,k,n);market['commodities'][k]['stock']+=n;reprice(game,market,market['commodities'][k])
            transfer_value(game,r['wallet'],'player',r['goods_value'],'仙会按登记价收购实交材料')
            r['delivered']=copy.deepcopy(r['materials']);success=True
            summary=f"会办履约完成，实际用时{game.player.age-r['started']}年；货款{r['goods_value']}、奖金{r['prize']}灵石。"
        else:
            if r['kind']=='supply':raise ValueError('资材会办不进行战斗')
            if r['kind']=='guard':
                from .formation_system import active_formation_profile
                if not active_formation_profile(game.player).get('active'):raise ValueError('护阵须先在原阵法页配置有效随身阵法')
                if value not in {'hold','break'}:raise ValueError('请选择稳守四轮或破敌护阵')
            from .mentorship_advanced import battle_target
            target=battle_target(find_person(game,r['opponent']),deps._npc_power)
            target.update(single_combat=True,objective='repel',max_rounds=4 if value=='hold' else 6)
            previous_report=game.last_combat_report
            rng=decode_rng(game.seed,game.rng_state);outcome,report=deps._combat(game,target,False,rng);game.rng_state=encode_rng(rng)
            battle=(game.last_combat_report or {}) if game.last_combat_report is not previous_report else {}
            rounds=battle.get('rounds',[])
            integrity=battle.get('formation_integrity_end')
            success=outcome=='victory'
            if r['kind']=='guard':
                success=bool(integrity is not None and integrity >= (.5 if value=='hold' else .7)
                    and (outcome=='victory' or value=='hold' and battle.get('outcome')=='stalemate' and len(rounds)>=4 and rounds[-1].get('player_hp_ratio',0)>.3))
            r['battle']=dict(outcome=outcome,rounds=len(rounds),integrity=integrity,plan=value,summary=report)
            summary=('达标获奖' if success else '未达成赛事目标')+'；'+report
        settle(game,r,success,summary)
    else:raise ValueError('未知仙会事务')
    game.history.append(HistoryRecord('SYS_YAOCHI_FAIR',1,game.player.age,'瑶池仙会',action,'completed',summary,{},['yaochi','fair']))
    game.updated_at=now_iso();deps.store.save(game);return deps.present(game)

def public(game):
    from .westward_rules import enabled
    if game.player.world!='celestial':return None
    local=game.player.location_id==config()['location_id']
    candidates=people(game) if local else []
    r=copy.deepcopy(active(game));blocked=reason(game)
    return dict(enabled=enabled(),token=token(game) if local else '',cycle=cycle(game),ends=(cycle(game)+1)*500,
        reason=blocked,recovery_reason=reason(game,True),work_reason=work_reason(game),active=r,
        candidates=[dict(id=n.id,name=n.name,realm=n.realm_index,layer=n.layer) for n in candidates if n.realm_index==game.player.realm_index],
        contests=[dict(id=k,name=v,used=any(e['cycle']==cycle(game) and e['kind']==k for e in entries(game))) for k,v in NAMES.items()],
        materials=[dict(id=k,name=ITEM_CATALOG[k].name,quantity=n,held=sum(i.quantity for i in game.player.inventory if i.id==k)) for k,n in (r['materials'] if r else bundle(game) if local else {}).items()],
        history=copy.deepcopy(entries(game)[-6:]),priority=copy.deepcopy(state(game).get('priority')))
