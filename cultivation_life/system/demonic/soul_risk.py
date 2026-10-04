"""One risk contract for pending soul occupancy, display and yearly settlement."""
import math


def refinement_risk(player, rules):
    pending = [s for s in player.foreign_souls if not s.get('refined')]
    capacity = max(0, player.realm_index - 1) if player.path == 'demonic' else 0
    excess = max(0, len(pending) - capacity)
    base = max(0., float(rules.get('soul_backlash_base', .025)))
    # Bound the exponent before evaluation; malformed/very large collections
    # must not overflow. At six excess souls the default reaches the 95% cap.
    chance = min(.95, base * math.expm1(min(excess, 32) * math.log(2))) if excess else 0.
    return dict(safe_capacity=capacity, pending=len(pending), excess=excess,
                annual_chance=round(chance, 8),
                burden=sum(max(0., float(s.get('strength', 1))) for s in pending))
