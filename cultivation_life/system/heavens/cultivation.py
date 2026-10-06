"""Merge a bounded local application into a single existing cultivation grant."""
from .state import phase, contacts
from . import incidents


def activity_gain(deps, game, base_gain, action):
    runtime = game.heavens_state.get('runtime')
    echo = next((row for row in contacts(runtime) if row['application']), None)
    application = echo and echo['application']
    extra = 0.0
    if application and action == 'cultivate':
        _cycle, offset, cutoff = phase(runtime, echo)
        facts = deps.read_actor_facts(game, echo['id'])
        if facts['can_apply'] and offset < cutoff:
            fraction, cap = (.15, .03) if echo['exchanged'] else (.10, .02)
            extra = min(max(0, base_gain) * fraction, max(0, echo['reward_base'] * cap - echo['reward_claimed']))
        # Each executed cultivation year consumes its saved allowance, even if
        # the old path has no positive gain; changing worlds never replenishes it.
        application['remaining'] -= 1
        if application['remaining'] <= 0:
            echo['application'] = None
        game.heavens_state['revision'] += 1
    local_extra, local_record = incidents.activity_extra(deps, game, base_gain, action) if deps.incident_facts else (0.0, None)
    actual = deps.grant_progress(game.player, base_gain + extra + local_extra)
    if local_record:
        local_record['claimed'] += min(local_extra, max(0, actual - max(0, base_gain) - extra))
    if extra:
        echo['reward_claimed'] += min(extra, max(0, actual - max(0, base_gain)))
    return base_gain + extra + local_extra
