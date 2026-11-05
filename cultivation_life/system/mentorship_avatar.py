"""The one held original actor; ordinary training, resources and movement own its state."""
from . import mentorship as m
from ..soul_rules import wandering
from ..content_registry import WORLD_SYSTEMS


def avatar_person(game):
    entry = game.mentorship_state.get('avatar', {})
    npc = m.person(game, entry.get('id', ''))
    return npc if npc and npc.alive and npc.roster_state == 'held' and (npc.custody or {}).get('kind') == 'external_avatar' and npc.custody.get('holder_id') == game.id else None


def avatar_reason(game, *, command=False):
    npc = avatar_person(game)
    p = game.player
    if not npc: return '化身已陨落或控制关系已结束'
    if npc.lifespan is not None and npc.age >= npc.lifespan: return '化身寿元已尽'
    if p.imprisonment or p.ghost_captor: return '拘禁期间不能驱动化身'
    if not p.alive or wandering(npc) or wandering(p): return '神游或肉身毁坏时化身不能行动'
    if p.sealed_cultivation or p.cultivation_suppression: return '封印或压制期间不能驱动化身'
    from ..npc_development_content import TIERS
    tier = TIERS.get(p.world, 0)
    if not tier or npc.world != p.world: return '当前界面无法承载化身'
    if npc.realm_index > {1:5, 2:8, 3:12}[tier]: return '化身真实修为超出当前界面承载'
    if game.guixu_state.get('player_session') or game.trial_site_state.get('active'): return '亲自副本中不能调用外部化身'
    if game.heavens_state.get('runtime'):
        from .heavens.state import active_task
        if active_task(game.heavens_state['runtime']): return '诸天亲自任务中不能调用化身'
    if command and (game.pending_event or game.active_trial or game.map_journey or p.imprisonment or p.ghost_captor):
        return '请先结束事件、行旅或拘禁'
    return ''


def avatar_unit(game, power):
    if avatar_reason(game) or not game.mentorship_state.get('avatar', {}).get('enabled'): return None
    from .combat_system import BattleUnit
    npc = avatar_person(game)
    factor = 1.2 if game.mentorship_state['avatar']['consented'] else 1.0
    return BattleUnit(npc.id, '身外化身·' + npc.name, 'external_avatar', power(npc) * factor, npc.realm_index, npc.path)


def tick_avatar(game, rng=None, tribulation=None):
    from ..regional_context import historical, region
    if historical(game) or region(game) and region(game) != game.player.world: return
    npc = avatar_person(game)
    if not npc: return
    state = game.mentorship_state['avatar']
    elapsed = max(0, game.player.age - state['last_age'])
    state['last_age'] = max(state['last_age'], game.player.age)
    npc.age += elapsed
    from .combat.npc_lifecycle import settle
    settle(npc, game.player.age, WORLD_SYSTEMS.get('transcendent_combat', {}))
    if npc.lifespan is not None and npc.age >= npc.lifespan:
        from ..npc_custody import kill_person
        kill_person(game, npc.id, '身外化身寿元耗尽')
    if npc.alive and elapsed:
        if rng and npc.wounds > 0 and rng.random() < .35:
            npc.wounds -= 1
        if tribulation and rng:
            tribulation(game, npc, rng, '身外化身·')


