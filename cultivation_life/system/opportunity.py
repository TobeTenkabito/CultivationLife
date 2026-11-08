"""One opportunity award, efficiency, upper cap and trace/qi settlement."""
from ..rules import opportunity_multiplier, opportunity_required, grant_qi_experience
from .cultivation_policy import ordinary_upper, opportunity_unbounded
from .immortal_cultivation import grant_trace_chance


def grant(player, amount, efficiencies, *, apply_efficiency=True, trace_multiplier=1.):
    if amount > 0 and player.nascent_state.get('stagnant'):
        return 0.
    if amount > 0 and apply_efficiency:
        amount *= opportunity_multiplier(player, allow_untrained=True)
    before = player.opportunity
    player.opportunity = max(0., before + float(amount))
    if ordinary_upper(player) and not opportunity_unbounded(player):
        player.opportunity = min(player.opportunity, opportunity_required(player))
    actual = player.opportunity - before
    if actual > 0:
        grant_trace_chance(player, actual, chance_multiplier=trace_multiplier)
        grant_qi_experience(player, actual, efficiencies)
    return actual
