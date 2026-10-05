"""Finite ruins use the existing spatial, resource and combat capabilities."""
from ...rules import max_mp, can_player_practice_technique
from ...system import spatial
from ...system.heavens.definitions import RUINS_ID
from ...system.formation_system import make_formation_material_instance
from ..actions.exploration import move_world


def bind_ruins(engine):
    def facts(game):
        p = game.player
        ruins = game.heavens_state.get('runtime', {}).get('ruins')
        location = ruins['definition']['location_id'] if ruins else engine._dependencies.heavens.get_definitions().ruins.location_id
        scene = spatial.current(game)
        inside = bool(ruins and p.world == 'rift' and scene and scene['id'] == ruins['scene_id'])
        reason = None
        assembly = game.buddhist_state.get('assembly')
        if not p.alive:
            reason = '此生已经结束'
        elif (p.imprisonment or p.ghost_captor or game.active_trial or game.guixu_state.get('player_session')
              or assembly and assembly.get('world') == p.world and assembly.get('location') == p.location_id):
            reason = '请先结束拘禁、劫战或专属活动'
        activity = reason
        if activity is None and (not 4 <= p.realm_index <= 8 or p.cultivation_suppression or p.sealed_cultivation):
            activity = '此处机关仅支持未封印、未压制的四至八阶本体修士，可先退出遗址'
        entry = activity
        if entry is None and (p.world != 'human' or p.location_id != location or scene):
            entry = '须在人界无棣原亲自进入'
        equipped = [row for row in [p.technique, *(p.combat_techniques or [])] if row]
        combat_reason = '灵根属性与已装备功法不合，须先调整战斗预案' if any(not can_player_practice_technique(p, row.element) for row in equipped) else None
        return dict(alive=p.alive, inside=inside, blocked_reason=reason or ('请先处理当前事件' if game.pending_event else None),
                    physical_reason=activity, activity_reason=activity, entry_reason=entry, mp=p.mp, max_mp=max_mp(p),
                    combat_reason=combat_reason, stones=sum(row.quantity for row in p.inventory if row.id == 'spirit_stone'))

    def material(game, scene_id):
        definitions = sorted((row for row in engine._formation_material_defs().values()
                              if row.get('world') == 'human' and row.get('tier') == 4), key=lambda row: row['id'])
        if not definitions:
            raise ValueError('因果遗址缺少本体四阶阵材来源')
        reward = make_formation_material_instance(definitions[0], source='因果遗址预留', origin_world='human')
        reward['id'] = f'{scene_id}-material-0'
        return reward

    def enter(game, ruins, rng):
        state = spatial.ensure(game)
        scene = state['instances'].get(ruins['scene_id'])
        if scene is None:
            scene = dict(id=ruins['scene_id'], name='因果遗址', kind='heavens', tier=0,
                heavens_target=RUINS_ID, location_id='causal_hall',
                locations=[dict(id='causal_hall', name='回潮阵室', description='异界阵纹与阵芯一同明灭，入口通向人界无棣原。',
                    combat_terrain='狭窄', combat_conditions=[], qi_gain_efficiencies=dict(spirit=1, demon=1, monster=1, yin=1))],
                edges=[], materials=[], techniques=[], npc_ids=[], sects=[], joined_sect=None,
                visits=0, explored=0, power_ceiling=None, resource_ceiling=None,
                power_description='有限机关遗址。', resource_description='抄本、阵材和唯一阵芯均有固定归属。')
            state['instances'][scene['id']] = scene
        state['current'] = scene['id']
        scene['visits'] += 1
        move_world(engine._exploration_dependencies(), game, 'rift', rng)

    def leave(game, ruins, rng):
        spatial.ensure(game)['current'] = None
        move_world(engine._exploration_dependencies(), game, ruins['definition']['world'], rng,
                   location=ruins['definition']['location_id'])

    def fight(game, ruins, rng):
        guardian = ruins['guardian']
        power = ruins['definition']['guardian_power'] * (1 - .15 * guardian['wounds'])
        member = dict(npc_id=f'{ruins["scene_id"]}-guardian', name='回潮守阵机关', realm_index=4, layer=1,
                      path='dao', kind='mechanical', power=power, wounds=guardian['wounds'], world='rift')
        target = dict(target_name=member['name'], target_power=power, target_realm_index=4, target_layer=1,
                      combat_type='mechanical', objective='repel', enemy_objective='repel', members=[member],
                      natural_terrain='狭窄', artificial_conditions=[], max_rounds=12)
        before = game.last_combat_report
        result, summary = engine._combat(game, target, True, rng)
        report = game.last_combat_report if game.last_combat_report is not before else {}
        wounds = max(guardian['wounds'], member.get('wounds', 0), min(4, int((1-report.get('enemy_hp_ratio', 1))*4)))
        return result, summary, wounds

    return dict(read_ruins_facts=facts, ruins_material=material, enter_ruins=enter, leave_ruins=leave, fight_ruins=fight)
