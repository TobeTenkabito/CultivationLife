"""Local expedition decisions, evidence and bounded receipts; no offscreen armies."""
import copy
from dataclasses import dataclass
from ...dungeon_schema import empty, decode
from ...content_registry import WORLD_SYSTEMS
from ...rules import max_hp, max_mp, combat_power
from ...reputation import true_rank, record
from ...models import HistoryRecord
from ...runtime import now_iso
from ...soul_rules import wandering
from .generation import generate, config, stream
from .people import materialize, power, pressures, fight, gratitude, available, opposition, team_reason
from .ecology import appearance_depth
from .rewards import grant, learn
from . import expedition, scenes, topography, formations
from .companions import carry, separate


@dataclass(frozen=True)
class Dependencies:
    load: object
    save: object
    present: object
    commit: object
    combat: object
    die: object
    npc_power: object
    maps: object
    activate_loadout: object
    formation_candidates: object


LOCAL_COMMANDS = {'get_game','present','dungeon_action','choose','use_item','equip_known_technique',
    'update_combat_plan','activate_formation','deactivate_formation','update_setting',
    'assert_ghost_operation_allowed','assert_guixu_operation_allowed','assert_buddhist_operation_allowed',
    'assert_building_operation_allowed'}


def guard(game, command):
    if game.dungeon_state.get('active') and command not in LOCAL_COMMANDS:
        raise ValueError('正在副本中，请先脱离当前局势并撤离，再办理外界事务')


def require_actor(game):
    p = game.player
    if not p.alive or wandering(p) or p.realm_index < 1 or p.imprisonment or p.ghost_captor or p.nascent_state.get('crisis'):
        raise ValueError('当前生命、修为或受制状态无法探索副本')
    from ..heavens.local_control import resource_reason
    if reason := resource_reason(game,'dungeon'):
        raise ValueError(reason)
    if game.pending_event or game.active_trial or game.generated_event_state.get('active') or game.trial_site_state.get('active') or game.guixu_state.get('player_session'):
        raise ValueError('请先处理当前事件或探索会话')
    if p.world == 'celestial' and not p.immortal_power_converted:
        raise ValueError('请先完成仙灵力转化')
    if p.world+':'+p.location_id not in config()['profiles']:
        raise ValueError('请返回普通地图后探幽寻宝')


def log(site, text, kind='实证', actors=(), source='亲眼所见'):
    sequence=int(site['logs'][-1]['id'].rsplit(':',1)[1])+1 if site['logs'] else 0
    if len(site['logs'])>=2000:site['logs'].pop(0)
    site['logs'].append(dict(id=site['id']+':log:'+str(sequence), step=site['step'],
        kind=kind, place=('入口','外围','深处','核心')[min(3,site['depth'])], text=text,
        source=source, actors=list(actors)))
    site['last_result'] = text


def label(role):
    names=('凡人','练气','筑基','结丹','元婴','化神','炼虚','合体','大乘','真仙','金仙','太乙','大罗')
    return f"{role['sect_name']}的{names[role['realm']]}修士{role['name']}"


def discover(game, maps):
    p = game.player
    if not game.dungeon_state: game.dungeon_state = empty()
    state=game.dungeon_state; scope=p.world+':'+p.location_id
    ids=state['maps'].setdefault(scope,[])
    if len(ids)>=config()['profiles'][scope]['slots']:
        raise ValueError('当地可探寻的副本次数已用尽')
    site=generate(game,maps.location(p.world,p.location_id),len(ids),len(state['legends'].get(p.world,[])))
    state['text_fingerprints'].extend(node['text'] for node in site['nodes'])
    state['instances'][site['id']]=site;ids.append(site['id'])
    if site['quality']=='legendary':state['legends'].setdefault(p.world,[]).append(site['id'])
    return site


