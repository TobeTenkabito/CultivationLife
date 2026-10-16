"""Physical battle baskets derived from the authoritative deployed roster."""
import math
from collections import Counter
from ...npc_custody import is_free
from ...person_assignments import research_assignment
from ...content_registry import WORLD_SYSTEMS
from ..economy.basket_rules import REALM_WEIGHTS, purpose_candidates
from ..intrigue.prison_state import is_imprisoned
from ...relationship_records import find_person
from ...spatial_people import instance_of

SHARES = dict(medical=.04, material=.064, energy=.03)


def deployed_ids(war,side):
    roster=war.get('roster',{}).get(side,())
    ratio=war.get('deployment',{}).get(side,1.)
    return roster[:max(1,math.ceil(len(roster)*ratio))]


def deployed_people(game, war, side, *, arrived_only=False):
    """Resolve only original roster IDs, independent of their registry container."""
    managed = bool(war.get('strategic_war_id'))
    if managed and arrived_only and war.get('campaign_phase') != 'engaged':
        return []
    escaped = set(war.get('escaped', {}).get(side, ())) | set(war.get('voisinage_suppressed', ()))
    row = war.get('logistics', {}).get('sides', {}).get(side)
    source_world=(row or {}).get('world',war['world'])
    journeys = {j['person_id']:j for j in war.get('journeys', {}).get(side, [])} if managed else {}
    withdrawn = set(war.get('withdrawn_orgs', []))
    result = []
    for identity in dict.fromkeys(deployed_ids(war, side)):
        if identity in escaped or war.get('roster_owner', {}).get(identity) in withdrawn:
            continue
        npc = find_person(game, identity)
        if (not npc or not is_free(npc) or npc.world != source_world or instance_of(game, identity)
                or research_assignment(game, identity, exclude_war=war.get('id')) or is_imprisoned(game, identity)):
            continue
        if managed:
            journey = journeys.get(identity, {})
            if journey.get('phase') not in ({'stationed'} if arrived_only else {'outbound', 'stationed'}):
                continue
            if arrived_only and npc.location_id != war.get('location_id'):
                continue
        result.append(npc)
    return result


def refresh(game, war, side, *, persist=True, participating_player_side=None):
    people = deployed_people(game, war, side, arrived_only=bool(war.get('strategic_war_id') and war.get('campaign_phase')=='engaged'))
    groups = Counter(n.realm_index for n in people)
    row = war.get('logistics', {}).get('sides', {}).get(side)
    player_present = (participating_player_side == side if war.get('strategic_war_id')
                      else participating_player_side == side or war.get('player_side') == side)
    if player_present and game.player.alive and game.player.world==war['world']:
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
    # Lifespan/breakthrough pills and raw herbs/cores cannot masquerade as
    # wound treatment or ready-to-use repair supplies.
    uses = (dict(medical='healing',material='repair',energy='energy')[category],)
    result = []
    for grade in (rank, rank+1):
        for use in uses:
            result.extend(purpose_candidates(market, f'{use}:{grade}'))
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
