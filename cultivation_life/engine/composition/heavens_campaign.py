"""Military ports read real offices and reuse map, item, combat and custody services."""
import copy

from ...content_registry import WORLD_SYSTEMS
from ...npc_custody import is_free, release_person
from ...person_assignments import research_assignment
from ...spatial_people import instance_of
from ...system.faction_geography import faction_site
from ...system.formation_system import make_formation_material_instance
from ...system.combat.npc_lifecycle import move_world
from ...system.combat.npc_battle import resolve_local_engagement
from ...system.doctrine.provider import battle_sources
from ...system.heavens.campaign_definitions import SOURCE, SOURCE_SITE, TARGET_SITE, REPORT_SITE


def bind_campaign(engine):
    def person(game, identity):
        return engine._dependencies.heavens.resolve_person(game, identity)

    def free(game, npc):
        return bool(npc and is_free(npc) and not instance_of(game, npc.id)
                    and npc.id not in game.intrigue_state.get('npc_prisons', {}))

    def authority(game, faction, scope):
        sect = game.sects.get(faction)
        if not sect or sect.extinct:
            return None
        members = [n for n in engine._sect_members(game, sect) if free(game, n) and n.world == sect.world]
        office = game.intrigue_state.get('factions', {}).get('sect:'+faction, {})
        controller = office.get('controller_id')
        leader = next((n for n in members if n.id == controller), None) if controller else max(
            members, key=lambda n: (n.realm_index, n.layer, -n.age), default=None)
        if not controller and game.player.alive and game.player.faction_id == faction and (
                sect.founded_by_player or leader and game.player.realm_index >= leader.realm_index):
            return None
        if not leader or research_assignment(game, leader.id):
            return None
        return dict(faction_id=faction, issuer_id=leader.id, scope=scope,
                    source='existing_office' if controller else 'native_sect_leadership')

    def roster(game, faction, roles):
        permit = authority(game, faction, 'build_and_supply' if faction == SOURCE else 'guard_lanjiang')
        if not permit:
            return None
        sect = game.sects[faction]
        home = faction_site(copy.deepcopy(sect))['id']
        destination = SOURCE_SITE if faction == SOURCE else TARGET_SITE
        relations = [game.player.master, game.player.dao_companion, *game.player.dao_friends,
                     *game.player.disciples, *game.player.concubines, *game.player.party, *game.player.disciple_requests]
        occupied = {r.get('npc_id') or r.get('id') for r in relations if r}
        occupied.update(n for war in game.wars if war.get('status') in {'active', 'peace_ready'}
                        for ids in war.get('roster', {}).values() for n in ids)
        result = []
        for npc in sorted(engine._sect_members(game, sect), key=lambda n: (n.realm_index, n.id)):
            if (not free(game, npc) or npc.id == permit['issuer_id'] or npc.id in occupied
                    or research_assignment(game, npc.id) or not 3 <= npc.realm_index <= 5
                    or npc.world != sect.world or npc.location_id not in {None, home}):
                continue
            plan = engine.maps.travel_plan(sect.world, home, destination, npc.realm_index)
            if plan.status != 'ok' or plan.years < 1:
                continue
            result.append(dict(person_id=npc.id, faction_id=faction, role=roles[len(result)], home=home,
                               road=list(plan.route), road_years=plan.years, phase='gathering',
                               duration=plan.years, progress=0, observed=False, reason=None))
            if len(result) == len(roles):
                return dict(permit=permit, units=result)
        return None

    def deploy(game, unit):
        npc = person(game, unit['person_id'])
        sect = game.sects[unit['faction_id']]
        if not free(game, npc):
            raise ValueError('军事人物已不可用')
        sect.npcs[:] = [n for n in sect.npcs if n.id != npc.id]
        game.notable_npcs.pop(npc.id, None)
        game.world_npcs[npc.id] = npc
        npc.location_id, npc.faction_id = unit['home'], sect.id

    def facts(game, unit):
        npc = person(game, unit['person_id'])
        return dict(alive=bool(npc and npc.alive), free=free(game, npc),
                    held_by_player=bool(npc and npc.roster_state == 'held' and (npc.custody or {}).get('holder_id') == game.id),
                    world=npc.world if npc else None, location=npc.location_id if npc else None,
                    rank=npc.realm_index if npc else 0, wounds=npc.wounds if npc else 4,
                    name=npc.name if npc else '已登记人物')

    def route(game, world, origin, destination, rank, duration):
        if not WORLD_SYSTEMS['world_profiles'][world]['enabled']:
            return False
        if origin == destination:
            return True
        plan = engine.maps.travel_plan(world, origin, destination, rank)
        return plan.status == 'ok' and plan.years <= duration

    def move(game, unit, world, location):
        npc = person(game, unit['person_id'])
        move_world(npc, world, game.player.age, WORLD_SYSTEMS.get('transcendent_combat', {}))
        npc.location_id = location

    def materials(game, world, prefix, count):
        rank = 6 if world == 'spirit' else 4
        definitions = sorted((d for d in engine._formation_material_defs().values()
                              if d['world'] == world and d['tier'] == rank), key=lambda d: d['id'])
        if not definitions:
            raise ValueError('缺少本体阵材定义')
        result = []
        for index in range(count):
            item = make_formation_material_instance(definitions[index % len(definitions)],
                    source='岚疆有限专项储备', origin_world=world)
            item['id'] = f'{game.id}-{prefix}-{index}'
            result.append(item)
        return result

    def fight(game, identity, capture, rng):
        npc = person(game, identity)
        member = dict(npc_id=npc.id, name=npc.name, power=engine._npc_power(npc), realm_index=npc.realm_index,
                      layer=npc.layer, faction_id=npc.faction_id, path=npc.path, race=npc.race)
        target = dict(npc_id=npc.id, faction_id=npc.faction_id, target_name=npc.name,
                      target_power=member['power'], target_realm_index=npc.realm_index,
                      target_layer=npc.layer, combat_type='cultivator', members=[member],
                      action='capture' if capture else 'repel', capture=capture,
                      objective='capture' if capture else 'repel', enemy_objective='repel',
                      non_story_combat=True, max_rounds=12)
        return engine._combat(game, target, True, rng)

    def funding(game, action, row=None, materials=None):
        from ...system.economy import campaign_finance as finance
        from ...system.heavens.campaign_definitions import CAMPAIGN_ID, BUDGET, DEFENSE_BUDGET, DEFENDER, INITIAL_SUPPLY, DONOR, AID_BUDGET
        if action == 'prepare':
            return finance.prepare(game,engine.maps,CAMPAIGN_ID,'attacker',SOURCE,'demon',SOURCE_SITE,
                BUDGET,INITIAL_SUPPLY,sum(i['base_value'] for i in materials))
        if action == 'defense':
            return finance.prepare(game,engine.maps,CAMPAIGN_ID,'defender',DEFENDER,'human',TARGET_SITE,DEFENSE_BUDGET)
        if action == 'aid':
            entity=game.sects.get(DONOR)
            return bool(entity and finance.prepare(game,engine.maps,CAMPAIGN_ID,'aid',DONOR,'spirit',
                faction_site(entity)['id'],AID_BUDGET,materials=sum(i['base_value'] for i in materials)))
        coverage=1.
        for side,owner,world,site,budget in [('attacker',SOURCE,'demon',SOURCE_SITE,row['budget']),
                ('defender',DEFENDER,'human',TARGET_SITE,(row.get('defense') or {}).get('budget'))]:
            if not budget:continue
            if side=='defender' and row['defense']['status']=='declined':continue
            key=finance.address(CAMPAIGN_ID,side)
            if key not in game.economy_v2.get('campaigns',{}):
                # Existing transported items stay in their old unique counters.
                # Only future cash commitment is adopted, on an actual year step.
                if not finance.prepare(game,engine.maps,CAMPAIGN_ID,side,owner,world,site,max(0,budget['total']-budget['spent'])):
                    if side=='attacker':coverage=0.
                    continue
                game.economy_v2['campaigns'][key]['charged']=budget['spent']
            present=[u for u in row['units'] if u['faction_id']==owner and u['phase']=='stationed']
            forward=side=='attacker' and any(facts(game,u)['world']=='human' for u in present)
            frontworld,frontsite=('human',TARGET_SITE) if forward else (world,site)
            ratio=finance.settle(game,engine.maps,CAMPAIGN_ID,side,budget['spent'],frontworld,frontsite,
                portal_scale=len(present) if side=='attacker' and row['gate']['state']=='open' else 0,
                finished=row['status'] in {'withdrawn','failed'} or bool(budget['refunded']))
            coverage=min(coverage,ratio) if side=='attacker' else coverage
        aid=row.get('aid')
        if aid and aid['status']!='declined':
            book=game.economy_v2.get('campaigns',{}).get(finance.address(CAMPAIGN_ID,'aid'))
            if book:
                finance.settle(game,engine.maps,CAMPAIGN_ID,'aid',aid['spent'],book['world'],book['location'],
                    finished=aid['status'] in {'arrived','claimed','cancelled'})
        return coverage

    def battle(game, attacker, defender, rng):
        a, b = person(game, attacker), person(game, defender)
        books=game.economy_v2.get('campaigns',{})
        def factor(side):
            coverage=books.get(f'campaign:lanjiang_gate:{side}',{}).get('coverage',0.)
            return 1. if coverage>=1 else .95 if coverage>=.75 else .8 if coverage>=.5 else .55 if coverage>=.25 else .25
        return resolve_local_engagement([(a, engine._npc_power(a)*factor('attacker'))], [(b, engine._npc_power(b)*factor('defender'))],
            WORLD_SYSTEMS.get('transcendent_combat', {}), rng, now=game.player.age,
            sources=battle_sources(game, {a.id: a, b.id: b}))

    def escape_plan(game):
        p = game.player
        if p.world != 'human' or p.location_id != TARGET_SITE or not WORLD_SYSTEMS['world_profiles']['human']['enabled']:
            return None
        plan = engine.maps.travel_plan('human', TARGET_SITE, REPORT_SITE, p.realm_index,
                                      engine._monster_travel_multiplier(p, REPORT_SITE))
        return dict(years=plan.years, route=list(plan.route)) if plan.status == 'ok' and 0 < plan.years <= 1000 else None

    def escape(game):
        if not escape_plan(game):
            raise ValueError('原撤离道路不再通行')
        game.player.location_id = REPORT_SITE
        engine._clear_market(game)

    def relief(game, unit):
        npc = person(game, unit['person_id'])
        npc.wounds = max(0, npc.wounds-1)

    def release(game, unit):
        release_person(game, unit['person_id'])
        game.player.prisoners[:] = [p for p in game.player.prisoners if (p.get('npc_id') or p.get('id')) != unit['person_id']]

    return dict(campaign_authority=authority, campaign_roster=roster, campaign_deploy=deploy,
                campaign_facts=facts, campaign_road=route, campaign_move=move, campaign_materials=materials,
                campaign_fight=fight, campaign_battle=battle, campaign_finance=funding,
                campaign_escape_plan=escape_plan, campaign_escape=escape,
                campaign_relief=relief, campaign_release=release,
                campaign_world_open=lambda world: bool(WORLD_SYSTEMS['world_profiles'][world]['enabled']))
