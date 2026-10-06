"""Explicit M1 wiring, including request-local cache publication."""
import copy

from ...content_registry import WORLD_SYSTEMS, REALMS
from ...models import SectNpc
from ...npc_custody import is_free
from ...relationship_records import find_person
from ...spatial_people import instance_of
from ...rules import max_mp, add_item, remove_item, can_player_practice_technique
from ...system.aperture_resources import true_realm
from ...system.heavens.definitions import HeavensDefinitions, SeaEchoDefinition, ContactSite, CONTACT_SITES, MirrorDefinition, MIRROR_ID, RuinsDefinition, RUINS_ID, OmenDefinition, OMENS
from ...system.heavens.state import current_site, site_for, contacts, echo_site
from ...system.heavens.dependencies import HeavensDependencies
from ...system.heavens import tasks, omens
from ...system.combat.npc_lifecycle import initialize_native
from ...time_flow import advance_elapsed_year, settle_elapsed_time, ACTION_TIME
from ...system.upper_institutions import advance_time
from ..transactions import request_games
from .heavens_mirror import bind_mirror
from .heavens_ruins import bind_ruins
from .heavens_visits import bind_visits
from .heavens_missions import bind_missions
from .heavens_survey import bind_survey
from .heavens_frontier import bind_frontier
from ...person_assignments import research_assignment


