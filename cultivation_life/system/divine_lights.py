"""Five body-born lights. Only the adapter reads cultivation/content records."""
from ..content_registry import CONTENT_DOCUMENTS

IDS = ('kun', 'zhen', 'kan', 'li', 'qian')
NAMES = ('坤元缃光', '震合缥光', '坎道玄光', '离上朱光', '乾古素光')


def definitions():
    return CONTENT_DOCUMENTS['doctrines.json']['cultivation']['divine_lights']


def body_record(owner, *, player=False):
    from .combat.actor_state import read
    if player:
        from .possession_system import is_possessed
        from .wuyun import enabled_for
        if not is_possessed(owner):
            if enabled_for(owner):return {}, True
            record=owner.immortal_body
            return record, True
        owner = owner.ghost_host_body
    from .wuyun import enabled_for
    if enabled_for(owner):return {}, False
    level = max(0, min(50, int(read(owner, 'immortal_body_level', 0) or 0)))
    # NPC advancement follows its independent body coordinate, never its realm.
    return dict(level=level, divine_lights={key:min(10, level // 5) for key in IDS}), False


def profile(owner, *, player=False):
    record, _ = body_record(owner, player=player)
    level = max(0, min(50, int(record.get('level', 0))))
    trained = record.get('divine_lights', {})
    levels, effects = {}, {}
    for row in definitions():
        if level < row['unlock_level']:
            continue
        key = row['id']; rank = trained.get(key, 0)
        if type(rank) is not int or not 0 <= rank <= 10:
            raise ValueError('神光修炼等级须为0至10')
        levels[key] = rank
        effects[key] = row['base'] + row['growth'] * rank
        if key == 'kun':effects['kun_resist'] = row['resist_growth'] * rank
        if key == 'zhen':effects['zhen_heal'] = row['heal_growth'] * rank
    return effects, levels


def recipe(row, rank):
    return {key:count * (rank + 1) for key,count in row['recipe'].items()}


def visual_lights(owner, *, player=False):
    """Bounded read-only projection; unlocking, not training rank, grants a light."""
    effects, _ = profile(owner, player=player)
    return [key for key in IDS if effects.get(key)]
