"""Bounded commissions: transfer ordinary stock, or fight an existing enemy."""
from math import ceil
from .state import ensure, members, ordinary, influence, merit, note, quota, record, active
from .finance import wallet
from ...rules import add_item, remove_item, has_item
from ...npc_custody import is_free
from ..economy import depot
from ..economy.ledger import balance, transfer_value
from ..economy.state import ensure_regional_market, reprice
from ..economy.local_market import quote
from ..economy.market_power import record_trade


def wars(game,sect):
    result=[]
    for war in game.wars:
        if war.get('status')!='active' or war.get('kind')!='sect' or war.get('world')!=sect.world:
            continue
        for side in ('attacker','defender'):
            ids={war.get(side+'_id'),*(r['id'] for r in war.get('coalitions',{}).get(side,[]))}
            if sect.id in ids:
                result.append((war,side))
    return result


def opponents(game,sect,war_id):
    found=next(((w,s) for w,s in wars(game,sect) if w['id']==war_id),None)
    if not found:return []
    war,side=found
    enemy='defender' if side=='attacker' else 'attacker'
    from ..war.requirements import deployed_people
    def minor(n):
        from ...content_registry import REALMS
        return n.realm_index*3+min(2,(n.layer-1)*3//REALMS[n.realm_index].layers)
    return [n for n in deployed_people(game,war,enemy,arrived_only=True)
            if n.world==sect.world and abs(minor(n)-minor(game.player))<=3]


def at_front(game,sect,task):
    return any(w['id']==task['war_id'] and w.get('location_id')==game.player.location_id
               for w,_ in wars(game,sect))


def publish(game,sect,identity,kind,key=None,quantity=1,war_id=None):
    board=ensure(game,sect); people=members(game,sect)
    actor=people.get(identity)
    if identity in game.intrigue_state.get('npc_prisons',{}):raise ValueError('在押成员不能发布任务')
    if actor is None or actor.realm_index<board['minimum_realm']:
        raise ValueError('尚未达到本宗任务发布境界')
    if sum(t['status']=='open' and t['issuer']==identity for t in board['tasks'])>=3:
        raise ValueError('每人最多同时发布3项任务')
    if sum(t['status']=='open' for t in board['tasks'])>=30:
        raise ValueError('任务栏已有30项待办任务')
    if type(quantity) is not int or not 1<=quantity<=100:
        raise ValueError('任务数量应为1至100')
    if kind=='material':
        good=ordinary(sect.world).get(key)
        if not good or good['tier']>actor.realm_index+1:
            raise ValueError('仅可委托本界、境界许可的普通材料')
        reward=max(1,ceil(good['price']*quantity/10))
        title=f'征集{good["name"]} ×{quantity}'
    elif kind=='mobilize':
        if not any(w['id']==war_id for w,_ in wars(game,sect)):
            raise ValueError('宗门当前未参与这场战争')
        reward=20+actor.realm_index*5
        title='战争动员'
        key=None;quantity=1
    else:
        raise ValueError('未知任务类型')
    cost=10+quantity
    if influence(game,sect,identity)<cost:
        raise ValueError(f'发布任务需要{cost}点宗门影响力；履职、完成任务或捐献可获得')
    board['influence'][identity]-=cost
    board['sequence']+=1
    task=dict(id=f'{sect.id}:{board["sequence"]}',issuer=identity,issuer_name=actor.name,
        issuer_join=game.player.faction_join_age if identity=='player' else None,
        completer=None,completer_name=None,kind=kind,item=key,quantity=quantity,war_id=war_id,
        reward=reward,title=title,status='open',year=game.player.age,
        world=sect.world,location=sect.location_id)
    board['tasks']=[t for t in board['tasks'] if t['status']=='open']+[t for t in board['tasks'] if t['status']!='open'][-30:]
    board['tasks'].append(task)
    note(game,sect,f'{actor.name}发布「{title}」，消耗{cost}影响力。')
    return task


def valid(game,sect,task):
    return (task['status']=='open' and task['issuer'] in members(game,sect)
            and task['world']==sect.world and task['location']==sect.location_id
            and (task['issuer']!='player' or task['issuer_join']==game.player.faction_join_age)
            and (task['kind']!='mobilize' or any(w['id']==task['war_id'] for w,_ in wars(game,sect))))


def finish(game,sect,task,identity):
    task.update(status='completed',completer=identity,completer_name=members(game,sect)[identity].name,
                completed_year=game.player.age)
    merit(game,sect,identity,task['reward'])
    board=ensure(game,sect)
    board['influence'][identity]=min(1000,board['influence'].get(identity,0)+3)
    note(game,sect,f'{task["completer_name"]}完成「{task["title"]}」，贡献+{task["reward"]}。')


def deliver(game,sect,task,identity):
    if not valid(game,sect,task) or task['issuer']==identity:
        raise ValueError('任务已失效，或不能完成自己发布的任务')
    good=ordinary(sect.world).get(task['item'])
    if not good:raise ValueError('材料已不可流通')
    if identity=='player':
        if not has_item(game.player,good['id'],task['quantity']):raise ValueError('行囊中的任务材料不足')
        remove_item(game.player,good['id'],task['quantity'])
    else:
        raise ValueError('NPC材料必须通过实际市场交割')
    receive(game,sect,task)
    finish(game,sect,task,identity)


def receive(game,sect,task):
    good=ordinary(sect.world)[task['item']]
    if task['issuer']=='player':
        add_item(game.player,good['id'],task['quantity'])
    else:
        # NPC commissions provision the communal treasury, not shadow inventories.
        row=depot.ensure(game,sect)
        row['stock'][task['item']]=row['stock'].get(task['item'],0)+task['quantity']
        depot.record(row,game,f'任务入库：{task["title"]}')


def npc_complete(game,maps,sect,task,npc):
    if not active(game,sect):return False
    if npc.id in game.intrigue_state.get('npc_prisons',{}):return False
    from ...person_assignments import research_assignment
    if research_assignment(game,npc.id) or (npc.location_id and npc.location_id!=sect.location_id):return False
    if not valid(game,sect,task) or task['issuer']==npc.id:return False
    if task['kind']=='mobilize':
        if task['issuer']!='player':return False
        war,side=next((w,s) for w,s in wars(game,sect) if w['id']==task['war_id'])
        if war.get('sect_mobilization_owner')!=sect.id:
            war['sect_mobilization']={}
        war['sect_mobilization_owner']=sect.id
        buffs=war.setdefault('sect_mobilization',{})
        buffs[side]=min(.10,buffs.get(side,0)+.02)
    else:
        good=ordinary(sect.world).get(task['item'])
        if not good or good['tier']>npc.realm_index+1:return False
        row=depot.ensure(game,sect)
        if task['issuer']!='player' and depot.occupied(row)+task['quantity']>10000:return False
        ensure_regional_market(game,maps,sect.world,row['location'])
        market=game.economy_v2['markets'][f'{sect.world}:{row["location"]}']
        product=market['commodities'].get(good['id'])
        if not product or product['stock']<task['quantity']:return False
        bill=quote(product,'buy',task['quantity'])
        source=wallet(game,npc.id)
        if balance(game,source)<bill['total']:return False
        transfer_value(game,source,f'market:{market["id"]}',bill['total'],'宗门任务购买材料')
        transfer_value(game,f'market:{market["id"]}',f'operator:{market["id"]}',bill['fee'],'宗门任务市场手续费')
        product['stock']-=task['quantity'];product['volume']+=task['quantity']
        market['turnover']+=bill['gross'];market['fees']+=bill['fee']
        record_trade(game,market,good['id'],source,'buy',task['quantity'])
        reprice(game,market,product)
        receive(game,sect,task)
    finish(game,sect,task,npc.id)
    return True


def advance(game,maps,sect):
    if not active(game,sect):return
    board=ensure(game,sect)
    if board.get('tasks_year')==game.player.age:return
    board['tasks_year']=game.player.age
    for task in board['tasks']:
        if task['status']=='open' and not valid(game,sect,task):task['status']='cancelled'
    people=[n for k,n in members(game,sect).items() if k!='player' and k not in game.intrigue_state.get('npc_prisons',{})]
    q=dict(quota(game,sect));board['quota']=q
    # A bounded board, no per-NPC market or per-item simulation.
    for task in list(board['tasks']):
        if q['npc_completions']>=3:break
        for npc in sorted(people,key=lambda n:n.id):
            if npc_complete(game,maps,sect,task,npc):
                q['npc_completions']+=1
                break
    for npc in sorted(people,key=lambda n:(-n.realm_index,n.id))[:3]:
        if sum(t['status']=='open' for t in board['tasks'])>=6:break
        if npc.realm_index<board['minimum_realm'] or influence(game,sect,npc.id)<11:continue
        if any(t['issuer']==npc.id and t['status']=='open' for t in board['tasks']):continue
        engagements=wars(game,sect)
        if engagements and not any(t['kind']=='mobilize' and t['status']=='open' for t in board['tasks']):
            publish(game,sect,npc.id,'mobilize',war_id=engagements[0][0]['id'])
        else:
            goods=[k for k,r in ordinary(sect.world).items() if r['tier']<=npc.realm_index+1]
            if goods:
                index=(game.player.age+len(board['tasks']))%len(goods)
                publish(game,sect,npc.id,'material',goods[index])
