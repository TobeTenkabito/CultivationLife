"""Base-game soul rules. Pure formulas; never move an actor or advance time."""
import math

SECRETS = {
    'second_nascent': ('第二元婴', 4, 12000),
    'path_dao': ('返璞归真', 1, 800),
    'path_demonic': ('化魔诀', 1, 800),
    'path_ghost': ('阴魂续命诀', 1, 800),
    'path_buddhist': ('转轮入禅', 1, 800),
    'path_confucian': ('养浩归儒', 1, 800),
}
PATH_QI = {'dao': 'spirit', 'demonic': 'demon', 'ghost': 'yin',
            'buddhist': 'spirit', 'confucian': 'spirit'}


def can_capture(player):
    return player.path == 'demonic' or wandering(player) or 'second_nascent' in player.nascent_state.get('known', [])


def wandering(actor):
    state = actor.get('spirit_state', {}) if isinstance(actor, dict) else actor.spirit_state
    return state.get('mode') == 'wandering'


def body_cap(player):
    return 100. + 20 * player.body_training


def require_body_training(player):
    if wandering(player) and not player.spirit_state.get('body_intact'):
        raise ValueError('肉身已毁，须先取得肉身才能炼体')


def soul_cap(player):
    return 100. + 25 * player.divine_sense_rank


def assimilation_cost(rank):
    return 10 + 5 * max(0, rank - 3)


def rebellion_chance(control):
    """No rebellion above the rescue threshold; grows linearly to 35% at zero."""
    return max(0., min(.35, (50. - control) * .007))


def lower_minor(rank, layer, realms):
    if rank >= 2 and layer > 3:
        return rank, layer - 3
    if rank >= 2:
        return rank - 1, realms[rank-1].layers - 3 + layer if rank > 2 else realms[1].layers
    if layer > 1:
        return rank, layer - 1
    return max(0, rank-1), realms[max(0, rank-1)].layers


def validate_spirit(value):
    if not isinstance(value, dict) or set(value) - {'mode', 'body_intact', 'entered', 'deadline', 'address'}:
        raise ValueError('神游状态结构无效')
    if not value:
        return {}
    if value.get('mode') != 'wandering' or type(value.get('body_intact')) is not bool:
        raise ValueError('神游状态无效')
    for key in ('entered', 'deadline'):
        n = value.get(key)
        if isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) or n < 0:
            raise ValueError('神游时限无效')
    if value['deadline'] < value['entered'] or not isinstance(value.get('address'), dict):
        raise ValueError('神游归体地址无效')
    return value


def validate_energy(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError('体魄／神魂能量无效')
    return float(value)