def invite_tick(game, maps):
    """Only invoked by real elapsed time, never by a view/load request."""
    try: require_actor(game)
    except ValueError: return
    if game.dungeon_state.get('active'):return
    p=game.player;scope=p.world+':'+p.location_id
    if not game.dungeon_state:game.dungeon_state=empty()
    state=game.dungeon_state
    unit=int(WORLD_SYSTEMS['time_units'][str(true_rank(p)[0])]);mark=int(p.age//unit)
    if state['invite_marks'].get(scope)==mark:return
    state['invite_marks'][scope]=mark
    rng=stream(game.seed,scope,'invitation',mark)
    from ...reputation import assess
    chance=config()['invitation_chance']*min(2.5,.6+assess(p,visible=True)['value']/200)
    if rng.random()>=chance:return
    try:site=discover(game,maps)
    except ValueError:return
    role=next((r for r in site['roles'].values() if not team_reason(game,r)),None)
    if role is None:return
    role.update(known=True,state='invited')
    site['initiator']=role['id']
    state['mail'].append(dict(id=site['id']+':invitation',dungeon_id=site['id'],
        sender=role['name'],sender_id=role['id'],title='邀你同探一处隐境',
        body=f"我在{maps.location(p.world,p.location_id)['name']}发现一处入口，愿邀道友同行。{role['story']}。内中情形尚待探明。",
        unread=True,status='pending',age=p.age))


def close(game, site, text):
    formations.close_arrays(game,site,log)
    for key,contract in site.get('expedition',{}).get('contracts',{}).items():
        if contract['state']=='promised':
            contract['state']='broken'
            role=site['roles'][key];role['trust']=max(0,role['trust']-15)
            log(site,'离开时与'+role['name']+'的交付约定仍未完成，履约记录已注明。',actors=[key])
    for key in site['party']:
        role=site['roles'][key];role.update(state='left',left_step=site['step'])
    if 'space' in site:site['space']['chase']=None
    site['party']=[];site['pending']=None;site['status']='closed'
    game.dungeon_state['active']=None
    game.dungeon_state['ready_age']=max(game.dungeon_state['ready_age'],game.player.age+site['unit'])
    log(site,text)
    game.history.append(HistoryRecord(site['id'],1,game.player.age,'探幽寻宝','exit','resolved',text,{},['dungeon']))


def claim(game,site,node):
    identity=node['reward']['id']
    if identity in site['claims']:return
    text=grant(game,node['reward']);site['claims'].append(identity);log(site,text)
    for key in site['party']:
        site['roles'][key]['desire']=min(100,site['roles'][key]['desire']+4)
    if node['kind']=='core':record(game.player,site['id']+':core',{'ordinary':3,'rare':8,'epic':20,'legendary':45}[site['quality']],'探境所得')


def contact(game,site,role):
    if not available(game,site,role):
        mark_absent(site,role)
        return False
    role['ledger']['encounter_step']=site['step']
    if team_reason(game,role):
        role.update(known=True,state='observed')
        log(site,label(role)+'从岔路经过，独自向前探去。',actors=[role['id']])
        return False
    role.update(known=True,state='contact')
    log(site,label(role)+'在岔路停步，提出结伴。'+role['story']+'。',actors=[role['id']])
    site['pending']={'kind':'join','actor':role['id']}
    return True


def mark_absent(site,role):
    if role['id'] in site['party']:site['party'].remove(role['id'])
    if role['state'] in {'missing','dead'}:return
    role.update(state='missing',known=True)
    log(site,role['name']+'没有按约出现，已无法参与眼前行动。约定的地方只剩一枚熄灭的传讯符。',actors=[role['id']])


def offer_invited(game,site):
    for role in site['roles'].values():
        if role['state']=='invited':
            contact(game,site,role)
            if site['pending']:break


def reveal_local_support(game,site):
    pending=site['pending']
    if not pending or pending['kind'] not in {'guardian','ambush','conflict'}:return
    leaders=[pending['actor']]+([pending['other']] if pending['kind']=='conflict' else [])
    for key in leaders:
        leader=site['roles'][key]
        newcomers=[r for r in opposition(game,site,leader)[1:] if not r['known']]
        for role in newcomers:role.update(known=True,state='contact')
        if newcomers:
            log(site,'你看见'+leader['name']+'身侧还有'+ '、'.join(label(r) for r in newcomers)+'，正彼此掩护。',actors=[r['id'] for r in newcomers])


def background(site):
    if site['quality'] not in {'epic','legendary'}:return
    if expedition.news(site,log,label) or 'space' in site:return
    rng=stream(site['seed'],'news',site['step'])
    a,b=rng.sample(list(site['roles'].values()),2)
    # These are reports, not authoritative changes to instantiated world people.
    if site['depth']<2:
        log(site,f"听说在{rng.choice(('东','西','南','北'))}方有灵力波动，杀气重重，想来是有不得了的人物在交手。",'听说',source='远处传言')
    else:
        outcome=rng.choice(('重伤退走','丢下阵旗败退','折损数名同门')) if site['quality']=='epic' else rng.choice(('死伤惨重，余众四散','多人陨落，山谷被夷平','护阵尽毁，几乎无人全身而退'))
        log(site,f"据说{label(a)}所代表的一方与{label(b)}一方争夺阵枢，前者{outcome}。",'据说',source='撤离修士转述')


def advance_scene(game,site):
    site['depth']=min(3,site['step']*4//len(site['nodes']))
    background(site)
    for key in list(site['party']):
        role=site['roles'][key]
        if not available(game,site,role):
            mark_absent(site,role);separate(game,role);continue
        if role['ledger'].get('outside_party'):continue
        if role['ledger'].get('conduct_step')==site['step']:continue
        role['ledger']['conduct_step']=site['step']
        if expedition.conduct(game,site,role,log):continue
        role['preparation']=min(100,role['preparation']+12)
        rng=stream(site['seed'],key,'conduct',site['step'])
        facts=pressures(game,site,role)
        if facts['risk']>72 and role['preparation']>=65 and facts['ratio']>.6:
            role.update(revealed=True,state='hostile');site['party'].remove(key)
            log(site,label(role)+'忽然封住你的退路，祭出杀招。此前的同行约定已被撕毁。',actors=[key])
            site['pending']={'kind':'ambush','actor':key};return
        if rng.random()<.55:
            metric=rng.choice(('desire','preparation','trust'))
            from .prose import OBSERVATIONS
            clue=rng.choice(OBSERVATIONS[metric])
            # Store only what this encounter permits the player to infer.
            expedition.observe(site,role,metric,clue,35,65,log)
        if site['step']>=3 and role['purpose']!='assassinate' and rng.random()<.22:
            role.update(state='left',left_step=site['step']);site['party'].remove(key)
            log(site,role['name']+'称另有要事，退出队伍，沿侧路离去。脚步声渐渐隐入回廊深处。',actors=[key])
    if len(site['party'])>=2 and site['step']>=2:
        a,b=(site['roles'][key] for key in site['party'][:2])
        rng=stream(site['seed'],'party_dispute',site['step'])
        rivalry=pressures(game,site,a,opponent=b)
        if rivalry['risk']>=50 and rivalry['ratio']>.5 and rng.random()<min(.7,rivalry['risk']/150):
            log(site,label(a)+'忽然截下'+b['name']+'的去路，索要刚发现的遗物；两人翻脸相向。',actors=[a['id'],b['id']])
            site['pending']={'kind':'conflict','actor':a['id'],'other':b['id'],'aftermath':True};return
    for role in site['roles'].values():
        if (role['state'] in {'unseen','observed'} and role['offer_step']<=site['step']<len(site['nodes'])
                and topography.present(site,role['id']) and appearance_depth(site,role)<=site['depth'] and not team_reason(game,role)):
            contact(game,site,role)
            if site['pending']:return


def resolve_node(deps,game,site,choice):
    if site['step']>=len(site['nodes']):raise ValueError('已到探索尽头，请撤离')
    if site['step'] in site.get('space',{}).get('cleared',[]):raise ValueError('此地已经探过，请另选方位')
    node=site['nodes'][site['step']];role=topography.local_actor(game,site,node)
    rng=stream(site['seed'],node['id'],choice)
    if choice=='detour':
        origin=site['step'];expedition.detour(game,site,log)
        after_travel(deps,game,site,origin,completed=True);return
    if choice=='survey':
        if node['id'] in site['branches']:raise ValueError('这一处已经勘察')
        cost=max_mp(game.player)*.04
        if game.player.mp<cost:raise ValueError('法力不足以勘察')
        game.player.mp-=cost;site['branches'].append(node['id']);site['preparations']+=1
        for key in site['party']:site['roles'][key]['trust']=min(100,site['roles'][key]['trust']+3)
        log(site,'你辨出阵势'+('向内收束，正面冲入容易受创。' if node['variant']%2 else '向外散逸，借势破阵或能取得遗物。'))
        route=site.get('expedition',{}).get('routes',{}).get(node['id'])
        if route:log(site,'你发现'+route['direction']+'可以绕行，另一头接着前面的石径。')
        return
    tactic=scenes.tactic(node,choice)
    if choice not in {'seize','bypass'} and not tactic:raise ValueError('不存在的探索选择')
    if tactic:
        if node['id'] not in site['branches']:raise ValueError('请先勘察此处阵势')
        cost=max_mp(game.player)*tactic[1]
        if game.player.mp<cost:raise ValueError('请准备足够法力再处理阵势')
        game.player.mp-=cost
        log(site,f'你{tactic[3]}，消耗 {cost:g} 点法力。')
    log(site,node['text'])
    if choice=='seize' or tactic:
        present=role is not None and available(game,site,role)
        if role and not present:mark_absent(site,role)
        contested=(site['quality']=='legendary' or site['quality']=='epic' and rng.random()<.55)
        if present and contested and node['kind'] in {'seal','cache','hazard'} and role['state'] not in {'dead','left','declined','joined'}:
            role.update(known=True,state='hostile')
            log(site,label(role)+'正守在遗物附近。你一接近，对方立刻展开封锁，争夺已无法悄然进行。',actors=[role['id']])
            site['pending']={'kind':'guardian','actor':role['id']};return
        if present and node['kind']=='conflict' and role['state'] not in {'dead','left','declined','joined'}:
            others=[r for r in site['roles'].values() if r['id']!=role['id']
                and topography.present(site,r['id']) and r['state'] in {'unseen','observed'} and appearance_depth(site,r)<=site['depth'] and available(game,site,r)]
            other=min(others,key=lambda r:abs(r['realm']-role['realm']),default=None)
            if other:
                role.update(known=True,state='contact');other.update(known=True,state='contact')
                log(site,label(role)+'与'+label(other)+'争抢同一件遗物，双方已经动手。',actors=[role['id'],other['id']])
                site['pending']={'kind':'conflict','actor':role['id'],'other':other['id']};return
        if present and node['kind']=='contact' and role['state'] in {'unseen','observed'}:
            if contact(game,site,role):return
        if present and node['kind']=='core' and role['state'] not in {'dead','joined'}:
            role.update(known=True,state='hostile',revealed=True)
            log(site,label(role)+'拦住核心入口，要你交出此前所得。',actors=[role['id']])
            site['pending']={'kind':'guardian','actor':role['id']};return
        risk=node['risk']*(.4 if node['id'] in site['branches'] and node['variant']%2==0 else 1)
        if tactic:risk*=tactic[2]
        elif node.get('mechanism')=='volatile':risk=min(1,risk*1.4)
        if node['kind'] in {'seal','hazard','core'}:
            # Environmental damage uses the original death/soul consequence path.
            damage=max_hp(game.player)*risk
            game.player.hp=max(0,game.player.hp-damage)
            if game.player.hp<=0:
                deps.die(game,'副本阵势反噬','SYS_DUNGEON_HAZARD',death_cause='ordinary')
            log(site,f'阵势反噬，受到 {damage:.0f} 点伤害。' if damage else '阵光沿拆开的缺口散尽，你稳稳走过石台。')
        if game.player.alive and not wandering(game.player) and not game.player.nascent_state.get('crisis'):claim(game,site,node)
    else:log(site,'你绕开此处，没有取得这里的遗物。')
    site['node_history'].append({'id':node['id'],'choice':choice});site['step']+=1
    if not game.player.alive or wandering(game.player) or game.player.nascent_state.get('crisis') or game.player.imprisonment or game.player.ghost_captor:
        close(game,site,'探境被迫中断，已取得的物品依照现有生死与拘禁规则处理。');return
    after_travel(deps,game,site,site['step']-1,completed=True)


def after_travel(deps,game,site,origin,*,completed=False):
    if 'space' in site:
        space=site['space']
        if completed and origin not in space['cleared']:space['cleared'].append(origin)
        dest=topography.here(site)
        revisited=dest in space['visited']
        if origin!=dest:
            topography.arrive(game,site,origin,dest)
            topography.encounter_snare(deps,game,site,log,close)
            if site['status']!='active':return
        if space['chase']:
            background(site)
            topography.pursuit(game,site,log)
            return
        if revisited and not completed:
            background(site)
            return
    advance_scene(game,site)


def resolve_pending(deps,game,site,choice):
    pending=site['pending'];role=site['roles'][pending['actor']]
    allowed={'join':{'accept','decline'},'conflict':{'support_actor','support_other','flee'},
             'guardian':{'fight','flee'},'ambush':{'fight','flee'},'settlement':{'part','ask_join'}}
    if choice=='flee' and pending.get('intercepted'):raise ValueError('追兵已经截住去路')
    if choice not in allowed[pending['kind']]:raise ValueError('当前局势没有这个选项')
    if choice in {'accept','ask_join'}:
        if reason:=team_reason(game,role):raise ValueError(reason)
    participants=[role]+([site['roles'][pending['other']]] if pending['kind']=='conflict' else [])
    absent=[r for r in participants if not available(game,site,r)]
    if absent:
        for r in absent:mark_absent(site,r)
        site['pending']=None
        log(site,'原先的交涉已无法继续，你重新查看眼前局势。')
        if pending['kind']=='join':offer_invited(game,site)
        return
    if pending['kind']=='settlement':
        ex=site['expedition']
        site['pending']=None
        facts=pressures(game,site,role)
        # Helping is a fact, not immunity. The survivor can still turn on the player.
        if role['id'] not in ex['settlements']:
            ex['settlements'].append(role['id'])
            if facts['risk']>72 and facts['ratio']>.6:
                role.update(state='hostile',revealed=True)
                if role['id'] in site['party']:site['party'].remove(role['id'])
                log(site,role['name']+'忽然改口索要你的全部所得，封住退路，出手相逼。',actors=[role['id']])
                site['pending']=dict(kind='ambush',actor=role['id']);return
        if choice=='ask_join' and role['id'] not in site['party']:
            if len(site['party'])>=config()['max_team']-1:raise ValueError('同行队伍已满')
            role.update(state='joined',joined_step=site['step']);site['party'].append(role['id'])
            log(site,role['name']+'应下继续同行的提议。',actors=[role['id']])
        elif choice=='part':
            separate(game,role)
            if role['id'] in site['party']:site['party'].remove(role['id'])
            role.update(state='left',left_step=site['step'])
            log(site,'你与'+role['name']+'当面分道，各自收拢所得。',actors=[role['id']])
        advance_scene(game,site);return
    if pending['kind']=='join':
        if choice not in {'accept','decline'}:raise ValueError('请接受或谢绝结伴')
        if choice=='accept':
            if len(site['party'])>=config()['max_team']-1:raise ValueError('同行队伍已满')
            materialize(game,site,role);role.update(state='joined',joined_step=site['step'])
            site['party'].append(role['id']);log(site,role['name']+'加入队伍。他收拢衣袖，跟上了众人的脚步。',actors=[role['id']])
        else:role['state']='declined';log(site,'你谢绝了'+role['name']+'的同行请求。',actors=[role['id']])
        site['pending']=None
        offer_invited(game,site)
        return
    enemy=role;ally=None
    if choice=='flee':
        enemies=opposition(game,site,enemy)
        if pending['kind']=='conflict':enemies+=opposition(game,site,site['roles'][pending['other']])
        enemies=list({r['id']:r for r in enemies}.values())
        topography.start_chase(game,site,[r['id'] for r in enemies],log)
        return
    elif pending['kind']=='conflict':
        if choice not in {'support_actor','support_other'}:raise ValueError('请选择援助一方或脱身')
        other=site['roles'][pending['other']]
        ally,enemy=(role,other) if choice=='support_actor' else (other,role)
    elif choice!='fight':raise ValueError('请迎战或尝试脱身')
    for key in list(site['party']):
        if not available(game,site,site['roles'][key]):mark_absent(site,site['roles'][key])
    allies=[site['roles'][key] for key in site['party'] if key!=enemy['id']]
    if ally:allies.extend(opposition(game,site,ally))
    allies=list({r['id']:r for r in allies if r['id']!=enemy['id']}.values())
    weaker=False
    if ally:
        own_side=[r for r in opposition(game,site,ally) if r['id']!=enemy['id']]
        their_side=[r for r in opposition(game,site,enemy) if r['id'] not in {a['id'] for a in allies}]
        weaker=sum(deps.npc_power(materialize(game,site,r)) for r in own_side)<sum(deps.npc_power(materialize(game,site,r)) for r in their_side)
    expedition.witnessed(game,site,[enemy['id']]+[r['id'] for r in allies])
    ambush = bool(pending.get('snared') and formations.local_field(game))
    outcome,text = fight(deps,game,site,enemy,allies,attack=ambush)
    log(site,text,actors=[enemy['id']]+([ally['id']] if ally else []))
    site['pending']=None
    if (outcome not in {'victory','killed','victory_escape','victory_controlled'} or not game.player.alive
            or wandering(game.player) or game.player.nascent_state.get('crisis') or game.player.imprisonment or game.player.ghost_captor):
        close(game,site,'你未能继续深入，探境结束。');return
    enemy['state']='dead' if enemy['state']=='dead' else 'left'
    separate(game,enemy)
    if enemy['id'] in site['party']:site['party'].remove(enemy['id'])
    if pending['kind'] in {'conflict','guardian'} and not pending.get('aftermath'):
        node=site['nodes'][site['step']];claim(game,site,node)
        if ally and available(game,site,ally):
            gratitude(game,ally,25 if weaker else 10)
            record(game.player,site['id']+':help:'+ally['id'],5,'争夺中援助同道')
            if weaker:
                # One extra, already frozen adjacent cache; cannot duplicate a receipt.
                bonus=next((r for r in site.get('expedition',{}).get('bonuses',[]) if r['id'] not in site['claims']),None)
                if bonus:
                    claim(game,site,dict(kind='bonus',reward=bonus));site['expedition']['bonus_claims'].append(bonus['id'])
                    log(site,ally['name']+'感谢你援助弱势一方，将所得中的另一份也交给你。')
            log(site,f"{label(ally)}在与{label(enemy)}的争夺中胜出，{node['reward']['name']}最后由你取得。",actors=[ally['id'],enemy['id']])
        site['step']+=1
        if 'space' in site:
            space=site['space'];origin=site['step']-1
            if origin not in space['cleared']:space['cleared'].append(origin)
            if site['step']<len(site['nodes']):
                topography.arrive(game,site,origin,site['step'])
                topography.encounter_snare(deps,game,site,log,close)
                if site['status']!='active':return
    elif ally and available(game,site,ally):
        gratitude(game,ally,20)
        if weaker:
            bonus=next((r for r in site.get('expedition',{}).get('bonuses',[]) if r['id'] not in site['claims']),None)
            if bonus:
                claim(game,site,dict(kind='bonus',reward=bonus));site['expedition']['bonus_claims'].append(bonus['id'])
                log(site,ally['name']+'将另一份所得交给你，感谢你出手相助。')
    if site.get('expedition'):
        site['expedition']['performance']['wins']+=1
        if ally and available(game,site,ally):
            site['expedition']['performance']['helped']+=1
            if 'space' in site:site['space']['positions'][ally['id']]=topography.here(site)
            site['pending']=dict(kind='settlement',actor=ally['id'])
            log(site,'战局暂定，'+ally['name']+'跟了上来，想问问你往后怎么走。',actors=[ally['id']]);return
    advance_scene(game,site)


def command(deps,game_id,action,payload):
    allowed={'action','dungeon_id','revision','choice','actor_id','mail_id','manual_id','world','location_id','slot'}
    if action=='ward':allowed.add('loadout_id')
    if action=='ask_location':allowed={'action','actor_id','world','expected_age'}
    if not isinstance(payload,dict) or set(payload)-allowed or payload.get('action',action)!=action:
        raise ValueError('副本仅接受玩家操作，不接受覆盖隐藏参数')
    game=copy.deepcopy(deps.load(game_id));state=game.dungeon_state
    if action=='ask_location':
        from ..npc_whereabouts import send_reply
        send_reply(game, payload.get('actor_id'), payload.get('world'), payload.get('expected_age'))
    elif action=='read_mail':
        mail=next((m for m in state.get('mail',[]) if m['id']==payload.get('mail_id')),None)
        if mail is None:raise ValueError('来信不存在')
        mail['unread']=False
    else:
        require_actor(game)
        if action=='discover':
            if state.get('active'):raise ValueError('请先结束当前副本')
            scope=game.player.world+':'+game.player.location_id
            if (payload.get('world'),payload.get('location_id'),payload.get('slot'))!=(game.player.world,game.player.location_id,len(state.get('maps',{}).get(scope,[]))):
                raise ValueError('地图或探寻次数已变化，请刷新后操作')
            discover(game,deps.maps)
        elif action in {'learn','study'}:
            if state.get('active'):raise ValueError('请撤离后研习传承')
            if action=='learn':learn(game,payload.get('manual_id'))
            else:
                from .study import start
                start(game,payload.get('manual_id'))
        else:
            site=state.get('instances',{}).get(payload.get('dungeon_id'))
            if site is None or type(payload.get('revision')) is not int or payload['revision']!=site['revision']:
                raise ValueError('副本页面已过期，请查看当前局势')
            if (site['world'],site['location_id'])!=(game.player.world,game.player.location_id):raise ValueError('必须实际抵达副本所在地图')
            if site['status']=='active' or action=='enter':topography.restore_map(site)
            if action=='invite':
                if state['active'] or site['status']!='open':raise ValueError('请在入境前发出同行邀请')
                from .people import invite
                invite(game,site,payload.get('actor_id'))
            elif action=='enter':
                if state['active'] or site['status']!='open' or site['entered']:raise ValueError('此副本已进入或已经结束')
                if game.player.age<state['ready_age']:raise ValueError('刚刚退出副本，尚需度过一个完整行动单位')
                site.update(status='active',entered=True,unit=int(WORLD_SYSTEMS['time_units'][str(true_rank(game.player)[0])]))
                state['active']=site['id'];log(site,'你跨过入口，停下脚步，听了听四周的动静。')
                if 'space' in site:
                    for key,role in site['roles'].items():
                        if role['state']=='invited':site['space']['positions'][key]=0
                carry(game,site,log)
                offer_invited(game,site)
                for mail in state['mail']:
                    if mail.get('dungeon_id')==site['id']:mail.update(status='accepted',unread=False)
            elif action=='decline_invite':
                if site['status']!='open':raise ValueError('邀请已失效')
                site['status']='closed'
                for mail in state['mail']:
                    if mail.get('dungeon_id')==site['id']:mail.update(status='declined',unread=False)
            else:
                if state['active']!=site['id'] or site['status']!='active':raise ValueError('当前未在此副本中')
                space=site.get('space')
                if space and space['chase'] and action!='move':raise ValueError('追兵将至，请先选择遁行方位')
                if action=='move':
                    if not space or site['pending']:raise ValueError('须先处置眼前局势')
                    origin=topography.here(site)
                    dest=topography.exits(space,origin).get(payload.get('choice'))
                    if dest is None:raise ValueError('此方向没有通路')
                    site['step']=dest
                    after_travel(deps,game,site,origin)
                elif action=='ward':
                    if not space:raise ValueError('此处无法布阵')
                    formations.place(game,site,payload.get('loadout_id'),deps,log)
                elif action=='withdraw_ward':
                    formations.withdraw(game,site,log)
                elif action=='exit':
                    if site['pending'] and site['pending']['kind']!='join':raise ValueError('正在争斗，须先尝试脱身')
                    close(game,site,'你收拢所得，沿原路退出副本。')
                elif action=='choose':
                    if site['pending']:resolve_pending(deps,game,site,payload.get('choice'))
                    else:resolve_node(deps,game,site,payload.get('choice'))
                elif action=='slay':
                    from .encounters import slay
                    slay(deps,game,site,payload.get('actor_id'),log,close,offer_invited)
                elif action=='bargain':
                    role=site['roles'].get(payload.get('actor_id'))
                    if not role or not available(game,site,role):raise ValueError('交涉对象已不在场')
                    expedition.bargain(game,site,role,payload.get('choice'),log)
                elif action=='pact':
                    role=site['roles'].get(payload.get('actor_id'))
                    if not role or role['id'] not in site['party'] or site['pending'] or not available(game,site,role):raise ValueError('当前无法与此人约定')
                    if role['id'] in site['agreements']:raise ValueError('已经达成约定')
                    site['agreements'][role['id']]=1;role['trust']=min(100,role['trust']+10)
                    log(site,'你与'+role['name']+'约定互相掩护。对方拱手应下，目光扫过前方岔路。',actors=[role['id']])
                else:raise ValueError('未知副本操作')
            reveal_local_support(game,site)
            from .encounters import reveal
            reveal(game,site,log,label)
            site['revision']+=1
    game.dungeon_state=decode(game.dungeon_state)
    game.updated_at=now_iso();deps.save(game);deps.commit(game)
    return deps.present(game)
