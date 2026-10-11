"""Local commands, applied to a detached game and committed by the engine."""
from ...monster_civilization_content import validate_state
from . import core


def guard(game):
    from .. import spatial
    p = game.player
    if not core.executable(game):
        raise ValueError('万灵扩展未启用，或存档子版本暂不支持')
    if not p.alive or game.pending_event or game.active_trial or p.imprisonment or p.ghost_captor:
        raise ValueError('请先处理当前事件、试炼或拘禁，再办理当地事务')
    if spatial.current(game) or p.world not in core.config()['worlds']:
        raise ValueError('须身处对应主界的真实栖地')
    if p.location_id not in core.config()['worlds'][p.world]['regions']:
        raise ValueError('此地不是万灵考察栖地，请按原地图前往标记地点')


def cost(game, action):
    tier = {'human': 1, 'monster_realm': 2, 'phantom_underworld': 2, 'nether': 3}.get(game.player.world, 1)
    return {'observe':0, 'protect':5*tier, 'guide':8*tier, 'found':30*tier,
            'join':5*tier, 'leave':0, 'invite':10*tier, 'contest':30*tier, 'law':10*tier,
            'branch':30*tier, 'alliance':10*tier, 'merge':20*tier, 'revive':25*tier, 'regime':30*tier}.get(action)


