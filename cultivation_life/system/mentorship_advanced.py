"""Personal inheritance and rebellion; all participants are original NPC IDs."""
from . import mentorship as m
from ..content_registry import WORLD_SYSTEMS
from ..rules import combat_power, opportunity_required
from ..soul_rules import wandering
from .mentorship_avatar import avatar_person, avatar_reason, avatar_unit, tick_avatar

ACTIONS = ('pact_possession', 'pact_avatar', 'revoke_pacts', 'possess_heir',
           'refine_avatar', 'avatar_toggle', 'sow_discord', 'plot', 'challenge_master')
EVENT = 'EVT_MENTORSHIP_REBELLION_001'


def extra(row):
    return row.get('advanced', {})


def ledger(row):
    return row.setdefault('advanced', {})


def precision(game, identity):
    row = m.record(game, 'player', identity)
    if not row or not m.active(game, 'player', identity, row): return 0
    limit = {'personal': 1, 'heir': 3}.get(row['rank'], 0)
    state = extra(row)
    used = state.get('precision_used', 0) if state.get('precision_cycle') == row['cycle'] else 0
    return max(0, limit - used)


def spend_precision(game, identity):
    row = m.record(game, 'player', identity)
    if not precision(game, identity): raise ValueError('本周期传承精修额度不足')
    state = ledger(row)
    used = state.get('precision_used', 0) if state.get('precision_cycle') == row['cycle'] else 0
    state.update(precision_cycle=row['cycle'], precision_used=used + 1)


def heir(game, identity):
    m.require_contact(game, identity)
    row = m.record(game, 'player', identity)
    if not row or not m.active(game, 'player', identity, row) or row['rank'] != 'heir':
        raise ValueError('此项传承只对在籍嫡传弟子开放')
    npc = m.person(game, identity)
    if npc.age < 18 or wandering(npc): raise ValueError('需要成年且肉身完好的嫡传弟子')
    if npc.lifespan is not None and npc.age >= npc.lifespan: raise ValueError('弟子寿元已尽，无法办理传承')
    return row, npc


def pact_valid(row, kind):
    return row['rank'] == 'heir' and row['status'] == 'active' and row['loyalty'] >= 60 and extra(row).get('pact_' + kind, False)


def battle_target(npc, power):
    value = power(npc)
    return dict(target_name=npc.name, target_power=value, primary_power=value,
                target_realm_index=npc.realm_index, target_layer=npc.layer,
                npc_id=npc.id, path=npc.path, race=npc.race, world=npc.world,
                faction_id=npc.faction_id, combat_type='cultivator', action='attack', non_story_combat=True)


def eligible_rebels(game, *, event=False):
    return [key for key, row in m.rows(game, 'player').items()
            if row['rank'] != 'registered' and row['loyalty'] < 25
            and not m.contact_reason(game, key, rebellion_event=event)
            and not wandering(m.person(game, key))]


def maybe_rebellion(deps, game, rng):
    from ..regional_context import historical, region
    if historical(game) or region(game) and region(game) != game.player.world: return
    if game.pending_event: return
    ids = sorted(eligible_rebels(game), key=lambda key: (-deps._npc_power(m.person(game, key)), key))[:4]
    if not ids or sum(deps._npc_power(m.person(game, k)) for k in ids) < combat_power(game.player) * .7:
        state = game.mentorship_state.get('rebellion')
        if state and state['ids']: state.update(ids=[], at=game.player.age)
        return
    state = game.mentorship_state.get('rebellion', {})
    if game.player.age < state.get('cooldown_until', 0): return
    period = max(m.record(game, 'player', key)['period'] for key in ids)
    if set(state.get('ids', [])) != set(ids):
        game.mentorship_state['rebellion'] = dict(ids=ids, at=game.player.age, cooldown_until=state.get('cooldown_until', 0))
        m.log(game, 'rebellion_warning', '低忠诚弟子正在串联，合力已足以威胁你。一个师门周期后可能发难，请及时改善关系。')
        return
    if game.player.age < state['at'] + period: return
    game.pending_event = deps._instantiate_event(deps.events_by_id[EVENT], game, rng)
    game.pending_event['runtime'] = {'rebels': ids}
    state['cooldown_until'] = game.player.age + period * 2


