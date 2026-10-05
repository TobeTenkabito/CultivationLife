"""Read-only survey facts and authoritative spatial membership transfers."""
from ...npc_custody import is_free
from ...content_registry import WORLD_SYSTEMS
from ...system.combat.npc_lifecycle import move_world
from ...person_assignments import research_assignment
from ...spatial_people import instance_of
from ...system.heavens import survey


def bind_survey(engine, ports):
    def facts(game, person_id=None):
        scene = game.heavens_state.get('runtime', {}).get('ruins')
        row = survey.get(game)
        identity = row['person_id'] if row else person_id
        npc = ports().resolve_person(game, identity) if identity else None
        reason = None
        if not npc or not npc.alive:
            reason = '勘察人物已经陨落或不在权威名册'
        elif not is_free(npc) or (engine._intrigue_enabled() and npc.id in game.intrigue_state.get('npc_prisons', {})):
            reason = '勘察人物正在受控，须待其真实获释'
        elif npc.id not in game.world_npcs or npc.faction_id:
            reason = '本人已有其他名册职责'
        elif not 4 <= npc.realm_index <= 5:
            reason = '本人不符合四至五阶人界勘察资格'
        elif row and row['status'] == 'active' and row['phase'] != 'outbound':
            if npc.world != 'rift' or npc.location_id != 'causal_hall' or instance_of(game, npc.id) != scene['scene_id']:
                reason = '本人须恢复自由并回到同一遗址才能继续'
        elif npc.world != 'human' or instance_of(game, npc.id):
            reason = '本人不在人界，不能赴约或会面'
        elif row and row['status'] == 'active' and npc.location_id != row['origin_location']:
            reason = '本人已离开原出发位置，赴约暂缓'
        if not reason:
            relations = [game.player.master, game.player.dao_companion, *game.player.dao_friends,
                         *game.player.disciples, *game.player.concubines, *game.player.party, *game.player.disciple_requests]
            if any(r and (r.get('npc_id') or r.get('id')) == npc.id for r in relations):
                reason = '本人已有关系或同行职责'
            elif any(npc.id in ids for war in game.wars if war.get('status') in {'active', 'peace_ready'}
                     for ids in war.get('roster', {}).values()):
                reason = '本人已有战事部署'
        current = game.spatial_state.get('instances', {}).get(game.spatial_state.get('current'), {})
        location = current.get('location_id', game.player.location_id)
        together = bool(npc and scene and npc.world == game.player.world and npc.location_id == location
                        and (npc.world == 'human' and npc.location_id == scene['definition']['location_id']
                             or npc.world == 'rift' and instance_of(game, npc.id) == game.spatial_state.get('current') == scene['scene_id']))
        departure_lost = bool(row and row['phase'] == 'outbound' and npc and
                              (npc.world != 'human' or not 4 <= npc.realm_index <= 5
                               or npc.location_id != row['origin_location']))
        return dict(alive=bool(npc and npc.alive), blocked_reason=reason, together=together,
                    departure_lost=departure_lost)

    def candidates(game, *, autonomous=False):
        if survey.get(game) or not autonomous and ports().read_ruins_facts(game)['entry_reason']:
            return []
        return [dict(id=npc.id, name=npc.name, affinity=npc.affinity)
                for npc in sorted(game.world_npcs.values(), key=lambda p:p.id)
                if (autonomous or (npc.affinity or 0) >= 20) and not research_assignment(game, npc.id)
                and not facts(game, npc.id)['blocked_reason']]

    def move(game, phase):
        ruins = game.heavens_state['runtime']['ruins']
        row = ruins['survey']
        reason = facts(game)['blocked_reason']
        if reason:
            raise ValueError(reason)
        if row['status'] != 'active' or row['phase'] != phase or row['progress'] != survey.DURATIONS[phase]:
            raise ValueError('尚未完成勘察人物的实际通行时间')
        npc = ports().resolve_person(game, row['person_id'])
        scene = game.spatial_state['instances'][ruins['scene_id']]
        if phase == 'outbound':
            if npc.id in scene['npc_ids']:
                raise ValueError('人物已在遗址中，不能重复入场')
            scene['npc_ids'].append(npc.id)
            move_world(npc, 'rift', game.player.age, WORLD_SYSTEMS.get('transcendent_combat', {}))
            npc.location_id = 'causal_hall'
        else:
            scene['npc_ids'].remove(npc.id)
            move_world(npc, 'human', game.player.age, WORLD_SYSTEMS.get('transcendent_combat', {}))
            npc.location_id = ruins['definition']['location_id']

    return dict(read_survey_facts=facts, survey_candidates=candidates, move_surveyor=move,
                advance_survey=lambda game, outside: survey.year_step(ports(), game, outside=outside))
