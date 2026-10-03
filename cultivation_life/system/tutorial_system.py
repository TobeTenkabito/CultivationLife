"""Opt-in reading progress and a one-time, deterministic apprenticeship event.

No annual hooks, random rolls, simulation shortcuts or replacement of pending events.
The mentor enters the normal persistent NPC roster and relationship lifecycle.
"""
from ..runtime import now_iso

from .tutorial_mentorship import (
    MENTOR_STEP as MENTOR_STEP, blocked_reason as blocked_reason,
    mentor_action as mentor_action, mentor_status,
)

CHAPTER_COUNT = 10

def public_tutorial(game):
    from .tutorial_walkthrough import public_guide
    info = mentor_status(game)
    return dict(guide=public_guide(game), **info)


def perform(engine, game_id, action, step=None, target_id=None):
    game = engine._load(game_id)
    p, state = game.player, game.player.tutorial_state
    if action.startswith('guide_'):
        from .tutorial_walkthrough import perform_guide
        return perform_guide(engine, game, action, step, target_id)
    if action in {'enable', 'disable'}:
        state['enabled'] = action == 'enable'
    elif action == 'navigate':
        if not state.get('enabled'):
            raise ValueError('请先开启新手教程')
        if type(step) is not int or not 0 <= step < CHAPTER_COUNT:
            raise ValueError('未知教程章节')
        state['step'] = step
    elif action == 'finish':
        state.update(enabled=False, completed=True)
    elif action in {'offer_mentor', 'accept_mentor', 'decline_mentor'}:
        mentor_action(engine, game, action)
    else:
        raise ValueError('未知教程操作')
    game.updated_at = now_iso()
    engine.store.save(game)
    return engine.present(game)
