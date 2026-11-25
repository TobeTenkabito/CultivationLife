"""Finite ruins use the existing spatial, resource and combat capabilities."""
from ...definition_data import definition as _content_definition
from ...rules import max_mp, can_player_practice_technique
from ...system import spatial
from ...system.heavens.definitions import RUINS_ID
from ...system.heavens import survey
from ...system.formation_system import make_formation_material_instance
from ..actions.exploration import move_world
from .heavens_guardians import fight_guardian


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
        combat_reason = '灵根属性与已装备功法不合，须先调整战斗预案' if any(not can_player_practice_technique(p, row) for row in equipped) else None
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

    def prepare(game, ruins):
        state = spatial.ensure(game)
        scene = state['instances'].get(ruins['scene_id'])
        if scene is None:
            scene = dict(**_content_definition(__name__, "RUINS"),
                         id=ruins['scene_id'],
                         heavens_target=RUINS_ID,
                         locations=[_content_definition(__name__, "prepare_id")])
            state['instances'][scene['id']] = scene
        return scene

    def enter(game, ruins, rng):
        scene = prepare(game, ruins)
        scene['visits'] += 1
        move_world(engine._exploration_dependencies(), game, 'rift', rng, instance_id=scene['id'])
        if 'player_known' in ruins:
            ruins['player_known'] = True
        survey.reveal(engine._dependencies.heavens, game)

    def leave(game, ruins, rng):
        move_world(engine._exploration_dependencies(), game, ruins['definition']['world'], rng,
                   location=ruins['definition']['location_id'])

    def fight(game, ruins, rng):
        return fight_guardian(engine, game, 'ruins', f'{ruins["scene_id"]}-guardian',
                              ruins['definition']['guardian_power'], ruins['guardian']['wounds'], rng)

    return dict(read_ruins_facts=facts, ruins_material=material, enter_ruins=enter, leave_ruins=leave, fight_ruins=fight, prepare_ruins=prepare)
