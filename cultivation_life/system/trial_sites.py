"""Static trial sites: causal text decisions, original effects and combat ports."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Callable, Any

from ..trial_site_schema import PREFIX, VERSION, REALM_ROWS, WORLD_TIERS, decode_state
from ..trial_site_generation import location_for, rank_for_floor, generate
from ..content_registry import ITEM_CATALOG, TECHNIQUE_CATALOG, WORLD_SYSTEMS, EXTENSION_REPORT
from ..models import HistoryRecord
from ..rules import expected_combat_power, max_hp, max_mp
from ..runtime import decode_rng, encode_rng, now_iso

# Versioned safe ordinary map candidates, not spatial instances or high-rank hazards.
LOCATIONS = {
    'human': ('wudi_plain', 'muling_desert', 'lanjiang_steppe'),
    'spirit': ('tianyuan_realm', 'thunder_continent', 'mist_sea_isles'),
    'celestial': ('ascension_terrace', 'jade_capital', 'law_sea'),
    'demon': ('gathering_baleful_plain', 'corpse_refining_valley', 'red_marrow_city'),
    'true_demon': ('black_sun_plain', 'bloodflame_range', 'abyss_city'),
    'monster_realm': ('myriad_beast_city', 'ancestral_mountain', 'azure_scale_sea'),
    'phantom_underworld': ('moonbeast_plain', 'myriad_spirit_forest', 'sky_bone_ridge'),
    'hell': ('ghost_gate', 'forgetful_river', 'iron_tree_wastes'),
    'asura': ('asura_gate', 'ten_thousand_battle_city', 'blood_moon_wilds'),
    'nether': ('ancestral_beast_garden', 'world_tree_crown', 'primal_chaos_wilds'),
    'reincarnation': ('reincarnation_well', 'karma_city', 'timeless_grave'),
}
REALM_NAMES = ('凡人', '练气', '筑基', '结丹', '元婴', '化神', '炼虚', '合体', '大乘', '真仙', '金仙', '太乙', '大罗')
LOCAL_COMMANDS = frozenset({
    'get_game', 'present', 'choose', 'trial_site_action', 'use_item', 'equip_known_technique',
    'update_combat_plan', 'activate_formation', 'deactivate_formation', 'update_setting',
    'assert_ghost_operation_allowed', 'assert_guixu_operation_allowed', 'assert_buddhist_operation_allowed',
})


@dataclass(frozen=True)
class TrialDependencies:
    load: Callable
    save: Callable
    present: Callable
    commit: Callable
    combat: Callable
    effect: Callable
    reward_pool: Callable
    maps: Any


def is_trial(event):
    return isinstance(event, dict) and str(event.get('id', '')).startswith(PREFIX)


def enabled():
    return (WORLD_SYSTEMS.get('trial_sites', {}).get('enabled') is True
            and any(row['id'] == 'official.trial-sites' and row['status'] == 'loaded' for row in EXTENSION_REPORT))


def freeze_disabled(game):
    """Detach only a safely pausable session; keep every blueprint and receipt."""
    site, floor = current(game)
    if enabled() or floor is None:
        return False
    if floor['result'] and floor['result']['outcome'] in {'controlled', 'defeat_trapped'}:
        return False
    game.trial_site_state['active'] = None
    floor['revision'] += 1
    return True


def guard(game, command):
    if game.trial_site_state.get('active') and command not in LOCAL_COMMANDS:
        raise ValueError('正在探索万象试境；请先暂停离开，再办理外界事务')


def bound_site(game, maps, world):
    if world not in REALM_ROWS:
        raise ValueError('当前界面尚未开放万象试境')
    if WORLD_SYSTEMS['world_profiles'][world]['tier'] != WORLD_TIERS[world]:
        raise ValueError('试境层序与权威界面等级不匹配')
    saved = game.trial_site_state.get('sites', {}).get(world)
    if saved:
        if saved['location_id'] not in {row['id'] for row in maps.worlds[world]['locations']}:
            raise ValueError('原试境地图已不可用，保留原绑定，不改为默认地点')
        maps.location(world, saved['location_id'])
        return saved
    candidates = set(LOCATIONS[world]) & {row['id'] for row in maps.worlds[world]['locations']}
    location = location_for(game.seed, world, candidates)
    return dict(id='trial:' + world, world=world, location_id=location, floors={}, cleared=0)


def current(game):
    active = game.trial_site_state.get('active')
    if not active:
        return None, None
    site = game.trial_site_state['sites'][active['world']]
    return site, site['floors'][str(active['floor'])]


def require_actor(game, site, *, allow_pending=False):
    p = game.player
    if not p.alive:
        raise ValueError('此生已经结束')
    if (p.world, p.location_id) != (site['world'], site['location_id']):
        raise ValueError('请实际抵达试境所在地图，不能远程挑战')
    if p.realm_index < 1 or p.imprisonment or p.ghost_captor or game.active_trial:
        raise ValueError('当前修持、拘禁或劫关状态不能挑战试境')
    if p.world == 'celestial' and not p.immortal_power_converted:
        raise ValueError('请先完成仙灵力转化，再挑战试境')
    if game.guixu_state.get('player_session') or game.generated_event_state.get('active'):
        raise ValueError('请先完成其他探索会话')
    if game.pending_event and not allow_pending:
        raise ValueError('请先完成待处理事件')


def event_id(floor):
    return f"{floor['id']}_node_{floor['index'] + 1}"


def situation(floor):
    """Compute consequences from saved objects; no outcome RNG or client truth."""
    node = floor['nodes'][floor['index']]
    kind, subject, variant = node['kind'], node['subject'], node['variant']
    positive, active = variant % 2 == 0, variant < 2
    outcomes = {}
    if kind == 'flow':
        direction = '流入守卫，甲片随之亮起' if positive else '从守卫流出，甲片随之黯淡'
        clue = f'{subject}的铜管中灵光{direction}。' if active else f'{subject}旁铜管已有断口；残图标明灵光应当{direction}。'
        outcomes = {
            'a': ('截断铜管', 0.03, 0., dict(supply=False, guard=False, delta=-.12 if positive and active else .12 if active else 0.), '铜管已断；' + ('供能强化已解除。' if positive else '抽能停止，守卫不再损耗灵力。')),
            'b': ('接通铜管', .03, 0., dict(supply=True, guard=positive, delta=.12 if positive and not active else -.12 if not positive and not active else 0.), '铜管接通；' + ('供能恢复，守卫甲胄亮起。' if positive else '抽能回路运转，守卫威能下降。')),
            'c': ('保留当前回路', 0., 0., dict(supply=active, guard=positive and active), '你保留了当前回路，记下灵流方向。'),
        }
        # The initial blueprint's flow orientation must also enter unchanged routes.
    elif kind == 'cooling':
        heating = positive != floor['supply']
        clue = f'{subject}的支路' + ('已把热流送回守卫，刻文提示先疏后封。' if heating else '正在抽取守卫余热，刻文提示引寒应续。')
        clue += '此前铜管' + ('保持接通。' if floor['supply'] else '已被截断，支路流向随之改变。')
        outcomes = {
            'a': ('疏导支路热流', .04, 0. if heating else .04, dict(cooling=True, delta=-.08 if heating else .08), '支路已疏导，' + ('守卫余热散去，威能下降。' if heating else '原抽热关系被破坏，守卫威能恢复。')),
            'b': ('续接引寒支路', .04, .04 if heating else 0., dict(cooling=True, delta=.08 if heating else -.08), '支路已续接，' + ('热流回灌，守卫威能增强。' if heating else '抽热稳定，守卫威能下降。')),
            'c': ('保持支路原状', 0., 0., {}, '支路原状保留。'),
        }
    elif kind == 'seal':
        swollen = positive != floor['cooling']
        clue = f'{subject}后的封匣' + ('向外鼓起，缝隙有灵火喷出；刻着“胀则泄”。' if swollen else '向内闭合，导灵纹失去供给；刻着“枯则充”。')
        clue += '此前' + ('支路处理改变了匣内压力。' if floor['cooling'] else '支路尚未调整。')
        outcomes = {
            'a': ('打开泄压孔', .04, 0. if swollen else .04, {} if swollen else dict(treasure=False, bonus=True), '压力稳定，遗藏保持完好。' if swollen else '处理方向相反，遗藏受损，逸出的灵火强化守卫。'),
            'b': ('补入封匣灵力', .04, .04 if swollen else 0., dict(treasure=False, bonus=True) if swollen else {}, '灵压过盛，遗藏受损，逸出的灵火强化守卫。' if swollen else '供给恢复，遗藏保持完好。'),
            'c': ('放弃关联遗藏，泄去储能', 0., 0., dict(treasure=False, delta=-.1), '你主动放弃关联遗藏，储能泄去，守卫威能降低。'),
        }
    elif kind == 'treasure':
        clue = f'{subject}中的遗藏' + ('仍完好，但保全阵同时护持守卫。' if floor['treasure'] else '已经损毁，尚存的隔离环仍护持守卫；不能恢复已毁遗藏。')
        clue += '刻文说明：拆除隔离环能削弱守卫，投入法力可将护持仅留在遗藏一侧。'
        outcomes = {
            'a': ('拆除隔离环，放弃关联遗藏', 0., 0., dict(treasure=False, guard=False, bonus=False, delta=-.08), '隔离环拆除，关联遗藏不再可得，守卫护持减弱。'),
            'b': ('以自身法力隔离护持', .08, 0., dict(guard=False, bonus=False), '你支付法力，护持与守卫分离；已损毁遗藏仍不能复原。'),
            'c': ('保留护持，承受更强守卫', 0., 0., dict(bonus=True), '护持保留，守卫获得余灵增幅；遗藏状态不变。'),
        }
    else:
        feeds = positive != floor['supply']
        clue = f'{subject}所接阵枢的灵光' + ('流入守卫，供能刻线朝向甲胄。' if feeds else '从守卫流向阵枢，抽能刻线朝向石槽。')
        clue += '此前铜管' + ('仍在运行。' if floor['supply'] else '已断，备用接点承担当前回路。')
        if floor['realm'] >= 9:
            clue += '这也是守卫展开邻域的接点；断开真实供能接点可封停该邻域，普通战力下降不会自行解除金光。'
        outcomes = {
            'a': ('关闭当前刻线接点', .05, 0. if feeds else .04, dict(delta=-.08 if feeds else .08, field=False if feeds else floor['field'], guard=False if feeds else floor['guard']), '真实供能切断，守卫强化解除' + ('，邻域接点封停。' if floor['realm'] >= 9 and feeds else '。') if feeds else '抽能停止，守卫威能恢复；邻域资格没有解除。'),
            'b': ('接通备用刻线接点', .05, .04 if feeds else 0., dict(delta=.08 if feeds else -.08, field=floor['field'] if feeds else False), '供能增强，守卫威能提高。' if feeds else '抽能稳定，守卫威能降低' + ('，邻域接点封停。' if floor['realm'] >= 9 else '。')),
            'c': ('保留当前阵枢', 0., 0., {}, '当前阵枢保留，按已有局势迎战。'),
        }
    return f'{subject} · {kind}', clue, outcomes


def available(game, site, floor, choice):
    if choice == 'pause':
        return (game.player.alive and not game.player.imprisonment and not game.player.ghost_captor
                and not (floor['result'] and floor['result']['outcome'] in {'controlled', 'defeat_trapped'}))
    try:
        require_actor(game, site, allow_pending=True)
    except ValueError:
        return False
    if choice == 'c':
        return True
    _, _, choices = situation(floor)
    _, mp, _, _, _ = choices[choice]
    risk = max(row[2] for row in choices.values())
    return game.player.mp >= max_mp(game.player) * mp and game.player.hp > max_hp(game.player) * risk


def project_event(game):
    if not enabled():
        return None
    site, floor = current(game)
    if not floor or floor['status'] != 'exploring':
        return None
    title, clue, outcomes = situation(floor)
    choices = []
    for key in floor['nodes'][floor['index']]['order']:
        label, mp, _, _, _ = outcomes[key]
        risk = max(row[2] for row in outcomes.values())
        cost = f'；法力上限 -{mp:.0%}' if mp else '；不消耗法力'
        warning = f'；判断失当可能损失 {risk:.0%} 气血上限' if risk else ''
        choices.append(dict(id=key, text=label + cost + warning,
                            enabled=available(game, site, floor, key), disabled_reason='所在地或状态已变化，或气血、法力不足'))
    choices.append(dict(id='pause', text='暂停离开，保留本层局势', enabled=available(game, site, floor, 'pause'), disabled_reason='当前受控状态不能离开'))
    return dict(id=event_id(floor), title=f"万象试境 · 第 {floor['number']} 层 · 事件 {floor['index'] + 1}/5",
                body=clue, choices=choices)


def public(game, maps):
    world = game.player.world
    if not enabled():
        return dict(enabled=False, available=False, active=bool(game.trial_site_state.get('active')),
                    blocked_session=bool(game.trial_site_state.get('active')))
    if world not in REALM_ROWS:
        return dict(enabled=True, available=False, active=bool(game.trial_site_state.get('active')),
                    unavailable_reason='独立空间没有本界试境；返回普通界面后可定位入口')
    site = bound_site(game, maps, world)
    actor_available = True
    reason = ''
    try:
        require_actor(game, site, allow_pending=is_trial(game.pending_event))
    except ValueError as error:
        actor_available, reason = False, str(error)
    active_site, floor = current(game)
    active = active_site is not None
    rows = []
    for number, realm in enumerate(REALM_ROWS[world], 1):
        saved = site['floors'].get(str(number))
        _, layer = rank_for_floor(world, number)
        rows.append(dict(number=number, realm_name=REALM_NAMES[realm], layer=layer,
                         status=saved['status'] if saved else 'unvisited', unlocked=number <= site['cleared'] + 1))
    view = dict(enabled=True, available=True, active=active, world=world, site_id=site['id'],
                world_name=WORLD_SYSTEMS['world_names'][world], tier=WORLD_TIERS[world],
                location_id=site['location_id'], location_name=maps.location(world, site['location_id'])['name'],
                total=len(rows), cleared=site['cleared'], floors=rows, can_enter=actor_available and not active,
                unavailable_reason=reason, session=None)
    if floor:
        view['session'] = dict(world=active_site['world'], number=floor['number'], status=floor['status'],
            floor_id=floor['id'], revision=floor['revision'], event_index=floor['index'],
            boss_name=floor['boss_name'], realm_name=REALM_NAMES[floor['realm']], layer=floor['layer'],
            known=[row['summary'] for row in floor['history']], attempts=floor['attempts'], result=copy.deepcopy(floor['result']),
            can_pause=available(game, active_site, floor, 'pause'))
        view['session']['mechanisms'] = [dict(kind=node['kind'], subject=node['subject'] if index <= floor['index'] else None,
            status='done' if index < floor['index'] else 'current' if index == floor['index'] else 'unknown',
            summary=floor['history'][index]['summary'] if index < floor['index'] else None)
            for index, node in enumerate(floor['nodes'])]
        if floor['index'] == 5:
            view['session'].update(power=power(floor), base_power=floor['base_power'], power_ratio=1 + floor['delta'], guard=floor['guard'], bonus=floor['bonus'],
                treasure=floor['treasure'], field=floor['field'], energy=floor['energy'],
                golden_light=floor['realm'] >= 10 or floor['realm'] == 9 and floor['layer'] >= 7,
                can_fight=actor_available and floor['status'] in {'ready', 'failed'} and game.pending_event is None,
                can_claim=actor_available and floor['status'] == 'won' and game.pending_event is None,
                rewards=[dict(row, preserved=index == 0 or floor['treasure']) for index, row in enumerate(floor['rewards'])])
    return view


def power(floor):
    return round(floor['base_power'] * (1 + floor['delta']), 4)


def target_for(site, floor):
    """The guardian owns a finite static pool; never borrow a world NPC."""
    key = floor['id'] + '_guardian'
    member = dict(npc_id=key, id=key, name=floor['boss_name'], kind='mechanical',
                  realm_index=floor['realm'], layer=floor['layer'], world=site['world'],
                  power=power(floor), path='dao', body_training=0, divine_sense_rank=1,
                  immortal_body_level=20 if floor['realm'] >= 10 or floor['realm'] == 9 and floor['layer'] >= 7 else 0)
    target = dict(target_name=member['name'], target_power=member['power'], target_realm_index=floor['realm'],
                  target_layer=floor['layer'], combat_type='trial_site', objective='repel',
                  members=[member], natural_terrain='开阔', artificial_conditions=[],
                  static_resource_ids=[key], enemy_buffs=[])
    if floor['guard']:
        target['enemy_buffs'].append(dict(id='trial_guard', name='阵甲供能', stat='guard', multiplier=1.2))
    if floor['bonus']:
        target['enemy_buffs'].append(dict(id='trial_residue', name='余灵增幅', stat='might', multiplier=1.1))
    if floor['realm'] >= 9:
        domain_id = key + '_field'
        member['transcendence'] = dict(version=1, conversion=1, capacity=1200., current=floor['energy'],
            force_tier=2, ward_tier=1, attack_cost=10, ward_cost=0,
            attainments={'trial_field': floor['realm'] - 8}, voisinage_ids=[domain_id] if floor['field'] else [])
        # Empty explicit grant after sealing must not fabricate a learned NPC doctrine.
        member['transcendence']['doctrine'] = {'manuals': [], 'manual_level': 0, 'progress': {}, 'active': None, 'at': 0, 'world': ''}
        target['voisinages'] = [dict(id=domain_id, name='试境守关域', attainment='trial_field', required_level=1,
            strength=1 + (floor['realm'] - 9) * .8 + (floor['layer'] - 1) * .03,
            opening_cost=80., upkeep_cost=40., effect='strike', effect_cost=35., effect_power=.2,
            max_investment=0.)]
    return target


def journal(game, floor, choice, summary, result='resolved'):
    game.history.append(HistoryRecord(floor['id'], VERSION, game.player.age, '万象试境', choice, result,
                                     summary, {'floor': floor['number']}, ['trial_site', f'world:{game.player.world}']))


def command(deps, game_id, action, payload):
    if not enabled():
        raise ValueError('万象试境 DLC 未加载；请在扩展管理中开启并重启')
    allowed = {'action', 'world', 'floor'} if action == 'enter' else {'action', 'floor_id', 'revision', 'event_id', 'choice_id'}
    if not isinstance(payload, dict) or set(payload) - allowed or payload.get('action', action) != action:
        raise ValueError('试境仅接受玩家本地挑战参数，不接受人物或隐藏配置覆盖')
    # Work on a detached transaction. Only a successful save publishes the result.
    game = copy.deepcopy(deps.load(game_id))
    site, floor = current(game)
    rng = decode_rng(game.seed, game.rng_state)
    if action == 'enter':
        if site:
            raise ValueError('已有活动试境，请先暂停当前层')
        world = payload.get('world')
        if world != game.player.world:
            raise ValueError('试境界面已变化，请重新查看地图')
        site = bound_site(game, deps.maps, world)
        require_actor(game, site)
        number = payload.get('floor')
        if type(number) is not int or not 1 <= number <= len(REALM_ROWS[world]) or number != site['cleared'] + 1:
            raise ValueError('该层尚未解锁或已领取通关奖励')
        floor = site['floors'].get(str(number))
        if floor is None:
            realm, layer = rank_for_floor(world, number)
            pool = deps.reward_pool(world, site['location_id'], realm)
            ordinal = sum(r == realm for r in REALM_ROWS[world][:number]) - 1
            # Some canonical ranks share an early/middle/late benchmark. The
            # ordinal keeps repeated late and early floors strictly increasing.
            base = expected_combat_power(realm, layer) * (1 + .12 * ordinal)
            floor = generate(game.seed, world, number, base, pool)
            site['floors'][str(number)] = floor
        if not game.trial_site_state:
            game.trial_site_state = dict(version=VERSION, sites={}, active=None)
        game.trial_site_state['sites'][world] = site
        game.trial_site_state['active'] = dict(world=world, floor=number)
        floor['revision'] += 1
        game.pending_event = project_event(game)
    else:
        if not floor or payload.get('floor_id') != floor['id'] or type(payload.get('revision')) is not int or payload.get('revision') != floor['revision']:
            raise ValueError('试境页面已经变化，请读取当前局势后再操作')
        if action == 'pause':
            if game.pending_event and not is_trial(game.pending_event):
                raise ValueError('请先处理当前事件，不能通过暂停跳过后果')
            if not available(game, site, floor, 'pause') or floor['result'] and floor['result']['outcome'] in {'controlled', 'defeat_trapped'}:
                raise ValueError('受控或封逃状态不能暂停离开')
            if game.pending_event:
                game.pending_event = game.pending_event.get('_followup_event')
            game.trial_site_state['active'] = None
        elif action == 'choose':
            require_actor(game, site, allow_pending=True)
            pending = game.pending_event
            if floor['status'] != 'exploring' or not pending or payload.get('event_id') != event_id(floor) or pending['id'] != event_id(floor):
                raise ValueError('本层事件已变化，请重新查看')
            choice = payload.get('choice_id')
            if choice not in {'a', 'b', 'c'} or not available(game, site, floor, choice):
                raise ValueError('当前没有此选项，或气血、法力不足')
            _, _, outcomes = situation(floor)
            _, mp, hp, updates, summary = outcomes[choice]
            for effect in ([{'type': 'restore_mp', 'value': -mp}] if mp else []) + ([{'type': 'damage', 'value': hp, 'reason': '试境机关失衡'}] if hp else []):
                _, effect_text = deps.effect(effect, game, pending, rng)
                summary += effect_text
            for name, value in updates.items():
                floor[name] = round(max(-.3, min(.4, floor[name] + value)), 6) if name == 'delta' else value
            floor['history'].append(dict(event_id=event_id(floor), choice_id=choice, summary=summary))
            floor['index'] += 1
            floor['revision'] += 1
            if floor['index'] == 5:
                floor['status'] = 'ready'
            following = pending.get('_followup_event')
            game.pending_event = project_event(game)
            if following:
                if game.pending_event:
                    game.pending_event['_followup_event'] = following
                else:
                    game.pending_event = following
            journal(game, floor, choice, summary)
        elif action == 'fight':
            require_actor(game, site)
            if floor['status'] not in {'ready', 'failed'}:
                raise ValueError('请完成五个事件后再交战')
            if floor['attempts'] >= 1000000:
                raise ValueError('本层尝试次数已达上限')
            floor['attempts'] += 1
            floor['revision'] += 1
            target = target_for(site, floor)
            outcome, summary = deps.combat(game, target, True, rng)
            if floor['realm'] >= 9:
                floor['energy'] = target['members'][0]['transcendence']['current']
            floor['result'] = dict(outcome=outcome, summary=summary)
            floor['status'] = 'won' if outcome == 'victory' and game.player.alive else 'failed'
            if game.last_combat_report:
                game.last_combat_report['trial_site'] = dict(floor_id=floor['id'], number=floor['number'],
                    choices=[r['summary'] for r in floor['history']], power=power(floor),
                    guard=floor['guard'], bonus=floor['bonus'], field=floor['field'], treasure=floor['treasure'])
            journal(game, floor, 'fight', summary, outcome)
            if not game.player.alive:
                game.trial_site_state['active'] = None
        elif action == 'claim':
            require_actor(game, site)
            if floor['status'] != 'won' or site['cleared'] + 1 != floor['number']:
                raise ValueError('本层尚未通关或奖励已领取')
            offered = [row for index, row in enumerate(floor['rewards']) if index == 0 or floor['treasure']]
            for row in offered:
                catalog = TECHNIQUE_CATALOG if row['kind'] == 'technique' else ITEM_CATALOG
                if row['content_id'] not in catalog:
                    raise ValueError('奖励内容已不可用，保留本层记录')
            summaries = []
            for row in offered:
                effect = {'type': 'learn_technique', 'technique_id': row['content_id']} if row['kind'] == 'technique' else {'type': 'add_item', 'item_id': row['content_id'], 'quantity': 1}
                _, summary = deps.effect(effect, game, {}, rng)
                summaries.append(summary)
            floor['status'] = 'claimed'
            floor['revision'] += 1
            site['cleared'] = floor['number']
            game.trial_site_state['active'] = None
            journal(game, floor, 'claim', ' '.join(summaries), 'claimed')
        else:
            raise ValueError('未知试境操作')
    decode_state(game.trial_site_state)
    game.updated_at = now_iso()
    game.rng_state = encode_rng(rng)
    deps.save(game)
    deps.commit(game)
    return deps.present(game)
