"""Small explicit opportunity costs; old progress is retained as a discount."""
from math import ceil

COSTS = (100, 180, 280, 420, 600)


def quote(game, *, asura=False):
    p = game.player
    stage = p.asura_cultivation.get('conversion', 0) if asura else p.immortal_conversion_stage
    complete = stage >= 5 or (not asura and p.immortal_power_converted)
    cost = 0 if complete else COSTS[stage]
    if not asura and not complete:
        from ..content_registry import CONTENT_DOCUMENTS
        progress = game.doctrine_state.get('player', {}).get('conversion_progress', 0)
        cost = max(0, ceil(cost * (1 - min(1, progress / CONTENT_DOCUMENTS['doctrines.json']['conversion_years'][stage]))))
    return dict(cost=cost, opportunity=p.opportunity, can_convert=not complete and p.opportunity >= cost and not p.sealed_cultivation and not p.cultivation_suppression,
                stage=stage, complete=complete)


def retire_events(game):
    """Retire only superseded conversion nodes, preserving queued rewards and RNG."""
    changed = False
    event = game.pending_event
    retained = []
    while event:
        following = event.get('_followup_event')
        if str(event.get('id', '')).startswith(('EVT_IMMORTAL_CONVERSION_', 'EVT_ASURA_CONVERSION_')):
            from ..models import HistoryRecord
            game.history.append(HistoryRecord('SYS_CONVERSION_PANEL_ADOPTED', 1, game.player.age,
                '转化入口更新', event['id'], 'retired', '旧转化事件已转入左侧转化面板，已完成阶段保留。',
                {'event_id':event['id']}, ['system']))
            changed = True
        else:
            retained.append(event)
        event = following
    if changed:
        for i,event in enumerate(retained):
            event.pop('_followup_event', None)
            if i+1<len(retained):event['_followup_event']=retained[i+1]
        game.pending_event=retained[0] if retained else None
    if (game.active_trial or {}).get('kind') in {'immortal_conversion', 'asura_conversion'}:
        game.active_trial = None
        changed = True
    return changed