def resolve_rebellion(deps, game, pending, method, rng):
    if pending.get('id') != EVENT or method not in {'fight', 'yield'}: raise ValueError('叛师事件无效')
    allowed = set(eligible_rebels(game, event=True))
    ids = list(dict.fromkeys(k for k in pending.get('runtime', {}).get('rebels', []) if k in allowed))[:4]
    if not ids: return 'dispersed', '叛师者已不在场或不再敌对，事件解除，不结算远程战斗。'
    summary = '你解除这些弟子的师承关系，结束争端。'
    result = 'yielded'
    if method == 'fight':
        target = battle_target(m.person(game, ids[0]), deps._npc_power)
        target.update(members=[dict(npc_id=k, name=m.person(game, k).name, power=deps._npc_power(m.person(game, k)),
                                    realm_index=m.person(game, k).realm_index, path=m.person(game, k).path,
                                    race=m.person(game, k).race, faction_id=m.person(game, k).faction_id) for k in ids],
                      exclude_allied_ids=ids, player_defending=True, mentorship_betrayal=True)
        target['target_power'] = sum(n['power'] for n in target['members'])
        result, summary = deps._combat(game, target, True, rng)
        summary = '熟悉你的门人封锁行功破绽：本场自身战斗属性降低40%。' + summary
    for key in ids:
        m.end(game, 'player', key, 'expelled')
        npc = m.person(game, key)
        if npc: npc.affinity = min(npc.affinity, -40)
    m.log(game, 'rebellion', summary)
    return result, summary


def execute(deps, game, action, identity, rng):
    p = game.player
    if action == 'avatar_toggle':
        reason = avatar_reason(game, command=True)
        if reason: raise ValueError(reason)
        state = game.mentorship_state['avatar'];state['enabled'] = not state['enabled']
        return '化身已' + ('启用出战。' if state['enabled'] else '停止出战。')
    if action in {'sow_discord', 'plot', 'challenge_master'}:
        return intrigue(deps, game, action, identity, rng)
    row, npc = heir(game, identity)
    state = extra(row)
    if action.startswith('pact_'):
        if row['loyalty'] < 85: raise ValueError('商议传承契约需要忠诚至少85')
        if state.get(action + '_cycle') == row['cycle']: raise ValueError('本周期已经商议过该契约')
        cost = m.duty_cost(game, {**row, 'rank':'true'})
        if p.opportunity < cost: raise ValueError(f'商议契约需要机缘{cost:g}')
        p.opportunity -= cost
        accepted = rng.random() < min(1., .5 + (row['loyalty'] - 85) * .05)
        ledger(row).update({action:accepted, action + '_cycle':row['cycle']})
        return f'{npc.name}' + ('同意了传承契约。' if accepted else '拒绝了契约，本周期不能再次说服。')
    if action == 'revoke_pacts':
        ledger(row).update(pact_possession=False, pact_avatar=False)
        return '已撤销此弟子的传承契约；本周期商议次数不会重置。'
    if action == 'possess_heir':
        if not pact_valid(row, 'possession'): raise ValueError('缺少有效的自愿夺舍契约')
        from .possession_system import can_possess, enter_host_body
        from .npc_techniques import resolve
        allowed, reason = can_possess(p, npc.to_dict())
        if not allowed: raise ValueError(reason)
        ledger(row)['pact_possession'] = False
        own, other = max(1., combat_power(p)), max(1., deps._npc_power(npc))
        chance = min(.95, max(.1, .55 + (own - other) / (own + other) * .35) + .15)
        if rng.random() >= chance:
            deps._die(game, '传承夺舍融合失败，神魂反噬', 'SYS_POSSESSION_FAILED', survival_stage='spirit_failed')
            return f'自愿宿主融合失败（成功率{chance:.0%}），已依原魂魄存续规则结算。'
        original_name = npc.name
        enter_host_body(p, dict(npc.to_dict(), npc_id=npc.id), technique=resolve(game, npc.main_technique_id))
        m.end(game, 'player', identity, 'departed')
        from ..npc_custody import kill_person
        kill_person(game, identity, '履行传承夺舍契约，原神魂消散')
        return f'成功承接{original_name}的肉身（成功率{chance:.0%}）；原人物退场，夺舍次数已计入。'
    if action != 'refine_avatar': raise ValueError('未知传承事务')
    from .npc_development.targets import resolve, require
    require(game, resolve(game, 'npc', identity))
    if p.path != 'demonic' or p.realm_index < 4 or wandering(p): raise ValueError('须元婴境及以上、有肉身的魔修才能炼化身外化身')
    if p.sealed_cultivation or p.cultivation_suppression: raise ValueError('封印或压制期间无法炼化化身')
    if (npc.realm_index, npc.layer) > (p.realm_index, p.layer): raise ValueError('弟子真实修为不可高于自身')
    if avatar_person(game): raise ValueError('只能控制一个身外化身')
    from ..npc_development_content import TIERS
    if p.world not in TIERS or game.guixu_state.get('player_session'): raise ValueError('当前空间不允许炼化化身')
    if npc.realm_index > {1:5, 2:8, 3:12}[TIERS[p.world]]: raise ValueError('弟子真实修为超出当前界面承载')
    cost = round(max(1., opportunity_required(p) * .1), 1)
    if p.opportunity < cost: raise ValueError(f'炼化化身需要机缘{cost:g}')
    consented = pact_valid(row, 'avatar')
    p.opportunity -= cost
    m.end(game, 'player', identity, 'departed')
    from ..npc_custody import detain_person
    from ..models import SectNpc
    detain_person(game, {'id':identity}, SectNpc, kind='external_avatar')
    p.party[:] = [r for r in p.party if r.get('id') != identity]
    game.mentorship_state['avatar'] = dict(id=identity, consented=bool(consented), enabled=True, last_age=p.age)
    if not consented:
        for disciple in m.rows(game, 'player').values():
            if disciple['rank'] != 'registered': disciple['loyalty'] = max(0, disciple['loyalty'] - 10)
    return f'{npc.name}被炼为唯一身外化身，保留原培养与寿命；' + ('自愿契合，战力提升20%。' if consented else '强制炼化，没有自愿契合加成。')


