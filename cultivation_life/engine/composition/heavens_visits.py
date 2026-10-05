"""Personal study passages through the existing authoritative world transition."""
from ...system.heavens.definitions import VISIT_DESTINATIONS
from ...system.heavens.state import get_echo, site_for, active_task
from ...system.world_transition_system import finish_world_transition


def bind_visits(engine, ports):
    def read_facts(game, target, action):
        deps = ports()
        origin = site_for(deps, game, target)
        destination = site_for(deps, game, VISIT_DESTINATIONS[target])
        local = origin if action == 'visit_depart' else destination
        remote = destination if action == 'visit_depart' else origin
        facts = deps.read_actor_facts(game, local.id)
        p = game.player
        reason = facts['blocked_reason']
        if not reason and (p.sealed_cultivation or game.spatial_state.get('current')):
            reason = '请先解除跨界封印并离开独立空间'
        if not reason and (p.party or any(n.alive and n.roster_state == 'held'
                and (n.custody or {}).get('holder_id') == game.id for n in game.inactive_npcs.values())):
            reason = '个人访学通道只容一人，请先解散同行队伍并安置俘虏'
        if not reason and action != 'visit_study':
            try:
                engine._plan_world_transition(game, remote.world, 'study',
                    arrival_location=remote.location_id, reason='个人访学')
            except ValueError as exc:
                reason = str(exc)
        facts['blocked_reason'] = reason
        return facts

    def move(game, target, action, rng):
        task = active_task(game.heavens_state['runtime'])
        if not task or task['action'] != action or task['target_id'] != target or task['progress'] != task['duration']:
            raise ValueError('尚未完成实际通行时间')
        facts = read_facts(game, target, action)
        if facts['blocked_reason']:
            raise ValueError(facts['blocked_reason'])
        deps = ports()
        echo = get_echo(game.heavens_state['runtime'], target)
        destination = site_for(deps, game, echo['visit']['destination'] if action == 'visit_depart' else target)
        plan = engine._plan_world_transition(game, destination.world, 'study',
            arrival_location=destination.location_id, reason='个人访学往返')
        engine._apply_world_transition(game, plan)
        game.player.awaiting_ascension = False
        finish_world_transition(game, rng, engine._refresh_world_market)

    return dict(read_visit_facts=read_facts, move_visit=move)
