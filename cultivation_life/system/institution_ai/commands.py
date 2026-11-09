"""Shared local controls; adapters provide scope authority and actual delivery."""
import copy
from . import rules,runtime
from ...relationship_records import find_person
from ..economy.ledger import balance,transfer_value
from ..economy.local_market import require_access,trade_available

def public(game,maps,adapter):
    if game.player.world in {'lost','rift'}:return []
    rows=[]
    for scope in adapter.scopes(game,maps):
        if scope['world']!=game.player.world or scope['location']!=game.player.location_id:continue
        if not scope['controlled']:continue
        record=rules.record(game,scope['id']);offers=adapter.offers(game,maps,scope)
        people=[]
        for identity in scope['people']:
            n=find_person(game,identity)
            if n and not rules.person_reason(game,identity,scope['world'],scope['location'],assignment='institution-delegate:'+scope['id']):people.append(dict(id=identity,name=n.name))
        rows.append(dict(id=scope['id'],name=scope['name'],kind=scope['kind'],token=rules.token(game,scope,offers),
            controlled=scope['controlled'],can_act=trade_available(game) and scope['controlled'],available=scope['available'],reserve=scope.get('reserve',0),
            policy=record.get('policy','balanced'),limit=record.get('limit',0),automatic=record.get('automatic',False),delegate=record.get('delegate'),
            people=people,offers=offers,proposals=copy.deepcopy(record.get('proposals',[])),job=copy.deepcopy(record.get('job')),
            history=copy.deepcopy(record.get('history',[])[-4:])))
    return rows

def command(game,maps,payload,adapter):
    require_access(game)
    scope=next((s for s in adapter.scopes(game,maps) if s['id']==payload.get('scope')),None)
    if not scope or not scope['controlled']:raise ValueError('没有原机构或产业的管理权限')
    if scope['world']!=game.player.world or scope['location']!=game.player.location_id:raise ValueError('须亲赴原机构所在地办理')
    offers=adapter.offers(game,maps,scope)
    if payload.get('token')!=rules.token(game,scope,offers):raise ValueError('机构事务、人员或报价已变化，请刷新')
    action=payload.get('action');row=rules.ensure(game,scope['id']);job=row.get('job')
    if action=='institution_configure':
        policy=payload.get('policy');limit=payload.get('limit');automatic=payload.get('automatic');person=payload.get('person')
        if not isinstance(policy,str) or policy not in rules.POLICIES or type(limit) is not int or not 0<=limit<=10**15 or type(automatic) is not bool:raise ValueError('经营方针或预算授权无效')
        if job:raise ValueError('请先完成或交接当前项目，再更换授权与执事')
        if person:
            if person not in scope['people']:raise ValueError('执行人不属于原机构合格人选')
            if blocked:=rules.person_reason(game,person,scope['world'],scope['location'],assignment='institution-delegate:'+scope['id']):raise ValueError(blocked)
        if automatic and not person:raise ValueError('自动代办须先指定真实执事')
        row.update(policy=policy,limit=limit,automatic=automatic,delegate=person or None,provider=scope['provider'])
    elif action=='institution_start':
        offer=next((o for o in offers if o['key']==payload.get('offer')),None)
        if not offer:raise ValueError('原需求已经消失，请刷新')
        runtime.start(game,scope,offer,payload.get('person'),adapter=adapter)
    elif action=='institution_cancel':
        if not job:raise ValueError('没有在办项目')
        runtime.close(game,scope,row,job,'cancelled','原址交接；已耗工时劳务保留，未耗款退回原付款人。')
    elif action=='institution_fund':
        if not job:raise ValueError('没有在办项目')
        value=payload.get('amount')
        if type(value) is not int or not 1<=value<=scope['available']:raise ValueError('追加额度须为可用原款范围内的整数')
        if game.player.age>=job['deadline']:raise ValueError('逾期项目须交接，不得续期刷工时')
        transfer_value(game,scope['payer'],job['wallet'],value,'机构原项目追加授权')
        job['funded']+=value
    else:raise ValueError('未知机构事务')
    row['revision']+=1
