"""Read-only DLC gates and original personal entitlement bookkeeping."""
from ..content_registry import WORLD_SYSTEMS


def config():
    return WORLD_SYSTEMS.get('yaochi_westward', {})


def enabled():
    return bool(config().get('enabled'))


def record(game):
    return game.yaochi_state.get('westward', {})


def project(game):
    return record(game).get('project')


def merit_balance(game):
    return int(game.heavenly_court.get('merit_account', {}).get('available', 0))


def adopt_merit(game):
    if 'merit_account' not in game.heavenly_court:
        game.heavenly_court['merit_account'] = dict(
            available=max(0, int(game.heavenly_court.get('player_merit', 0))),
            adopted_age=game.player.age)


def credit_merit(game, amount):
    """After explicit adoption, all original awards update the same balance.

    Disabling the DLC does not erase rights or create a second adoption grant.
    Negative original sanctions affect available rights, never create a debt.
    """
    account = game.heavenly_court.get('merit_account')
    if account is not None:
        account['available'] = max(0, int(account['available']) + int(amount))


def training_lock(game, kind=None):
    row = project(game)
    return bool(row and (kind is None or row['kind'] == kind))
