"""Discover and execute heavens operations through the isolated engine boundary."""
import copy

from .capabilities import BY_OPERATION
from .registry import Argument, Command


def inspect(ctx, target_id=None):
    """Public projection plus explicit debug-only authoritative state; no preparation."""
    view = ctx.services.preview(ctx.session, 'heavens-view',
                                {'view': 'known', 'target_id': target_id})
    return {'view': view, 'saved_state': copy.deepcopy(ctx.document.get('heavens_state', {})),
            'session_revision': ctx.session.get('revision', 0)}


def act(ctx, action, options, target_id=None):
    """Quote afresh and allocate the formal sequence inside one debug transaction."""
    payload = {'action': action, 'options': options, 'target_id': target_id}
    quote = ctx.services.preview(ctx.session, 'heavens-preview', payload)
    view = ctx.services.preview(ctx.session, 'heavens-view', {'view': 'known'})
    result = ctx.services.simulate(ctx.session, 'heavens-command', {
        **payload, 'command_seq': view['next_command_seq'], 'expected_revision': quote['revision']})
    return {**result, 'quote': quote,
            'heavens': ctx.services.preview(ctx.session, 'heavens-view',
                                            {'view': 'known', 'target_id': target_id})}


def register(registry):
    registry.register(Command('heavens inspect', 'preview',
        'Read the current heavens projection and authoritative saved state without advancing time or RNG. '
        'Includes incidents, contacts, tasks, frontier and campaign; requires an isolated debug session.',
        inspect, (Argument('target_id', required=False),)))
    registry.register(Command('heavens act', 'simulation',
        'Quote then execute one ordinary heavens action in the isolated copy. '
        'Allocates the current sequence/revision; eligibility, costs and event pauses still apply. '
        'Use structured request_key and expected_revision for retry-safe agent writes.',
        act, BY_OPERATION['heavens-preview'].arguments))
