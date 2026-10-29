"""Local promised duels over the original people and shared NPC combat settlement."""
from ..content_registry import WORLD_SYSTEMS
from ..npc_custody import is_free, kill_person
from ..person_assignments import research_assignment
from ..spatial_people import accessible


def site(game, npc):
    if npc.location_id:
        return npc.location_id
    if npc.world in {'lost', 'rift'}:
        return None
    groups = [*game.sects.values(), *([game.family] if game.family else [])]
    group = next((g for g in groups if not g.extinct and g.world == npc.world
                  and (g.id == npc.faction_id or any(n.id == npc.id for n in g.npcs))), None)
    if group:
        from .faction_geography import faction_site
        return faction_site(group, persist=False)['id']
    return None


def participant_reason(game, npc):
    if not is_free(npc) or not accessible(game, npc):
        return '此人不在当前界面或空间，或不在自由名册'
    if npc.id in game.intrigue_state.get('npc_prisons', {}):
        return '此人正在被关押，无法赴约交战'
    if research_assignment(game, npc.id):
        return '此人已有行程或战役职责，无法另赴约战'
    if not site(game, npc):
        return '此人当前地点不明，无法安排约战'
    return ''


def request_reason(game, npc):
    p = game.player
    if (not p.alive or game.pending_event or game.active_trial or p.imprisonment or p.ghost_captor
            or p.nascent_state.get('crisis') or game.guixu_state.get('player_session')):
        return '请先结束当前事件、战斗或拘禁'
    reason = participant_reason(game, npc)
    if reason:
        return reason
    if float(npc.affinity or 0) < WORLD_SYSTEMS['relationship']['friend_affinity_required']:
        return f"好感须达到{WORLD_SYSTEMS['relationship']['friend_affinity_required']:g}，方可要求承诺"
    if game.governance_actions.get(f'npc_promise:{npc.id}') == game.diplomacy_unit:
        return '此人本行动单位已经履行过承诺'
    return ''


def validate(game, actor, target, expected_unit):
    reason = request_reason(game, actor)
    if reason:
        raise ValueError(reason)
    if type(expected_unit) is not int or expected_unit != game.diplomacy_unit:
        raise ValueError('承诺页面已过期，请刷新后重新选择目标')
    if actor.id == target.id:
        raise ValueError('不能要求此人与自己交战')
    reason = participant_reason(game, target)
    if reason:
        raise ValueError(reason)
    if site(game, actor) != site(game, target):
        raise ValueError('双方须在同一地点才能约战，请待实际会合后再要求承诺')


def resolve(game, actor, target, rng, npc_power):
    from .combat.npc_battle import resolve_local_engagement
    from .doctrine.provider import battle_sources
    p = game.player
    status = p.concubine_status or {}
    companion = p.dao_companion or {}
    fengyi = (status.get('owner_id') == target.id
              and companion.get('id') == actor.id and actor.id != target.id)
    outcome = resolve_local_engagement([(actor, npc_power(actor))], [(target, npc_power(target))],
        WORLD_SYSTEMS.get('transcendent_combat', {}), rng, now=p.age,
        sources=battle_sources(game, {actor.id: actor, target.id: target}),
        attacker_objective='kill', defender_objective='kill')
    for npc in (actor, target):
        if npc.id in outcome.killed and not npc.alive:
            other = target if npc is actor else actor
            kill_person(game, npc.id, f'与{other.name}斗法时陨落')
    slain_owner = target.id in outcome.killed and not target.alive
    if fengyi and slain_owner:
        p.milestones['fengyi_pavilion'] = 1
    if slain_owner and (p.concubine_status or {}).get('owner_id') == target.id:
        p.concubine_status = None
    return outcome


def projection(game, npc):
    return dict(contact_location_id=site(game, npc) if accessible(game, npc) else None,
                contact_promise_unit=game.diplomacy_unit,
                contact_promise_target_reason=participant_reason(game, npc))
