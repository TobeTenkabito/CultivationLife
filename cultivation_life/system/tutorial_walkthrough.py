"""Ordered, once-only teaching actions. No annual hook or random event overrides."""
from ..definition_data import definition as _content_definition
from copy import deepcopy
import random

from ..content_registry import TECHNIQUE_CATALOG, FACTION_DEFINITIONS, WORLD_SYSTEMS
from ..models import HistoryRecord
from ..rules import acquire_technique, add_item, assign_technique
from ..runtime import now_iso
from .faction_geography import can_enter_faction
from .tutorial_mentorship import MENTOR

STEPS = (
    'welcome', 'identity', 'roots', 'close_identity', 'practice', 'gain',
    'living', 'treasure', 'bag', 'resources', 'close_bag', 'arts_identity',
    'library', 'equip', 'art_result', 'close_arts', 'travel_tab', 'meet',
    'mentor_choice', 'relationships', 'npc', 'close_relationships', 'faction',
    'join', 'sect', 'close_faction', 'map', 'roads', 'close_map', 'settings',
    'handbook', 'finish',
)
MUTATIONS = {'practice', 'treasure', 'equip', 'meet', 'mentor_choice', 'join'}


def blocked(game):
    p = game.player
    if not p.alive:
        return '此生已结束，可在新角色中体验操作引导。'
    if game.pending_event or game.active_trial or p.imprisonment or p.ghost_captor or (game.guixu_state.get('player_session') or {}).get('trapped'):
        return '请先暂停引导，处理眼前的事件或困境，再从主界面继续。'
    return ''


def beginner(game):
    p = game.player
    return max(p.realm_index, int((p.sealed_cultivation or {}).get('realm_index', 0))) < 3 and WORLD_SYSTEMS['world_profiles'].get(p.world, {}).get('tier', 1) == 1


def lesson_art(game):
    """Use only an already learned art; opening the dungeon grants no manual."""
    p = game.player
    saved = p.tutorial_state.get('guide_art')
    candidates = [p.technique, *p.known_techniques]
    if saved:
        candidates = [x for x in candidates if x and x.id == saved]
    for art in candidates:
        if not art or art.category != 'spiritual':
            continue
        try:
            assign_technique(deepcopy(p), deepcopy(art), 'main')
        except ValueError:
            continue
        return art
    return None


def admissions(game):
    p = game.player
    if p.faction_id or not beginner(game) or blocked(game):
        return []
    rows = [s for s in game.sects.values() if s.id in FACTION_DEFINITIONS and not s.extinct
            and s.world == p.world and can_enter_faction(s, p) and p.hostility.get('sect:'+s.id, 0) <= 0]
    rows.sort(key=lambda s: (s.path != p.path, s.id))
    return [{'id':s.id, 'name':s.name} for s in rows]


def public_guide(game):
    state = game.player.tutorial_state
    index = min(max(int(state.get('guide_index', 0)), 0), len(STEPS)-1)
    active = bool(state.get('enabled')) and not state.get('guide_completed', False)
    # No catalog scans or NPC traversal when the guide is off.
    art = lesson_art(game) if active and STEPS[index] in {'treasure', 'equip', 'art_result'} else None
    reason = blocked(game) if active else ''
    from .tutorial_mentorship import blocked_reason
    mentor_reason = blocked_reason(game) if active and STEPS[index] in {'meet', 'mentor_choice'} else ''
    if state.get('mentor_result'):
        mentor_reason = '你已结算过这份师缘，这次只回顾师徒关系。'
    npc = game.notable_npcs.get(state.get('mentor_id'))
    if npc and (not npc.alive or npc.world != game.player.world or npc.realm_index != MENTOR["realm_index"]):
        mentor_reason = '前辈的处境已改变，这次只回顾师承说明。'
    choices = admissions(game) if active and STEPS[index] == 'join' else []
    event = None
    if active and STEPS[index] == 'mentor_choice' and npc and not mentor_reason:
        event = _content_definition(__name__, "MENTOR_OFFER")
        event['body'] = event['body'].format(realm=MENTOR['realm_label'], name=npc.name)
    return {'active':active, 'index':index, 'step':STEPS[index], 'total':len(STEPS),
            'completed':bool(state.get('guide_completed')), 'blocked':reason,
            'beginner':beginner(game), 'practice_gain':5 if beginner(game) and game.player.spirit_root != 'none' else 0,
            'art':{'id':art.id, 'name':art.name} if art else None,
            'mentor_reason':mentor_reason, 'admissions':choices, 'event':event,
            'last_result':state.get('guide_result', '')}


