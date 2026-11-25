"""Mirror anomaly adapters reuse world transitions, spatial isolation and combat."""
from ...definition_data import definition as _content_definition
from ...rules import max_mp
from ...system import spatial
from ...system.heavens.definitions import MIRROR_ID
from ...system.heavens import survey
from ...system.formation_system import make_formation_material_instance
from ..actions.exploration import move_world
from .heavens_guardians import fight_guardian


def bind_mirror(engine):
    def facts(game):
        p = game.player
        mirror = game.heavens_state.get('runtime', {}).get('mirror')
        # Slots definitions are read through their public attributes before creation.
        location = mirror['definition']['location_id'] if mirror else engine._dependencies.heavens.get_definitions().mirror.location_id
        scene = spatial.current(game)
        inside = bool(mirror and p.world == 'rift' and scene and scene['id'] == mirror['scene_id'])
        reason = None
        if not p.alive:
            reason = '此生已经结束'
        elif p.imprisonment or p.ghost_captor or game.active_trial or game.guixu_state.get('player_session'):
            reason = '请先结束拘禁、劫战或专属活动'
        assembly = game.buddhist_state.get('assembly')
        if assembly and assembly.get('world') == p.world and assembly.get('location') == p.location_id:
            reason = '请先结束当前法会'
        activity_reason = reason
        if activity_reason is None and (not 4 <= p.realm_index <= 8 or p.cultivation_suppression or p.sealed_cultivation):
            activity_reason = '此处机关仅支持未封印、未压制的四至八阶本体修士，可先退出场域'
        entry_reason = activity_reason
        if entry_reason is None and (p.world != 'human' or p.location_id != location or scene):
            entry_reason = '须在人界穆陵沙漠亲自进入'
        return dict(alive=p.alive, inside=inside, blocked_reason=reason or ('请先处理当前事件' if game.pending_event else None),
                    physical_reason=activity_reason, activity_reason=activity_reason, entry_reason=entry_reason,
                    mp=p.mp, max_mp=max_mp(p))

    def materials(game, scene_id):
        definitions = sorted((row for row in engine._formation_material_defs().values()
                              if row.get('world') == 'human' and row.get('tier') == 4), key=lambda row: row['id'])
        if not definitions:
            raise ValueError('镜律场域缺少本体四阶阵材来源')
        result = []
        for index in range(2):
            material = make_formation_material_instance(definitions[index % len(definitions)], source='镜律场域预留', origin_world='human')
            material['id'] = f'{scene_id}-material-{index}'
            result.append(material)
        return result

    def prepare(game, mirror):
        state = spatial.ensure(game)
        scene = state['instances'].get(mirror['scene_id'])
        if scene is None:
            scene = dict(**_content_definition(__name__, "MIRROR"),
                         id=mirror['scene_id'],
                         heavens_target=MIRROR_ID,
                         locations=[_content_definition(__name__, "prepare_id")])
            state['instances'][scene['id']] = scene
        return scene

    def enter(game, mirror, rng):
        scene = prepare(game, mirror)
        if mirror.pop('capacity_pending', False):
            mirror['mana_capacity'] = max_mp(game.player) * mirror['definition']['capacity_fraction']
        if 'player_known' in mirror:
            mirror['player_known'] = True
        scene['visits'] += 1
        move_world(engine._exploration_dependencies(), game, 'rift', rng, instance_id=scene['id'])
        survey.reveal(engine._dependencies.heavens, game, target=MIRROR_ID)

    def leave(game, mirror, rng):
        move_world(engine._exploration_dependencies(), game, mirror['definition']['world'], rng,
                   location=mirror['definition']['location_id'])

    def fight(game, mirror, chamber, rng):
        guardian = mirror['chambers'][chamber]['guardian']
        return fight_guardian(engine, game, 'mirror', f'{mirror["scene_id"]}-guardian-{chamber}',
                              guardian['power'], guardian['wounds'], rng, chamber=chamber + 1)

    return dict(read_mirror_facts=facts, mirror_materials=materials, enter_mirror=enter, leave_mirror=leave, fight_mirror=fight, prepare_mirror=prepare)
