"""Physical battle baskets derived from the authoritative deployed roster."""
import math
from collections import Counter
from ...npc_custody import is_free
from ...person_assignments import research_assignment
from ...content_registry import WORLD_SYSTEMS
from ..economy.basket_rules import REALM_WEIGHTS, index, candidates

SHARES = dict(medical=.04, material=.064, energy=.03)


def deployed_ids(war,side):
    roster=war.get('roster',{}).get(side,())
    ratio=war.get('deployment',{}).get(side,1.)
    return roster[:max(1,math.ceil(len(roster)*ratio))]


def refresh(game, war, side, *, persist=True):
    ids = set(deployed_ids(war,side))
    escaped = set(war.get('escaped', {}).get(side, ())) | set(war.get('voisinage_suppressed', ()))
    pool = [*game.sects.values(), *([game.family] if game.family else [])]
    people = {n.id:n for e in pool for n in e.npcs if n.id in ids}
    people.update({k:n for k,n in game.world_npcs.items() if k in ids})
    row = war.get('logistics', {}).get('sides', {}).get(side)
    source_world=(row or {}).get('world',war['world'])
    groups = Counter(n.realm_index for k,n in people.items() if k not in escaped and is_free(n) and n.world==source_world
                     and not research_assignment(game, k))
    if game.player.alive and game.player.world==war['world'] and war.get('player_side')==side:
        groups[game.player.realm_index]+=1
    if row is not None and persist:
        row['realm_groups'] = {str(k):n for k,n in groups.items()}
    return groups


def groups(game, war, side):
    row = war.get('logistics', {}).get('sides', {}).get(side, {})
    if 'realm_groups' in row:
        return {int(k):n for k,n in row['realm_groups'].items()}
    return refresh(game, war, side, persist=False)


def physical(game, war, side):
    result = {}
    intensity = 1.
    for rank, n in groups(game, war, side).items():
        for category, rate in SHARES.items():
            group=f'{category}:{max(1,rank)}'
            result[group] = result.get(group,0)+n*REALM_WEIGHTS[rank]*rate*intensity
    return result


def suitable(market, group):
    category, rank = group.split(':'); rank = int(rank)
    # Equivalent uses, same grade or one grade higher; cheaper low-grade goods
    # never cover elite needs. Pills supply the medical basket where classified
    # as cultivation drugs; repairs consume materials at a low replacement rate.
    uses = (category, 'training') if category == 'medical' else (category,)
    result = []
    for grade in (rank, rank+1):
        for use in uses:
            result.extend(candidates(market, f'{use}:{grade}'))
    return tuple(dict.fromkeys(result))[:4]


def energy(game, war, side):
    tier = WORLD_SYSTEMS['world_profiles'][war['world']]['tier']
    return max(40*tier, math.ceil(sum(n*REALM_WEIGHTS[r] for r,n in groups(game,war,side).items())*12*tier))


def reference_need(game, war, side, market):
    value = energy(game,war,side)
    for group, quantity in physical(game,war,side).items():
        goods = suitable(market, group)
        if goods:
            value += quantity*min(market['commodities'][k]['reference'] for k in goods)
        else:
            value += quantity*40*(int(group.split(':')[1])+1)**2
    return max(1, math.ceil(value))


def turns(game, war, side, market, row, cash):
    # Price-independent physical sufficiency. A stock cannot be reused across
    # baskets: candidate categories are disjoint, medicine may use training.
    needs=physical(game,war,side)
    low,high=0.,min(10000.,cash/max(1,energy(game,war,side)))
    # A bounded feasibility search allocates each piece once, including a
    # higher-grade substitute which could fit two adjacent realm buckets.
    for _ in range(24):
        target=(low+high)/2
        available=dict(row['items']);valid=True
        for group,quantity in sorted(needs.items(),key=lambda x:-int(x[0].split(':')[1])):
            remaining=max(0,quantity*target+row.get('demand_credit',{}).get(group,0))
            for item in suitable(market,group):
                take=min(remaining,available.get(item,0))
                available[item]=available.get(item,0)-take
                remaining-=take
            if remaining>1e-8:valid=False;break
        if valid:low=target
        else:high=target
    return low