def perform_guide(engine, game, action, expected, target_id=None):
    state, p = game.player.tutorial_state, game.player
    info = public_guide(game)
    # An acknowledged step cannot be applied twice, even after a lost response.
    if expected in STEPS and STEPS.index(expected) < info['index']:
        return engine.present(game)
    if not info['active'] or expected != info['step']:
        raise ValueError('引导进度已改变，请重新打开教程')
    if info['blocked']:
        raise ValueError(info['blocked'])
    step, summary = info['step'], ''
    if action == 'guide_next':
        skippable = ((step == 'equip' and not info['art']) or
                     (step in {'meet', 'mentor_choice'} and bool(info['mentor_reason'])) or
                     (step == 'join' and (p.faction_id or not info['admissions'])))
        if step in MUTATIONS and not skippable:
            raise ValueError('请先完成高亮的操作')
    elif action == 'guide_practice' and step == 'practice':
        gain = info['practice_gain']
        if gain:
            engine._add_opportunity(p, gain)
        summary = f'你试行一周天，获得 {gain} 点机缘。此次入门练习不推进岁月，也不自动突破。' if gain else '你观察运气方式；当前角色只演示操作，不改变修为或资质。'
    elif action == 'guide_treasure' and step == 'treasure':
        art = lesson_art(game)
        summary = '探幽寻宝现为副本入口：探寻后入口固定，入境不耗岁月，退出后须间隔一个完整行动单位。此次引导只认识入口。'
        if art:
            state['guide_art'] = art.id
    elif action == 'guide_equip' and step == 'equip':
        art = lesson_art(game)
        if not art or target_id != art.id or not any(t.id == art.id for t in p.known_techniques):
            raise ValueError('请配置本课指定的已悟功法')
        assign_technique(p, deepcopy(art), 'main')
        summary = f'《{art.name}》已配置为主修功法。学会功法与配置功法是两回事。'
    elif action in {'guide_meet', 'guide_accept', 'guide_decline'}:
        if (action == 'guide_meet' and step != 'meet') or (action != 'guide_meet' and step != 'mentor_choice'):
            raise ValueError('当前尚未到师缘这一步')
        if info['mentor_reason']:
            raise ValueError(info['mentor_reason'])
        from .tutorial_mentorship import mentor_action
        state['step'] = 6
        mentor_action(engine, game, {'guide_meet':'offer_mentor','guide_accept':'accept_mentor','guide_decline':'decline_mentor'}[action])
        summary = f'你遇到{MENTOR["realm_label"]}的{MENTOR["name"]}，请在事件中亲自作出选择。' if action == 'guide_meet' else (f'{MENTOR["name"]}已收你为徒。' if action == 'guide_accept' else '你谢过师缘，日后仍可另寻师承。')
    elif action == 'guide_join' and step == 'join':
        if target_id not in {s['id'] for s in info['admissions']}:
            raise ValueError('这座宗门当前不能通过教学引荐加入')
        _, summary = engine._effect({'type':'join_faction', 'faction_id':target_id}, game, {}, random.Random(0))
        summary += '此次引荐不耗岁月或灵石；日后正常享有福利并承担门内事务。'
    else:
        raise ValueError('此操作与当前引导不符')
    if summary:
        state['guide_result'] = summary
        game.history.append(HistoryRecord('SYS_TUTORIAL_PRACTICE', 1, p.age, '初入问道', step,
            'guided', summary, {}, ['system','tutorial']))
    if step == 'finish':
        state.update(guide_completed=True, enabled=False, completed=True)
    else:
        state['guide_index'] = info['index'] + 1
    game.updated_at = now_iso()
    engine.store.save(game)
    return engine.present(game)
