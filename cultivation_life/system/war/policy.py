"""System wars cannot cross world tiers; explicit player action is exempt."""
from ...content_registry import WORLD_SYSTEMS, RACE_DEFINITIONS


def strategic_conflicts(game, first, second):
    """Original opposite commitments remain binding through total settlement."""
    result=[]
    for row in game.strategic_war_state.get('wars',[]):
        if row['status']=='ended':continue
        sides={c['org']['id']:c['side'] for c in row['commitments']}
        if first in sides and second in sides and sides[first]!=sides[second]:
            result.append(row)
    return result


def system_war_allowed(game, kind, attacker, defender):
    def tiers(identity):
        if kind == 'race':
            worlds = RACE_DEFINITIONS.get(identity, {}).get('worlds', [])
        else:
            entity = game.sects.get(identity)
            if game.family and game.family.id == identity:
                entity = game.family
            worlds = [entity.world] if entity else []
        return {WORLD_SYSTEMS['world_profiles'][world]['tier'] for world in worlds
                if world in WORLD_SYSTEMS['world_profiles'] and WORLD_SYSTEMS['world_profiles'][world]['tier'] > 0}
    return bool(tiers(attacker) & tiers(defender))
