"""Reconcile saved event structure without rerunning ambient trigger eligibility."""
from __future__ import annotations

import copy
from ...content_registry import FACTION_SYSTEMS
from ...models import GameState, HistoryRecord
from .dependencies import EventsPreparationDependencies


def prepare_events(deps: EventsPreparationDependencies, game: GameState) -> bool:
    changed = False
    head = game.pending_event
    retained = []
    while head:
        following = head.get('_followup_event')
        definition = deps.events_by_id.get(head.get('id'))
        if head.get('id') == 'SYS_POST_BATTLE_POSSESSION':
            retained.append(head)
        elif definition is None:
            # A removed content pack must not take a queued earned reward with it.
            game.history.append(HistoryRecord(
                'SYS_CONTENT_MIGRATION', 1, game.player.age, '事件校正', None, 'unavailable',
                f"事件“{head.get('title') or head.get('id')}”的内容定义已不可用，已保留其后续事件。",
                {'event_id': head.get('id')}, ['system', 'migration'],
            ))
            if head is game.pending_event:
                game.active_trial = None
            changed = True
        else:
            tags = definition.get('tags', [])
            if 'court_task' in tags and head.get('runtime') and not head['runtime'].get('court_authorized'):
                head['runtime']['court_authorized'] = True
                changed = True
            originals = list(definition['choices'])
            if game.player.realm_index >= 4 and 'faction' in tags and 'duty' in tags and 'war' not in tags:
                originals += [
                    {'id': '__delegate_faction_task', 'text': f"派遣门下弟子代为完成（宗门贡献 -{int(FACTION_SYSTEMS['shareholder_delegate_cost'])}）"},
                    {'id': '__decline_faction_task', 'text': f"以议事席身份拒绝任务（宗门贡献 -{int(FACTION_SYSTEMS['shareholder_decline_cost'])}）"},
                ]
            saved = {row['id']: row for row in head.get('choices', []) if isinstance(row, dict) and row.get('id')}
            choices = []
            for original in originals:
                row = copy.deepcopy(saved.get(original['id'], original))
                row.pop('effects', None)
                row.pop('conditions', None)
                if original.get('conditions') or original['id'] not in saved:
                    row['enabled'] = deps._condition(original.get('conditions', {}), game)
                row.setdefault('enabled', True)
                row.setdefault('text', original['text'])
                if original.get('disabled_reason'):
                    row['disabled_reason'] = original['disabled_reason']
                choices.append(row)
            if choices != head.get('choices'):
                head['choices'] = choices
                changed = True
            # Trigger eligibility governs selection, not completion of an opened
            # encounter. A realm change must not erase an authorized event.
            retained.append(head)
        head = following
    if changed:
        for index, event in enumerate(retained):
            event.pop('_followup_event', None)
            if index + 1 < len(retained):
                event['_followup_event'] = retained[index + 1]
        game.pending_event = retained[0] if retained else None
    if not game.pending_event and game.active_trial:
        game.active_trial = None
        game.history.append(HistoryRecord(
            'SYS_TRIAL_MIGRATION', 1, game.player.age, '劫数校正', None, 'migrated',
            '失去对应事件的突破或雷劫状态已经清理，可以继续行动。', {},
            ['system', 'migration', 'tribulation'],
        ))
        changed = True
    return changed
