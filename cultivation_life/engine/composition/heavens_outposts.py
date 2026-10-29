"""Frontier adapters reuse native authority, roads and formal movement."""
from ...content_registry import WORLD_SYSTEMS, ITEM_CATALOG
from ...relationship_records import find_person
from ...npc_custody import sync_offspring
from ...person_assignments import research_assignment
from ...system.faction_geography import faction_site
from ...system.organization_authority import player_controls
from ...system.organization_heritage import controls
from ...system.combat.npc_lifecycle import move_world
from ...system.world_transition_system import finish_world_transition, cultivation_ceiling
from ...system.heavens.outpost_definitions import ENDPOINTS, route_id
from ...system.heavens.outpost_runtime import free


def bind_outposts(engine, ports):
    def owner(game, identity):
        return game.family if game.family and game.family.id == identity else game.sects.get(identity)

    def owners(game):
        identities = {game.player.faction_id}
        if game.family:
            identities.add(game.family.id)
        identities.update(row['owner_id'] for row in game.heavens_state.get('runtime', {}).get('outposts', {}).values()
                          if row['issuer_id'] == game.id)
        return [entity for key in sorted(i for i in identities if i) if (entity := owner(game, key))
                and entity.kind in {'sect', 'family'}]

    def control(game, entity, charter):
        if entity.extinct or not game.player.alive:
            return False
        if entity.world == game.player.world:
            return controls(game, entity)
        if not charter or charter['issuer_id'] != game.id:
            return False
        member = entity is game.family or game.player.faction_id == entity.id
        if not member:
            return False
        # A pre-issued local charter permits local frontier decisions only.
        # It never changes the generic cross-world governance check.
        return player_controls(game, entity, engine._sect_members(game, entity), member=member)

    def candidates(game, entity):
        home = faction_site(entity, persist=False)['id']
        relations = [game.player.master, game.player.dao_companion, *game.player.dao_friends,
                     *game.player.disciples, *game.player.concubines, *game.player.party, *game.player.disciple_requests]
        related = {r.get('npc_id') or r.get('id') for r in relations if r}
        war_ids = {i for w in game.wars if w.get('status') in {'active', 'peace_ready', 'withdrawing'}
                   for ids in w.get('roster', {}).values() for i in ids}
        return [dict(id=n.id, name=n.name) for n in sorted(engine._sect_members(game, entity), key=lambda n: n.id)
                if free(game, n) and n.world == entity.world and n.location_id in {None, home}
                and 1 <= n.realm_index <= 5 and n.id not in related | war_ids
                and (n.realm_index, n.layer) <= cultivation_ceiling(WORLD_SYSTEMS, 'demon' if entity.world == 'human' else 'human')
                and not research_assignment(game, n.id)]

    def road(game, world, origin, destination, rank):
        if origin == destination:
            return dict(years=0, route=[origin])
        plan = engine.maps.travel_plan(world, origin, destination, rank)
        return dict(years=plan.years, route=list(plan.route)) if plan.status == 'ok' else None

    def lane(game, row, returning=False, person_id=None):
        source, destination = (row['destination'], row['source']) if returning else (row['source'], row['destination'])
        if person_id:
            npc = find_person(game, person_id, include_inactive=True)
            ceiling = cultivation_ceiling(WORLD_SYSTEMS, destination)
            if not npc or ceiling and (npc.realm_index, npc.layer) > ceiling:
                return False
        return bool(WORLD_SYSTEMS['world_profiles'][source]['enabled'] and WORLD_SYSTEMS['world_profiles'][destination]['enabled']
                    and any(r['id'] == route_id(source, destination) and r['enabled'] and r['mode'] == 'expedition'
                            for r in WORLD_SYSTEMS['world_transition_routes']))

    def prepare(game, identity, entity, home):
        npc = find_person(game, identity, include_inactive=True)
        entity.npcs[:] = [n for n in entity.npcs if n.id != identity]
        game.notable_npcs.pop(identity, None)
        game.relationship_npcs.pop(identity, None)
        game.world_npcs[identity] = npc
        npc.faction_id, npc.location_id = entity.id, home

    def move_npc(game, identity, world, location):
        npc = find_person(game, identity, include_inactive=True)
        if npc.world != world:
            move_world(npc, world, game.player.age, WORLD_SYSTEMS.get('transcendent_combat', {}))
        npc.location_id = location
        sync_offspring(game, npc)

    def player_plan(game, row, returning=False):
        p = game.player
        source, destination = (row['destination'], row['source']) if returning else (row['source'], row['destination'])
        if (p.world, p.location_id) != (source, ENDPOINTS[source]):
            raise ValueError('须亲自抵达' + ENDPOINTS[source] + '的开拓通行落点')
        visit = row['visit']
        from ...system.heavens.state import active_task
        task = active_task(game.heavens_state.get('runtime'))
        underway = task and task['target_id'] == row['id'] and task['action'] == 'outpost_return'
        if returning:
            if not visit or visit['status'] != 'visiting' or visit['return_fare'] < 800 and not underway:
                raise ValueError('没有已付费且尚未结束的开拓返程许可')
        else:
            if not control(game, owner(game, row['owner_id']), row) or row['status'] in {'withdrawing', 'closed'}:
                raise ValueError('原开拓授权已失效或驻地正在撤回')
            if visit and visit['status'] in {'preparing', 'visiting'} and not (task and task['action'] == 'outpost_depart'):
                raise ValueError('已有未结束的开拓个人行程')
        if p.party or any(n.alive and n.roster_state == 'held' and (n.custody or {}).get('holder_id') == game.id for n in game.inactive_npcs.values()):
            raise ValueError('开拓个人通道只容一人，请先安置同行者与俘虏')
        return engine._plan_world_transition(game, destination, 'expedition',
            route_id=route_id(source, destination), arrival_location=ENDPOINTS[destination], reason='组织开拓往返')

    def move_player(game, row, returning, rng):
        plan = player_plan(game, row, returning)
        engine._apply_world_transition(game, plan)
        finish_world_transition(game, rng, engine._refresh_world_market)

    def local_people(game, row, location, identity):
        entity = owner(game, identity)
        if not entity or entity.extinct:
            return []
        home = faction_site(entity, persist=False)['id']
        return [npc for npc in engine._sect_members(game, entity)
                if free(game, npc) and npc.world == row['destination']
                and (npc.location_id or home) == location
                and not research_assignment(game, npc.id)]

    def site_reason(game, row, location):
        from ...system.heavens.local_control import occupied
        from ...system.heavens.campaign_definitions import SOURCE
        return '当地有他方实际驻军，不能绕过封锁经营' if occupied(game, row['destination'], location) and row['owner_id'] != SOURCE else None

    def advance_job(game, row, unit):
        from ...system.heavens.outpost_development import advance_job
        advance_job(ports(), game, row, unit)

    def end_job(game, row, unit):
        from ...system.heavens.outpost_development import end_job
        end_job(ports(), game, row, unit, lost=True)

    def settle_claims(game, row):
        from ...system.heavens.outpost_development import settle_claims, abandon
        if row['status'] in {'withdrawing', 'closed'}:
            abandon(game, row)
        else:
            settle_claims(ports(), game, row)

    def register_war(game, war):
        from ...system.war.creation import register
        engine._ensure_npc_formations(game)
        register(game, war, engine._append_war_log, engine._war_side_name)

    def war_round(game, war, rng, personal):
        from ...system.war import logistics
        from ...system.war.requirements import deployed_people
        before = war['war_score']
        if personal:
            engine._resolve_player_war_round(game, war, 'attacker', rng)
        else:
            logistics.begin_round(game, engine.maps, war, rng, 'attacker')
            contexts = engine._war_formation_contexts(game, war)
            lines = [engine._resolve_field_attack(game, war, 'attacker', rng, contexts)]
            if not engine._finish_war_by_morale(game, war):
                lines.append(engine._resolve_field_attack(game, war, 'defender', rng, contexts))
            war['battles'] += 1
            engine._wear_war_guard_arrays(game, war)
            engine._finish_war_by_morale(game, war)
            engine._append_war_log(game, war, '驻地部众会战', ' '.join(lines))
        if war['war_score'] > before:
            war['frontier']['victory_battles'] += 1
        # The ordinary one-sided empty-roster result is a real rout, not a
        # second battle. Preserve the underlying morale/scoring settlement.
        missing = [side for side in ('attacker', 'defender') if not deployed_people(game, war, side, arrived_only=True)]
        if missing:
            for side in missing:
                war['morale'][side] = 0.
            war['status'] = 'active'
            engine._finish_war_by_morale(game, war)

    def advance_war(game, row):
        from ...system.heavens.outpost_conquest import advance
        advance(ports(), game, row)

    def defenders(game, row, location, identity):
        people = local_people(game, row, location, identity)
        # The original guest helper adopts a faction on read. Quotes must use
        # the same original guest records without invoking that mutation.
        record = game.intrigue_state.get('factions', {}).get(f'sect:{identity}', {})
        guests = [g.get('npc_id') for g in record.get('guests', [])] if engine._intrigue_enabled() else []
        deployed = {i for w in game.wars if w.get('status') in {'active', 'peace_ready', 'withdrawing'}
                    for ids in w.get('roster', {}).values() for i in ids}
        selected = []
        for person in guests:
            npc = find_person(game, person, include_inactive=True)
            if (free(game, npc) and npc.id not in deployed and npc.world == row['destination'] and npc.location_id == location
                    and not research_assignment(game, npc.id)):
                selected.append(npc)
        regular = sorted(people, key=engine._npc_power, reverse=True)[:int(engine._war_rules().get('roster_cap', 24))]
        by_id = {n.id: n for n in [*regular, *selected]}
        chosen = list(by_id.values())
        if len(chosen) > 48:
            raise ValueError('当地原守军及防御客卿超出本期战役容量，不能省略防御保证')
        return dict(people=chosen, guests=[n.id for n in chosen if n.id in guests])

    return dict(outpost_owner=owner, outpost_owners=owners, outpost_control=control,
                outpost_candidates=candidates, outpost_road=road, outpost_lane=lane,
                outpost_prepare_npc=prepare, outpost_move_npc=move_npc,
                outpost_player_plan=player_plan, outpost_move_player=move_player,
                outpost_item_name=lambda key: ITEM_CATALOG[key.removeprefix('item:')].name,
                outpost_maps=lambda: engine.maps, outpost_local_people=local_people, outpost_site_reason=site_reason,
                advance_outpost_job=advance_job, end_outpost_job=end_job, outpost_settle_claims=settle_claims,
                outpost_organizations=lambda game: [*game.sects.values(), *([game.family] if game.family else [])],
                outpost_register_war=register_war, outpost_war_round=war_round, advance_outpost_war=advance_war,
                outpost_defenders=defenders,
                outpost_conclude_war=lambda game, war, term: engine._conclude_war(game, war, term, 'attacker'),
                outpost_vassal_cost=lambda: engine._dependencies.war.peace.WAR_TERM_DEFS['vassal'][1])
