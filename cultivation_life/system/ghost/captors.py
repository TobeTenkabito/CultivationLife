"""Reconcile personal soul custody against the original registered person."""
from ...relationship_records import find_person
from ...models import HistoryRecord


def release_dead_captor(game):
    captor = game.player.ghost_captor
    if not captor:
        return False
    identity = str(captor.get('npc_id') or captor.get('id') or '')
    owner = find_person(game, identity, include_inactive=True) if identity else None
    # Generated opponents may legitimately have only a capture snapshot.
    if owner is None or owner.alive:
        return False
    game.player.ghost_captor = None
    game.history.append(HistoryRecord(
        'SYS_GHOST_CAPTOR_DIED', 1, game.player.age, '魂印消散', None, 'released',
        f'{owner.name}已经陨落，拘魂禁制失去主人，你重获自由。',
        {'captor_id': owner.id}, ['system', 'ghost', 'controlled'],
    ))
    return True