def observe(game, data):
    region = game.player.location_id
    old = data['observations'].get(region)
    if old and old['year']==game.player.age:
        raise ValueError('本年已考察此地；请待时间推进后再观察变化')
    values = {t: dict(min=max(0, p['p']//50*50), max=(p['p']//50+1)*50,
                       capacity=p['k'], adaptation=p['adaptation'])
              for t, p in data['regions'][region]['populations'].items()}
    trend = list(old.get('trend', [])) if old else []
    trend.append(dict(year=game.player.age, value=sum(v['min'] for v in values.values())))
    data['observations'][region] = dict(year=game.player.age, populations=values, trend=trend[-12:],
                                       case=data['regions'][region]['case'], hunting=data['regions'][region]['hunting'])
    known = data['known_clans']
    for clan in data['clans'].values():
        if clan['home']==region and clan['id'] not in known:
            known.append(clan['id'])
    core.fact(game, game.player.world, 'observation', region, '留下当地生灵数量与栖地状况的考察记录。', [core.PLAYER], 'observed')


def _name(payload, fallback):
    name = payload.get('name', fallback)
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 12 or any(ord(c)<32 for c in name):
        raise ValueError('氏族名称须为一至十二个可见字符')
    return name.strip()


def apply(game, action, payload):
    guard(game)
    if payload.get('expected_world',game.player.world)!=game.player.world or payload.get('expected_location',game.player.location_id)!=game.player.location_id:
        raise ValueError('所在界面或地点已改变，请刷新万灵图志后重试')
    amount = cost(game, action)
    if amount is None:
        raise ValueError('万灵操作不合法')
    if game.player.opportunity < amount:
        raise ValueError(f'需要 {amount} 机缘，当前不足')
    state = game.monster_civilization_state
    if type(payload.get('expected_revision')) is not int or payload['expected_revision'] != state.get('revision', 0):
        raise ValueError('万灵记录已更新，请刷新面板后重试')
    data = core.activate(game)
    p = game.player
    cooldown_key = f'{action}:{p.location_id}'
    if action != 'observe' and data['ecology_clock'] < data['cooldowns'].get(cooldown_key, -1000):
        raise ValueError('此事尚在筹备，请待冷却结束后再办理')
    if action == 'observe':
        observe(game, data)
    elif action in {'protect', 'guide'}:
        if p.location_id not in data['observations']:
            raise ValueError('须先考察此地，再决定护育或疏导')
        unit = min(100, max(1, core.CONTENT_DOCUMENTS['world.json']['systems']['time_units'][str(p.realm_index)]))
        row = data['regions'][p.location_id]
        if row.get('effect') and row['effect']['until'] > data['ecology_clock']:
            raise ValueError('此地已有护育安排，请待其结束后再办理')
        row['effect'] = dict(until=data['ecology_clock']+max(20, unit*2), relief=15 if action=='protect' else 10,
                             kind=action)
        if action == 'guide':
            # Relieve predator pressure through existing adjacency, preserving population.
            populations = row['populations']
            for taxon, pop in populations.items():
                if core.config()['taxa'][taxon]['role']=='predator':
                    pop['adaptation'] = min(3, pop['adaptation']+1)
        core.fact(game, p.world, 'intervention', p.location_id, '立下护育约束，减少猎取压力。' if action=='protect' else '疏导猛兽领地，缓解捕食争夺。', [core.PLAYER], action)
    else:
        _clan_action(game, data, action, payload)
    if amount:
        p.opportunity -= amount
    if action!='observe':
        data['cooldowns'][cooldown_key] = data['ecology_clock'] + (100 if p.world=='nether' else 10)
    game.monster_civilization_state['revision'] += 1
    validate_state(game.monster_civilization_state)


def _clan_action(game, data, action, payload):
    p = game.player
    if p.world=='human' or p.path!='monster':
        raise ValueError('氏族与王庭事务须由妖修在妖界、幻冥界或幽冥界办理')
    clans = data['clans']
    current = clans.get(data['player_clan'])
    target = clans.get(payload.get('target_id'))
    if action=='regime':
        from .court import propose
        propose(game, data, payload.get('target_id'))
        return
    if action=='found':
        if current:
            raise ValueError('已有氏族归属；可按族约建立分支')
        available = 10000-sum(c['share'] for c in clans.values() if c['home']==p.location_id)
        if available < 500:
            raise ValueError('此地既有氏族份额已满，不可重复认领族众')
        clan = core.create_clan(game, p.world, p.location_id, core.PLAYER, _name(payload, p.name+'氏'), share=min(1000, available))
        data['player_clan']=clan['id']; data['known_clans'].append(clan['id'])
        # Read-only linkage. No inferred genetic relationship with other characters.
        from ...content_registry import MONSTER_BLOODLINE_SETTINGS, MONSTER_EVOLUTIONS
        if MONSTER_BLOODLINE_SETTINGS and p.monster_evolution_id in MONSTER_EVOLUTIONS:
            clan['lineage_ref'] = dict(evolution_id=p.monster_evolution_id,
                                       lineage_id=p.monster_custom_lineage_id)
        return
    if action=='join':
        if current or not target or target['status']!='active' or target['home']!=p.location_id or target['id'] not in data['known_clans']:
            raise ValueError('须在当地考察已知氏族，且当前没有其他氏族归属')
        if len(target['members'])>=12:
            raise ValueError('此族的重要成员名册已满')
        target['members'].append(core.PLAYER); data['player_clan']=target['id']
        core.fact(game, p.world, 'membership', p.location_id, f'你加入{target["name"]}，接受现行族约。', [core.PLAYER, target['id']], 'join')
        return
    if action=='revive':
        if current or not target or target['status']!='dormant' or target['home']!=p.location_id:
            raise ValueError('须无氏族归属并身处沉寂氏族的祖地')
        if target['founder_id']!=core.PLAYER and core.PLAYER not in target['members']:
            raise ValueError('没有明确的族籍或创始记录，不能冒认祖源')
        target.update(status='active', leader=core.PLAYER)
        if core.PLAYER not in target['members']: target['members'].append(core.PLAYER)
        data['player_clan']=target['id']
        core.fact(game, p.world, 'revival', p.location_id, f'{target["name"]}重续族约，文化传承复兴。', [core.PLAYER, target['id']], 'verified_member')
        return
    if not current or current['home']!=p.location_id:
        raise ValueError('须前往所属氏族祖地办理')
    if action=='leave':
        current['members'].remove(core.PLAYER); data['player_clan']=None
        if current['leader']==core.PLAYER:
            current['leader']=None
            core.politics(game, p.world, data)
        return
    roster = core.people(game, p.world)
    if action=='contest':
        eligible = core.candidates(game, current, roster)
        if not eligible or eligible[0]!=core.PLAYER:
            raise ValueError('按现行族约，你尚非首位合格继承人')
        current['leader']=core.PLAYER; current['status']='active'
    elif action=='branch':
        if current['share']<1000:
            raise ValueError('本族人口份额不足以立分支')
        new = core.create_clan(game, p.world, p.location_id, core.PLAYER,
                               _name(payload, p.name+'支'), parent=current['id'], share=current['share']//2)
        current['share']-=new['share']; current['members'].remove(core.PLAYER)
        if current['leader']==core.PLAYER: current['leader']=None
        data['player_clan']=new['id']; data['known_clans'].append(new['id'])
        core.politics(game, p.world, data)
        core.fact(game, p.world, 'split', p.location_id, f'{current["name"]}分出{new["name"]}，祖源仍相连。', [core.PLAYER,current['id'],new['id']], 'transferred_share')
    elif current['leader']!=core.PLAYER:
        raise ValueError('此操作须取得族长资格')
    elif action=='law':
        if payload.get('target_id') not in core.LAWS: raise ValueError('族约不合法')
        if payload['target_id']==current['law']: raise ValueError('当前已经采用此族约，无需再次缴付机缘')
        current['law']=payload['target_id']
    elif action=='invite':
        person = roster.get(payload.get('target_id'))
        if not person or person.path!='monster' or person.location_id!=p.location_id or not person.encountered_player or (person.affinity or 0)<50:
            raise ValueError('须邀请已相识、亲近且正在祖地的空闲妖修')
        if len(current['members'])>=12 or any(person.id in c['members'] for c in clans.values()):
            raise ValueError('此人已有氏族归属，或本族名册已满')
        current['members'].append(person.id)
    elif action in {'alliance', 'merge'}:
        if not target or target['id']==current['id'] or target['status']!='active' or target['home']!=p.location_id or target['id'] not in data['known_clans']:
            raise ValueError('须与当地已知、活跃的其他氏族办理')
        if action=='alliance':
            if target['id'] in current['alliances']: raise ValueError('两族已缔盟')
            leader = roster.get(target['leader'])
            if not leader or not leader.encountered_player or (leader.affinity or 0)<50:
                raise ValueError('须先取得对方族长的友善认可')
            current['alliances'].append(target['id']); target['alliances'].append(current['id'])
        else:
            if target['id'] not in current['alliances'] or len(current['members'])+len(target['members'])>12:
                raise ValueError('并族须先缔盟，且重要成员名册不得超限')
            leader=roster.get(target['leader'])
            if not leader or not leader.encountered_player or (leader.affinity or 0)<50:
                raise ValueError('对方族长当前无法认可并族，请先核实继承与盟约')
            current['members'].extend(target['members']); current['share']+=target['share']
            target.update(members=[], share=0, leader=None, status='merged', successor_id=current['id'])
            core.fact(game, p.world, 'merge', p.location_id, f'{target["name"]}并入{current["name"]}，原祖源名录保留。', [core.PLAYER,target['id'],current['id']], 'transferred_members')
    else:
        raise ValueError('氏族操作不合法')
