"""Shared institution ledger, policy lookup and history recording.

No court simulation, combat assessment or cultivation presentation belongs here.
"""
from ..content_registry import WORLD_SYSTEMS
from ..models import HistoryRecord


def config():
    return WORLD_SYSTEMS['upper_institutions']


def definition(game):
    return config()['worlds'].get(game.player.world)


def fresh():
    return dict(unit=0, fraction=0.0, joined=False, merit=0, earned=0, rank=0,
                regard=40, support=[45]*5, bloc=0, seat_active=False,
                treasury=config()['initial_treasury'], policy='study', agenda_at=4,
                job=None, obligation=None, completed=0, blessing_until=0,
                log=[], last_appointment=-100, last_proposal=-100)


def account(game, *, create=False):
    return (game.upper_institutions.setdefault(game.player.world, fresh()) if create
            else game.upper_institutions.get(game.player.world, fresh()))


def policy(game, state=None):
    state = state if state is not None else account(game)
    return next(p for p in definition(game)['policies'] if p['id'] == state['policy'])


def record(game, state, text):
    state['log'].append(dict(unit=state['unit'], text=text))
    state['log'] = state['log'][-20:]
    game.history.append(HistoryRecord('SYS_UPPER_INSTITUTION', 1, game.player.age,
        definition(game)['name'], 'governance', 'completed', text, {}, ['institution', game.player.world]))
