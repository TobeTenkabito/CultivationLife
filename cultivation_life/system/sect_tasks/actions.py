"""Validated local commands; the engine supplies actual combat and commits once."""
from math import ceil
from . import state as s, tasks
from .finance import donate
from ...content_registry import REALMS
from ...rules import add_item
from ..economy import depot
from ..economy.ledger import balance, transfer_value
from ..economy.organization_accounts import register, book_expense
from ..sect_membership import release
from ..intrigue.leadership import appoint


def execute(game,maps,payload,rng,combat,npc_power):
    sect=game.sects.get(game.player.faction_id or '')
    task=next((t for t in s.snapshot(game,sect)['tasks'] if t['id']==payload.get('task_id')),None) if sect else None
    war_task=bool(payload.get('action')=='complete' and task and task['kind']=='mobilize')
    reason=s.blocked(game,sect,at_site=not war_task)
    if reason:raise ValueError(reason)
    board=s.ensure(game,sect)
    if payload.get('owner_id')!=sect.id or type(payload.get('revision')) is not int or payload['revision']!=board['revision']:
        raise ValueError('宗门任务页面已过期，请刷新后重试')
    action=payload.get('action'); rights=s.permissions(game,sect); row=s.record(game,sect)
    q=dict(s.quota(game,sect))
    board['quota']=q
    if action=='donate':
        donate(game,sect,'player',payload.get('amount'))
        return
    if action=='minimum':
        rank=payload.get('realm')
        if not rights['policy']:raise ValueError('只有掌门或控制者可以设置发布境界')
        if type(rank) is not int or not 0<=rank<len(REALMS):raise ValueError('任务发布境界无效')
        board['minimum_realm']=rank
        text=f'最低发布境界调整为{REALMS[rank].name}。'
    elif action=='recruitment':
        if not rights['recruit']:raise ValueError('需要掌门、决策权或控制权')
        value=payload.get('enabled')
        if type(value) is not bool:raise ValueError('招新政策必须明确开启或关闭')
        board['recruitment_open']=value
        if not value:row['pending_recruitment']=None
        text='山门恢复招收新弟子。' if value else '山门暂停招收新弟子，已在册成员保留。'
    elif action=='dismiss':
        if not rights['dismiss'] or not board['arrears'] or row.get('unrest',0)<20:
            raise ValueError('罢免止怨需要决策权，且本宗正欠薪、不满至少20')
        former=s.leader(game,sect)
        if not former:raise ValueError('当前没有可罢免的掌门')
        if board.get('dismissed_crisis_year')==board['salary_year']:
            raise ValueError('本年度危机已经通过罢免掌门平息过')
        successor=payload.get('successor')
        if successor==former:raise ValueError('继任者不能是被罢免者')
        appoint(game,row,sect.npcs,successor)
        board['dismissed_crisis_year']=board['salary_year']
        board['dismissals']+=1
        row['unrest']=max(0.,row.get('unrest',0)-25)
        text=f'罢免现任掌门并任命继任者，不满降低25；今后每次欠薪额外增加{2*board["dismissals"]}不满。'
    elif action=='expel':
        if not rights['expel']:raise ValueError('只有掌门或控制者可以开除弟子')
        identity=payload.get('npc_id')
        npc=next((n for n in sect.npcs if n.id==identity),None)
        if not npc or identity not in s.members(game,sect) or identity=='player':raise ValueError('目标不是本宗在册弟子')
        highest=max(s.members(game,sect),key=lambda k:(s.members(game,sect)[k].realm_index,s.members(game,sect)[k].layer))
        if identity in {s.leader(game,sect),highest} or identity in game.intrigue_state.get('npc_prisons',{}):
            raise ValueError('不能开除现任掌门、实际控制者或在押成员')
        from ...person_assignments import require_unassigned
        require_unassigned(game,identity)
        release(game,sect,row,npc)
        npc.affinity=float(npc.affinity or 0)-30
        row['unrest']=min(100.,row.get('unrest',0)+5)
        text=f'{npc.name}被逐出宗门，不满增加5；其人物状态与个人灵石保留。'
    elif action=='publish':
        if q['posts']>=3:raise ValueError('每行动单位最多发布3项任务')
        tasks.publish(game,sect,'player',payload.get('kind'),payload.get('item'),payload.get('quantity',1),payload.get('war_id'))
        q['posts']+=1
        return
    elif action=='cancel':
        task=next((t for t in board['tasks'] if t['id']==payload.get('task_id')),None)
        if not task or task['issuer']!='player' or task['status']!='open':raise ValueError('只能撤销自己仍待完成的任务')
        task['status']='cancelled'
        text=f'撤销「{task["title"]}」，已消耗的影响力不退还。'
    elif action=='complete':
        task=next((t for t in board['tasks'] if t['id']==payload.get('task_id')),None)
        if not task or not tasks.valid(game,sect,task) or task['issuer']=='player':raise ValueError('任务已失效或不能完成自己的任务')
        if q['completions']>=1:raise ValueError('每行动单位只能完成1项宗门任务')
        if task['kind']=='material':
            if depot.occupied(depot.ensure(game,sect))+task['quantity']>10000:raise ValueError('府库实物容量不足')
            tasks.deliver(game,sect,task,'player')
        else:
            if not tasks.at_front(game,sect,task):raise ValueError('请沿地图前往本场战役驻地，再执行战争动员')
            candidates=tasks.opponents(game,sect,task['war_id'])
            if not candidates:raise ValueError('敌宗没有与你相差三个小境界以内的可战对手')
            npc=rng.choice(candidates)
            target=dict(target_name=npc.name,target_power=npc_power(npc),target_realm_index=npc.realm_index,
                target_layer=npc.layer,combat_type='cultivator',action='repel',enemy_objective='repel',
                max_rounds=8,non_story_combat=True,war_id=task['war_id'],members=[dict(npc_id=npc.id,name=npc.name,
                power=npc_power(npc),realm_index=npc.realm_index,layer=npc.layer,path=npc.path,
                faction_id=npc.faction_id,race=npc.race)])
            result,detail=combat(game,target,True,rng)
            if result=='victory' and game.player.alive and game.player.faction_id==sect.id:
                tasks.finish(game,sect,task,'player')
            else:
                task.update(status='failed',completer='player',completer_name=game.player.name)
                s.note(game,sect,f'战争动员失败：{detail}')
        q['completions']+=1
        return
    elif action=='redeem':
        key=payload.get('item');quantity=payload.get('quantity',1)
        if type(quantity) is not int or not 1<=quantity<=10000:raise ValueError('兑换数量应为1至10000')
        inventory=depot.ensure(game,sect)
        if key=='spirit_stone':
            value=quantity;cost=ceil(value/10)
            if balance(game,depot.treasury(game,sect))<quantity:raise ValueError('府库灵石不足')
        else:
            good=s.ordinary(sect.world).get(key)
            if not good or good['tier']>game.player.realm_index+1:raise ValueError('此物资不可兑换或超出境界')
            if inventory['stock'].get(key,0)<quantity:raise ValueError('府库实物不足')
            value=depot.unit_value(game,inventory,key)*quantity;cost=max(1,ceil(value/10))
        from ...sect_board_rules import can_withdraw
        if not can_withdraw(game,q['value'],value,quantity,item=key!='spirit_stone'):
            raise ValueError('本行动单位兑换额度不足，请推进时间后再来')
        if s.contribution(game,sect,'player')<cost:raise ValueError('宗门贡献不足')
        if key=='spirit_stone':
            transfer_value(game,depot.treasury(game,sect),'player',quantity,'贡献兑换灵石')
            book_expense(game,register(game,'sect',sect.id,sect.world),quantity)
        else:
            inventory['stock'][key]-=quantity
            depot.record(inventory,game,f'贡献兑换：{good["name"]} ×{quantity}')
            add_item(game.player,good['id'],quantity)
        s.merit(game,sect,'player',-cost)
        q['value']+=value
        text=f'贡献兑换支出{cost}贡献，使用本行动单位额度{value}。'
    else:raise ValueError('未知宗门任务操作')
    s.note(game,sect,text)
