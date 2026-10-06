"""Named adapters for real faction authority, people and limited recon travel."""
import copy

from ...content_registry import WORLD_SYSTEMS
from ...npc_custody import is_free
from ...person_assignments import research_assignment
from ...spatial_people import instance_of
from ...system.combat.npc_lifecycle import move_world
from ...system.faction_geography import faction_site
from ...system.heavens.frontier_definitions import ROUTE, SOURCE_FACTION


def bind_frontier(engine):
    def authority(game):
        sect = game.sects.get(SOURCE_FACTION)
        if not sect or sect.extinct or sect.world != ROUTE.source_world:
            return None
        members = [n for n in engine._sect_members(game, sect) if n.alive and is_free(n)
                   and n.world == sect.world and not instance_of(game, n.id)
                   and n.id not in game.intrigue_state.get('npc_prisons', {})]
        # Read existing offices without initializing DLC politics in a query.
        office = game.intrigue_state.get('factions', {}).get('sect:'+sect.id, {})
        controller = office.get('controller_id')
        if controller:
            leader = next((n for n in members if n.id == controller), None)
        else:
            leader = max(members, key=lambda n: (n.realm_index, n.layer, -n.age), default=None)
            if (game.player.faction_id == sect.id and game.player.alive and
                    (sect.founded_by_player or leader and game.player.realm_index >= leader.realm_index)):
                return None  # A player office never silently signs an NPC order.
        if not leader or research_assignment(game, leader.id):
            return None
        return dict(faction_id=sect.id, issuer_id=leader.id, scope='recon_only',
                    source='existing_office' if controller else 'native_sect_leadership')

    def player_reason(game, location=None):
        p = game.player
        assembly = game.buddhist_state.get('assembly')
        if not p.alive:
            return '此生已经结束'
        if (p.imprisonment or p.ghost_captor or game.active_trial or game.guixu_state.get('player_session')
                or assembly and assembly.get('world') == p.world and assembly.get('location') == p.location_id):
            return '须先结束受控状态或专属活动'
        if game.pending_event:
            return '请先处理当前事件'
        if game.spatial_state.get('current') or p.world != 'human':
            return '须亲自返回人界地面参与'
        if location and p.location_id != location:
            return '须亲自到无棣原递交消息' if location == 'wudi_plain' else '须亲自到岚疆草原接触先遣'
        return None

    def person_reason(game, npc):
        if not npc or not npc.alive:
            return '先遣人物已经陨落或失联'
        if not is_free(npc) or npc.id in game.intrigue_state.get('npc_prisons', {}) or instance_of(game, npc.id):
            return '先遣人物受控或身在独立空间'
        if npc.realm_index > ROUTE.maximum_realm:
            return '实际修为超出有限路线承载，伪装不能通行'
        if any(npc.id in ids for war in game.wars if war.get('status') in {'active', 'peace_ready'}
               for ids in war.get('roster', {}).values()):
            return '人物已有其他战争部署'
        relations = [game.player.master, game.player.dao_companion, *game.player.dao_friends,
                     *game.player.disciples, *game.player.concubines, *game.player.party, *game.player.disciple_requests]
        if any(r and (r.get('npc_id') or r.get('id')) == npc.id for r in relations):
            return '人物已有同行或关系职责'
        return None

    def candidate(game):
        permit = authority(game)
        if not permit:
            return None
        sect = game.sects[SOURCE_FACTION]
        home = faction_site(copy.deepcopy(sect))['id']
        for npc in sorted(sect.npcs, key=lambda n: n.id):
            if (npc.id == permit['issuer_id'] or not 3 <= npc.realm_index <= 4 or npc.world != sect.world
                    or npc.location_id not in {None, home} or research_assignment(game, npc.id) or person_reason(game, npc)):
                continue
            plan = engine.maps.travel_plan(sect.world, home, ROUTE.source_location, npc.realm_index) if home != ROUTE.source_location else None
            if plan and plan.status != 'ok':
                continue
            return dict(person_id=npc.id, home=home, road=list(plan.route) if plan else [home],
                        road_years=plan.years if plan else 0, authority=permit)
        return None

    def deploy(game, person_id, home):
        sect = game.sects[SOURCE_FACTION]
        npc = next(n for n in sect.npcs if n.id == person_id)
        if person_id in game.world_npcs or person_id in game.notable_npcs:
            raise ValueError('人物在多个名册中重复出现')
        sect.npcs = [n for n in sect.npcs if n.id != person_id]
        npc.faction_id, npc.location_id = sect.id, home
        game.world_npcs[npc.id] = npc  # Same identity; world annual owns all subsequent growth.

    def route_reason(game, row, phase):
        npc = engine._dependencies.heavens.resolve_person(game, row['person_id'])
        reason = person_reason(game, npc)
        if reason:
            return reason
        source = ('human', ROUTE.destination_location) if phase in {'scouting', 'returning'} else ('demon', row['home'] if phase == 'gathering' else ROUTE.source_location)
        if (npc.world, npc.location_id) != source:
            return '人物已离开实际出发地点，行程暂缓'
        if phase in {'outbound', 'returning'}:
            destination = ROUTE.destination_world if phase == 'outbound' else ROUTE.source_world
            if not WORLD_SYSTEMS['world_profiles'][destination]['enabled']:
                return '目标界面暂不可达，保留原地人物和返程预算'
        if phase in {'gathering', 'homeward'} and row['road_years']:
            origin, target = (row['home'], ROUTE.source_location) if phase == 'gathering' else (ROUTE.source_location, row['home'])
            plan = engine.maps.travel_plan('demon', origin, target, npc.realm_index)
            if plan.status != 'ok' or plan.years > row['road_years']:
                return '原道路或通行能力已改变，行程暂缓'
        return None

    def move(game, row, world, location):
        npc = game.world_npcs[row['person_id']]
        move_world(npc, world, game.player.age, WORLD_SYSTEMS.get('transcendent_combat', {}))
        npc.location_id = location

    return dict(frontier_authority=authority, frontier_candidate=candidate, frontier_deploy=deploy,
                frontier_player_reason=player_reason, frontier_route_reason=route_reason, frontier_move=move)
