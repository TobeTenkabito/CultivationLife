"""Mirror anomaly adapters reuse world transitions, spatial isolation and combat."""
from ...rules import max_mp
from ...system import spatial
from ...system.heavens.definitions import MIRROR_ID
from ...system.formation_system import make_formation_material_instance
from ..actions.exploration import move_world


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

    def enter(game, mirror, rng):
        state = spatial.ensure(game)
        scene = state['instances'].get(mirror['scene_id'])
        if scene is None:
            scene = dict(id=mirror['scene_id'], name='镜律场域', kind='heavens', tier=0,
                heavens_target=MIRROR_ID, location_id='mirror_hall',
                locations=[dict(id='mirror_hall', name='三镜回廊', description='三处机关保存独立状态，入口通向人界穆陵沙漠。',
                    combat_terrain='狭窄', combat_conditions=[],
                    qi_gain_efficiencies=dict(spirit=1, demon=1, monster=1, yin=1))],
                edges=[], materials=[], techniques=[], npc_ids=[], sects=[], joined_sect=None,
                visits=0, explored=0, power_ceiling=None, resource_ceiling=None,
                power_description='有限机关场域。', resource_description='所得仅来自三处已登记机关，不生成随机战利品。')
            state['instances'][scene['id']] = scene
        state['current'] = scene['id']
        scene['visits'] += 1
        move_world(engine._exploration_dependencies(), game, 'rift', rng)

    def leave(game, mirror, rng):
        spatial.ensure(game)['current'] = None
        move_world(engine._exploration_dependencies(), game, mirror['definition']['world'], rng,
                   location=mirror['definition']['location_id'])

    def fight(game, mirror, chamber, rng):
        guardian = mirror['chambers'][chamber]['guardian']
        power = guardian['power'] * (1 - .15 * guardian['wounds'])
        member = dict(npc_id=f'{mirror["scene_id"]}-guardian-{chamber}', name=f'第 {chamber+1} 处守镜机关',
                      realm_index=4, layer=1, path='dao', kind='mechanical', power=power,
                      wounds=guardian['wounds'], world='rift')
        target = dict(target_name=member['name'], target_power=power, target_realm_index=4, target_layer=1,
                      combat_type='mechanical', objective='repel', enemy_objective='repel', members=[member],
                      natural_terrain='狭窄', artificial_conditions=[], max_rounds=12)
        before = game.last_combat_report
        result, summary = engine._combat(game, target, True, rng)
        report = game.last_combat_report if game.last_combat_report is not before else {}
        wounds = max(guardian['wounds'], member.get('wounds', 0), min(4, int((1-report.get('enemy_hp_ratio', 1))*4)))
        return result, summary, wounds

    return dict(read_mirror_facts=facts, mirror_materials=materials, enter_mirror=enter, leave_mirror=leave, fight_mirror=fight)