def intrigue(deps, game, action, identity, rng):
    p = game.player
    teacher = p.master.get('id') if p.master else None
    if not teacher: raise ValueError('尚未拜师，不能参与师门夺位')
    m.require_contact(game, teacher)
    own = m.record(game, teacher, 'player')
    if not own or own['rank'] == 'registered': raise ValueError('记名弟子没有师门交流权')
    if action != 'challenge_master':
        peer = m.record(game, teacher, identity)
        if identity == 'player' or not peer or not m.active(game, teacher, identity, peer): raise ValueError('此人不是在籍同门')
        m.require_contact(game, identity)
        npc = m.person(game, identity)
        if peer['rank'] == 'registered' or wandering(npc): raise ValueError('此同门不能参加师门争斗')
        if action == 'sow_discord':
            if extra(peer).get('sow_cycle') == own['cycle']: raise ValueError('本周期已游说此同门')
            cost = m.duty_cost(game, {**own, 'rank':'true'})
            if p.opportunity < cost: raise ValueError(f'游说需要机缘{cost:g}')
            p.opportunity -= cost
            ledger(peer)['sow_cycle'] = own['cycle']
            if rng.random() < min(.9, max(.1, .5 + npc.affinity / 200)):
                peer['loyalty'] = max(0, peer['loyalty'] - 20)
                return f'游说动摇了{npc.name}，其对师父忠诚降低20。'
            own['discontent'] = min(100, own['discontent'] + 15)
            return '游说被师父察觉，师门不满增加15。'
        if peer['loyalty'] >= 30 or npc.affinity < 30: raise ValueError('结盟需要同门忠诚低于30且对你好感至少30')
        ledger(peer)['plot'] = True
        return f'{npc.name}愿意在同场夺位时助你。'
    if extra(own).get('challenge_cycle') == own['cycle']: raise ValueError('本周期已挑战师父')
    allies = [key for key, row in m.rows(game, teacher).items() if key != 'player' and row['rank'] != 'registered'
              and extra(row).get('plot') and row['loyalty'] < 30 and m.person(game, key).affinity >= 30
              and not m.contact_reason(game, key) and not wandering(m.person(game, key))][:3]
    if not allies: raise ValueError('须有至少一名仍符合条件且实际在场的同门盟友')
    master = m.person(game, teacher)
    target = battle_target(master, deps._npc_power)
    target.update(mentorship_allies=allies, exclude_allied_ids=[teacher, *allies], mentorship_master_betrayed=True)
    ledger(own)['challenge_cycle'] = own['cycle']
    result, summary = deps._combat(game, target, True, rng)
    master.affinity = min(master.affinity, -60)
    if result not in {'victory', 'killed', 'victory_controlled', 'victory_escape'}:
        own['discontent'] = 100
        m.end(game, teacher, 'player', 'expelled')
        return summary + ' 夺位失败，师承已断。'
    # Transfer only the consenting survivors. Neither sect seats nor property move.
    m.end(game, teacher, 'player', 'departed')
    for key in allies:
        npc = m.person(game, key)
        m.end(game, teacher, key, 'departed')
        if npc.alive and not wandering(npc):
            p.disciples.append(game.link_relationship({'id':key}))
            row = m.admit(game, 'player', key)
            row['loyalty'] = 45
    return summary + ' 你接掌同盟的个人师承；未夺取宗门职位、领地或仓库。'


def public(game):
    avatar = game.mentorship_state.get('avatar')
    view = {'rebellion':game.mentorship_state.get('rebellion'), 'avatar':None}
    if avatar:
        npc = m.person(game, avatar['id'])
        from .npc_development.portraits import FIELDS
        view['avatar'] = {**avatar, 'name':getattr(npc, 'name', '昔日化身'), 'reason':avatar_reason(game, command=True),
                          'portrait':{key:getattr(npc, key, None) for key in FIELDS} if npc else None}
    return view