def bind_heavens(engine) -> HeavensDependencies:
    def perception_realm(player):
        # Suppression changes usable power, not the cultivation already attained.
        return max(true_realm(player), int((player.cultivation_suppression or {}).get('realm_index', 0)))

    def get_definitions():
        config = WORLD_SYSTEMS['heavens_framework']
        return HeavensDefinitions(generation_available=config['enabled'],
            sea_echo=SeaEchoDefinition(**config.get('sea_echo', {})),
            mirror=MirrorDefinition(**config.get('mirror', {})),
            ruins=RuinsDefinition(**config.get('ruins', {})),
            omens=tuple(OmenDefinition(**row) for row in config['omens']) if 'omens' in config else OMENS,
            contact_sites=tuple(ContactSite(**row) for row in config['contact_sites']) if 'contact_sites' in config else CONTACT_SITES)

    def read_actor_facts(game, target_id=None):
        p = game.player
        site = site_for(ports, game, target_id) if target_id else current_site(ports, game)
        assembly = game.buddhist_state.get('assembly')
        reason = None
        if not p.alive:
            reason = '此生已经结束'
        elif (p.imprisonment or p.ghost_captor or game.active_trial or game.guixu_state.get('player_session')
              or assembly and assembly.get('world') == p.world and assembly.get('location') == p.location_id):
            reason = '当前受控状态或专属活动尚未结束'
        elif site is None:
            reason = '须在仙界、修罗界、幽冥界或轮回界的诸天联系地点参与'
        elif p.world != site.world or p.location_id != site.location_id:
            reason = f'须在{site.name.split(" · ")[0]}亲自参与'
        can_perceive = reason is None and not game.spatial_state.get('current') and perception_realm(p) >= 9
        if reason is None and (p.realm_index < 9 or p.cultivation_suppression or p.sealed_cultivation):
            reason = '须具备未封印、未压制的九阶以上修为'
        physical_reason = reason
        if reason is None and game.pending_event:
            reason = '请先处理当前事件'
        return dict(alive=p.alive, blocked_reason=reason, physical_reason=physical_reason,
            can_discover=can_perceive,
            can_apply=physical_reason is None and (p.world != 'celestial' or p.immortal_power_converted) and p.technique is not None
                and can_player_practice_technique(p, p.technique.element),
            true_realm=perception_realm(p), stones=sum(i.quantity for i in p.inventory if i.id == 'spirit_stone'),
            mp=p.mp, max_mp=max_mp(p))

    def read_omen_facts(game, target_id):
        p = game.player
        desc = omens.definition(ports, game, target_id)
        assembly = game.buddhist_state.get('assembly')
        reason = None
        if not p.alive:
            reason = '此生已经结束'
        elif (p.imprisonment or p.ghost_captor or game.active_trial or game.guixu_state.get('player_session')
              or assembly and assembly.get('world') == p.world and assembly.get('location') == p.location_id):
            reason = '请先结束拘禁、劫战或专属活动'
        elif not desc or p.world != desc['world'] or p.location_id != desc['location_id'] or game.spatial_state.get('current'):
            reason = '须亲自回到征兆出现的本界地点'
        return dict(alive=p.alive, physical_reason=reason, can_discover=reason is None,
                    blocked_reason=reason or ('请先处理当前事件' if game.pending_event else None), true_realm=perception_realm(p))

    def create_visitor(game, identity, site):
        if find_person(game, identity, include_inactive=True) is not None:
            raise ValueError('合作人物身份已存在，不能重建或复活')
        npc = SectNpc(identity, site.visitor_name, '诸天访学者',
            9, 1, 3000, None, spirit_root=site.spirit_root, world=site.world, path=site.visitor_path,
            affinity=0, location_id=site.location_id, encountered_player=True)
        initialize_native(npc, WORLD_SYSTEMS.get('transcendent_combat', {}), now=game.player.age)
        game.world_npcs[identity] = npc

    def person_available(game, identity):
        if research_assignment(game, identity):
            return False
        npc = find_person(game, identity, include_inactive=True)
        site = next((echo_site(echo) for echo in contacts(game.heavens_state.get('runtime')) if echo['visitor_id'] == identity), None)
        if (site is None or npc is None or not is_free(npc) or npc.world != site.world or npc.location_id != site.location_id
                or game.player.world != site.world or game.player.location_id != site.location_id
                or npc.faction_id or identity in {row.get('id') if isinstance(row, dict) else row for row in game.player.party}
                or instance_of(game, identity) or engine._intrigue_is_imprisoned(game, identity)):
            return False
        return not any(identity in ids for war in game.wars if war.get('status') in {'active', 'peace_ready'}
                       for ids in war.get('roster', {}).values())

    def quote_materials(game, target_id=None):
        definitions = engine._formation_material_defs()
        if target_id in {MIRROR_ID, RUINS_ID}:
            return [copy.deepcopy(row) for row in game.player.formation_materials
                    if row.get('id') and not row.get('dynamic_definition')
                    and definitions.get(row.get('material_id'), {}).get('world') == 'human'
                    and definitions.get(row.get('material_id'), {}).get('tier') == 4
                    and row.get('acquired_tier', 4) == 4]
        site = site_for(ports, game, target_id) if target_id else current_site(ports, game)
        if site is None:
            return []
        return [copy.deepcopy(row) for row in game.player.formation_materials
                if row.get('id') and not row.get('dynamic_definition')
                and definitions.get(row.get('material_id'), {}).get('tier') == 9
                and definitions.get(row.get('material_id'), {}).get('world') == site.world
                and row.get('acquired_tier', 9) == 9]

    def reserve_resources(game, stones, material_id, mp, *, target_id=None):
        material = next((row for row in quote_materials(game, target_id) if row['id'] == material_id), None) if material_id else None
        if material_id and material is None:
            raise ValueError('阵材已不可用')
        if game.player.mp < mp or (stones and not remove_item(game.player, 'spirit_stone', stones)):
            raise ValueError('资源不足')
        game.player.mp -= mp
        if material:
            game.player.formation_materials = [row for row in game.player.formation_materials if row['id'] != material_id]
        return dict(total=stones, spent=0, refunded=0, material=material, mp_paid=mp)

    def refund_resources(game, escrow):
        refund = escrow['total'] - escrow['spent'] - escrow['refunded']
        if refund:
            add_item(game.player, 'spirit_stone', refund)
        escrow['refunded'] += refund
        if escrow['material']:
            game.player.formation_materials.append(escrow['material'])
            escrow['material'] = None

    def settle_units(game, rng, units, elapsed, start_age, unit, news):
        scene = game.spatial_state.get('instances', {}).get(game.spatial_state.get('current'))
        if scene and scene.get('heavens_target') in {MIRROR_ID, RUINS_ID}:
            # Match isolated activities: no outside wages, politics or market clocks.
            if units and game.player.alive:
                engine._advance_natal_artifact(game, 'heavens_research', units)
            engine._compact_world_history(game)
            return
        advance_time(game, elapsed, unit)
        settle_elapsed_time(engine._dependencies.advancement.settlement, game, rng, news,
            action='heavens_research', units=units, start_age=start_age, elapsed_years=elapsed, policy=ACTION_TIME)
        if units:
            engine._ensure_market(game, rng)
        engine._compact_world_history(game)

    def accept_committed(game):
        games = request_games(engine)
        if games is not None:
            games[game.id] = game

    def invalidate_game(game_id):
        games = request_games(engine)
        if games is not None:
            games.pop(game_id, None)

    ports = HeavensDependencies(
        load_game=lambda game_id: engine._load(game_id),
        get_store=lambda: engine.store,
        get_definitions=get_definitions,
        accept_committed=accept_committed,
        invalidate_game=invalidate_game,
        read_actor_facts=read_actor_facts,
        read_omen_facts=read_omen_facts,
        create_visitor=create_visitor,
        resolve_person=lambda game, identity: find_person(game, identity, include_inactive=True),
        person_available=person_available,
        quote_materials=quote_materials,
        reserve_resources=reserve_resources,
        refund_resources=refund_resources,
        advance_year=lambda game, rng, news: advance_elapsed_year(engine._dependencies.advancement.year, game, rng, news),
        settle_activity_units=settle_units,
        unit_years=lambda game: int(WORLD_SYSTEMS['time_units'][str(game.player.realm_index)]),
        opportunity_base=lambda game: float(REALMS[game.player.realm_index].opportunity_base),
        grant_progress=lambda player, gain: engine._add_opportunity(player, gain),
        reconcile_tasks=lambda game: tasks.reconcile(ports, game),
        grant_stones=lambda game, amount: add_item(game.player, 'spirit_stone', amount),
        **bind_mirror(engine),
        **bind_ruins(engine),
        **bind_visits(engine, lambda: ports),
        **bind_missions(engine, lambda: ports),
        **bind_survey(engine, lambda: ports),
        **bind_frontier(engine),
    )
    return ports
