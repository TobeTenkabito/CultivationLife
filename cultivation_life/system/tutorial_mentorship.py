"""Shared apprenticeship rules for reading lessons and the interactive walkthrough."""
from ..content_registry import REALMS, WORLD_SYSTEMS
from ..models import HistoryRecord, SectNpc
from ..rules import has_living_master

MENTOR_STEP = 6


def blocked_reason(game):
    p = game.player
    if not p.alive:
        return '此生已经落幕，可阅读指南，在新的一世再结师缘。'
    if game.pending_event or game.active_trial or p.imprisonment or p.ghost_captor or (game.guixu_state.get('player_session') or {}).get('trapped'):
        return '请先处理眼前的事件、试炼或困境，再赴师缘。'
    if has_living_master(p):
        return '你已有在世的师父；本课不会替换现有师承。'
    if max(p.realm_index, int((p.sealed_cultivation or {}).get('realm_index', 0))) >= 3:
        return '这份结丹师缘留给尚未结丹的新手；你仍可阅读这一课。'
    if WORLD_SYSTEMS['world_profiles'].get(p.world, {}).get('tier', 1) != 1:
        return '这位结丹修士在人间诸界云游，上界角色可阅读师承说明。'
    return ''


def mentor_status(game):
    state = game.player.tutorial_state
    npc = game.notable_npcs.get(state.get('mentor_id'))
    reason = blocked_reason(game)
    if npc and (not npc.alive or npc.world != game.player.world or npc.realm_index != 3):
        reason = '师缘已随岁月或行踪改变；请在同道往来中另寻师承。'
    result = state.get('mentor_result')
    return dict(enabled=bool(state.get('enabled')), step=state.get('step', 0),
        completed=bool(state.get('completed')), mentor_result=result,
        can_offer=not reason and not result and npc is None,
        can_accept=not reason and not result and npc is not None,
        blocked_reason=reason,
        mentor=({'name': npc.name, 'id': npc.id, 'realm': '结丹后期', 'alive': npc.alive} if npc else None))


def mentor_action(engine, game, action):
    p, state = game.player, game.player.tutorial_state
    if not state.get('enabled') or state.get('step', 0) != MENTOR_STEP:
        raise ValueError('请先在新手教程中读到拜师一课')
    # Repeated requests, re-enabling and replaying the chapter grant nothing.
    if state.get('mentor_result'):
        return
    info = mentor_status(game)
    if action == 'offer_mentor':
        if state.get('mentor_id'):
            return
        if not info['can_offer']:
            raise ValueError(info['blocked_reason'])
        key = 'tutorial_mentor:' + game.id
        span = REALMS[3].lifespan
        npc = SectNpc(key, '沈照尘', '云游讲道的前辈', 3, 7, 180,
            max(181, sum(span) // 2) if span else None,
            spirit_root='supreme_wood', path=p.path, race=p.race,
            world=p.world, affinity=35, encountered_player=True)
        from .cultivation_ranks import ensure_npc
        from .npc_social import instantiate_social
        ensure_npc(npc)
        game.notable_npcs[key] = npc
        instantiate_social(game, npc)
        state['mentor_id'] = key
        summary = '结丹后期修士沈照尘停步讲道，愿引你入门。你可以执弟子礼，或谢过这份好意。'
        result = 'offered'
    else:
        npc = game.notable_npcs.get(state.get('mentor_id'))
        if not npc:
            raise ValueError('尚未遇见这位授业前辈')
        if action == 'accept_mentor':
            if not info['can_accept']:
                raise ValueError(info['blocked_reason'])
            p.master = engine._relationship_snapshot(npc.id, npc.name, npc.realm_index, npc.layer,
                'world', npc.age, npc.lifespan, spirit_root=npc.spirit_root,
                path=npc.path, race=npc.race, world=npc.world, affinity=35, gender=npc.gender)
            p.master = game.link_relationship(p.master)
            result = 'accepted'
            summary = '你执弟子礼，沈照尘欣然收徒。自此可在关系窗口查看师承、请益修行；师父也有自己的修行与际遇。'
        else:
            result = 'declined'
            summary = '你谢过沈照尘的好意，决定自行问道。这次选择不损及声望，也不影响日后另寻师承。'
        state['mentor_result'] = result
    game.history.append(HistoryRecord('SYS_TUTORIAL_MENTOR', 1, p.age, '山道授业', action,
        result, summary, {'npc_id': state['mentor_id']}, ['system', 'relationship', 'master', 'tutorial']))
