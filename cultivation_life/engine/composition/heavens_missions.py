"""Civilian researcher facts and movement; no alternate NPC registry or year."""
from ...content_registry import WORLD_SYSTEMS
from ...npc_custody import is_free
from ...person_assignments import route_occupied
from ...spatial_people import instance_of
from ...system.combat.npc_lifecycle import move_world
from ...system.heavens.definitions import VISIT_DESTINATIONS
from ...system.heavens.state import get_echo, site_for
from ...system.heavens import missions


def bind_missions(engine, ports):
    def facts(game, target, *, check_route=True):
        deps = ports()
        echo = get_echo(game.heavens_state.get('runtime'), target)
        npc = deps.resolve_person(game, echo['visitor_id']) if echo else None
        mission = echo.get('mission') if echo else None
        phase = mission['phase'] if mission else 'outbound'
        origin, destination = site_for(deps, game, target), site_for(deps, game, VISIT_DESTINATIONS[target])
        local = origin if phase == 'outbound' else destination
        remote = origin if phase == 'returning' else destination
        reason = None
        if not npc or not npc.alive:
            reason = '回访人物已经陨落或不在权威名册'
        elif not is_free(npc) or engine._intrigue_is_imprisoned(game, npc.id):
            reason = '回访人物正在受控，行程暂缓'
        elif npc.world != local.world or npc.location_id != local.location_id or instance_of(game, npc.id):
            reason = '回访人物已离开约定位置，须回到原处才能续行'
        elif npc.realm_index < 9:
            reason = '回访人物不满足九阶通行资格'
        elif npc.faction_id or npc.id not in game.world_npcs:
            reason = '此人物已有其他名册职责，不能重复安排'
        else:
            relations = [game.player.master, game.player.dao_companion, *game.player.dao_friends,
                         *game.player.disciples, *game.player.concubines, *game.player.party, *game.player.disciple_requests]
            if any(row and (row.get('npc_id') or row.get('id')) == npc.id for row in relations):
                reason = '回访人物已有关系或同行职责'
            elif any(npc.id in ids for war in game.wars if war.get('status') in {'active', 'peace_ready'}
                     for ids in war.get('roster', {}).values()):
                reason = '回访人物已有战事部署'
        if check_route and not reason and phase != 'studying':
            route = next((r for r in WORLD_SYSTEMS['world_transition_routes']
                          if r['id'] == f'study:{local.world}:{remote.world}'), None)
            if (not route or not route['enabled'] or route.get('research_visitors') is not True
                    or route.get('capacity') != 1 or route.get('purpose') != 'personal_study'
                    or route.get('mode') != 'study' or route.get('source') != local.world
                    or route.get('destination') != remote.world
                    or not WORLD_SYSTEMS['world_profiles'][remote.world]['enabled']):
                reason = '约定研究人员通道尚不可用'
            elif route_occupied(game, local.world, remote.world, exclude=npc.id):
                reason = '通道正在被另一项个人行程占用'
            elif npc.realm_index < int(engine.maps.location(remote.world, remote.location_id).get('min_realm_index', 0)):
                reason = '抵达修为不满足接待地点要求'
        return dict(alive=bool(npc and npc.alive), blocked_reason=reason,
                    world=npc.world if npc else None, location_id=npc.location_id if npc else None)

    def move(game, target, phase):
        deps = ports()
        echo = get_echo(game.heavens_state['runtime'], target)
        mission = echo['mission']
        if (mission['status'] != 'active' or mission['phase'] != phase
                or phase not in {'outbound', 'returning'} or mission['progress'] != 2):
            raise ValueError('研究人员尚未完成实际通行时间')
        reason = facts(game, target)['blocked_reason']
        if reason:
            raise ValueError(reason)
        destination = site_for(deps, game, mission['destination'] if phase == 'outbound' else target)
        npc = deps.resolve_person(game, echo['visitor_id'])
        move_world(npc, destination.world, game.player.age, WORLD_SYSTEMS.get('transcendent_combat', {}))
        npc.location_id = destination.location_id

    return dict(read_mission_facts=facts, move_researcher=move,
                advance_researchers=lambda game: missions.year_step(ports(), game))
