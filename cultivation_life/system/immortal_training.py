"""Shared paid training outcomes. Callers own eligibility, costs and persistence."""
from ..rules import max_hp, max_mp
from .immortal_cultivation import body_probability


def settle_body(player, rng, probability):
    level = player.immortal_body.get('level', 0)
    hp_ratio, mp_ratio = player.hp / max_hp(player), player.mp / max_mp(player)
    if rng.random() >= probability:
        player.immortal_body['failures'] = player.immortal_body.get('failures', 0) + 1
        return f'淬体未成，本次药材已消耗；下次基础成功率 {body_probability(player):.0%}。'
    player.immortal_body.update(level=level + 1, failures=0)
    from .ghost_system import grant_intrinsic_progression_if_new_highwater
    grant_intrinsic_progression_if_new_highwater(player)
    player.hp = max_hp(player) * min(1, hp_ratio)
    player.mp = max_mp(player) * min(1, mp_ratio)
    summary = f'真仙之躯修至第 {level + 1} 层（成功率 {probability:.0%}）。'
    from .ghost_body import enabled_for as ghost_enabled
    if ghost_enabled(player):
        from ..ghost_body_content import NAMES
        if (level + 1) % 10 == 0:
            summary += f' {NAMES[(level + 1)//10-1]}已解锁，可从鬼躯入口独立修炼。'
    else:
        from .divine_lights import definitions
        unlocked = next((r for r in definitions() if r['unlock_level'] == level + 1), None)
        if unlocked:
            summary += f" {unlocked['name']}已解锁，可独立修炼。"
    return summary


def settle_light(player, key, expected_level):
    from .divine_lights import profile
    _, levels = profile(player, player=True)
    if key not in levels or levels[key] != expected_level or expected_level >= 10:
        raise ValueError('神光资格或等级已变化，请刷新后重新办理')
    player.immortal_body.setdefault('divine_lights', {})[key] = expected_level + 1
