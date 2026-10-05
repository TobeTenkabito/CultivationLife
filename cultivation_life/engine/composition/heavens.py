"""Explicit M1 wiring, including request-local cache publication."""
import copy

from ...content_registry import WORLD_SYSTEMS, REALMS
from ...models import SectNpc
from ...npc_custody import is_free
from ...relationship_records import find_person
from ...spatial_people import instance_of
from ...rules import max_mp, add_item, remove_item, can_player_practice_technique
from ...system.aperture_resources import true_realm
from ...system.heavens.definitions import HeavensDefinitions, SeaEchoDefinition
from ...system.heavens.dependencies import HeavensDependencies
from ...system.heavens import tasks
from ...system.combat.npc_lifecycle import initialize_native
from ...time_flow import advance_elapsed_year, settle_elapsed_time, ACTION_TIME
from ...system.upper_institutions import advance_time
from ..transactions import request_games


def bind_heavens(engine) -> HeavensDependencies:
    def get_definitions():
        config = WORLD_SYSTEMS['heavens_framework']
        return HeavensDefinitions(generation_available=config['enabled'],
                                  sea_echo=SeaEchoDefinition(**config.get('sea_echo', {})))

    def read_actor_facts(game):
        p = game.player
        assembly = game.buddhist_state.get('assembly')
        reason = None
        if not p.alive:
            reason = '此生已经结束'
        elif (p.imprisonment or p.ghost_captor or game.active_trial or game.guixu_state.get('player_session')
              or assembly and assembly.get('world') == p.world and assembly.get('location') == p.location_id):
            reason = '当前受控状态或专属活动尚未结束'
        elif p.world != 'celestial' or p.location_id != 'law_sea':
            reason = '须在仙界法则天海亲自参与'
        elif p.realm_index < 9 or p.cultivation_suppression:
            reason = '须具备未压制的九阶以上修为'
        physical_reason = reason
        if reason is None and game.pending_event:
            reason = '请先处理当前事件'
        return dict(alive=p.alive, blocked_reason=reason, physical_reason=physical_reason,
            can_discover=physical_reason is None and true_realm(p) >= 9,
            can_apply=physical_reason is None and p.immortal_power_converted and p.technique is not None
                and can_player_practice_technique(p, p.technique.element),
            true_realm=true_realm(p), stones=sum(i.quantity for i in p.inventory if i.id == 'spirit_stone'),
            mp=p.mp, max_mp=max_mp(p))

    def create_visitor(game, identity):
        if find_person(game, identity, include_inactive=True) is not None:
            raise ValueError('合作人物身份已存在，不能重建或复活')
        npc = SectNpc(identity, '观澜散人', '法则天海访学者',
            9, 1, 3000, None, spirit_root='supreme_water', world='celestial',
            affinity=0, location_id='law_sea', encountered_player=True)
        initialize_native(npc, WORLD_SYSTEMS.get('transcendent_combat', {}), now=game.player.age)
        game.world_npcs[identity] = npc

    def person_available(game, identity):
        npc = find_person(game, identity, include_inactive=True)
        if (npc is None or not is_free(npc) or npc.world != 'celestial' or npc.location_id != 'law_sea'
                or npc.faction_id or identity in {row.get('id') if isinstance(row, dict) else row for row in game.player.party}
                or instance_of(game, identity) or engine._intrigue_is_imprisoned(game, identity)):
            return False
        return not any(identity in ids for war in game.wars if war.get('status') in {'active', 'peace_ready'}
                       for ids in war.get('roster', {}).values())

    def quote_materials(game):
        definitions = engine._formation_material_defs()
        return [copy.deepcopy(row) for row in game.player.formation_materials
                if row.get('id') and not row.get('dynamic_definition')
                and definitions.get(row.get('material_id'), {}).get('tier') == 9
                and definitions.get(row.get('material_id'), {}).get('world') == 'celestial'
                and row.get('acquired_tier', 9) == 9]

    def reserve_resources(game, stones, material_id, mp):
        material = next((row for row in quote_materials(game) if row['id'] == material_id), None) if material_id else None
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
    )
    return ports
