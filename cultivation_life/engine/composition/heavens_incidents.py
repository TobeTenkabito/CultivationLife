"""Ordinary-world incident ports using the player's existing resources."""
from ...content_registry import WORLD_SYSTEMS
from ...rules import max_hp, max_mp, can_player_practice_technique
from ...system.heavens.incident_definitions import BY_ID


def bind_incidents(engine):
    def facts(game, identity, action):
        desc, p = BY_ID[identity], game.player
        field = action in {'incident_preserve', 'incident_seal'}
        location, name = (desc.field, desc.field_name) if field else (desc.location, desc.location_name)
        assembly = game.buddhist_state.get('assembly')
        reason = None
        if not p.alive:
            reason = '此生已经结束'
        elif (p.imprisonment or p.ghost_captor or game.active_trial or game.guixu_state.get('player_session')
              or assembly and assembly.get('world') == p.world and assembly.get('location') == p.location_id):
            reason = '请先结束受控状态或专属活动'
        elif not WORLD_SYSTEMS['world_profiles'].get(desc.world, {}).get('enabled', True):
            reason = '当前界面未开放'
        elif p.world != desc.world or p.location_id != location or game.spatial_state.get('current'):
            reason = f'须亲自前往{desc.world_name}·{name}'
        elif p.realm_index < desc.rank or p.sealed_cultivation or p.cultivation_suppression:
            reason = f'须具备未封限的{desc.rank}阶以上修为'
        elif game.pending_event:
            reason = '请先处理当前事件'
        return dict(reason=reason, mp=p.mp, max_mp=max_mp(p),
                    stones=sum(i.quantity for i in p.inventory if i.id == 'spirit_stone'),
                    can_apply=(p.world != 'celestial' or p.immortal_power_converted) and p.technique is not None
                    and can_player_practice_technique(p, p.technique.element))

    def relief(game):
        p = game.player
        before = p.hp
        p.hp = min(max_hp(p), p.hp + max_hp(p) * .20)
        return p.hp - before

    def restore(game):
        p = game.player
        p.hp = min(max_hp(p), p.hp + max_hp(p) * .02)

    return dict(incident_facts=facts, incident_relief=relief, incident_restore=restore)
