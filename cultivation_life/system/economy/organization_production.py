"""One realm histogram and a bounded local sales portfolio per organization."""
from collections import Counter
from ...npc_custody import is_free
from ...content_registry import WORLD_SYSTEMS
from ..faction_geography import faction_site
from .state import ensure_regional_market
from .industry import supplier_delivery


def workforce(entity):
    # A single tally, not a business simulation per NPC. Only 13 realm buckets
    # enter the economic calculation; births/deaths are already authoritative.
    return Counter(n.realm_index for n in entity.npcs if is_free(n) and n.world == entity.world)


def produce(game, maps, entity, row, *, years=1, extra=False):
    world, location = entity.world, faction_site(entity)['id']
    ensure_regional_market(game, maps, world, location)
    market = game.economy_v2['markets'][f'{world}:{location}']
    from ..war.requirements import deployed_ids
    from ...person_assignments import research_assignment
    deployed={(war.get('logistics',{}).get('sides',{}).get(side,{}).get('world',war['world']),identity)
        for war in game.wars if war.get('status') in {'active','peace_ready'}
        for side in ('attacker','defender') for identity in deployed_ids(war,side)
        if identity not in war.get('escaped',{}).get(side,()) and identity not in war.get('voisinage_suppressed',())}
    groups=Counter();working=Counter()
    for npc in entity.npcs:
        if not is_free(npc) or npc.world != entity.world:continue
        groups[npc.realm_index]+=1
        if (npc.world,npc.id) not in deployed and not research_assignment(game,npc.id):
            working[npc.realm_index]+=1
    tier = WORLD_SYSTEMS['world_profiles'][world]['tier']
    row['expected_upkeep'] = sum(count*(25*tier+rank**2*8) for rank,count in groups.items())
    row['workforce'] = {str(k):v for k,v in sorted(groups.items())}
    row['workforce_year'] = game.player.age
    capacity = sum(count * (60 + 60 * rank ** 3) for rank,count in working.items()) * 5 ** (tier-1)
    row['labor_capacity'] = capacity
    if not capacity:
        return 0
    capacity *= .25 if extra else 1
    # Ordinary production and fixed estates draw on the same workforce.
    estate_count = sum(e['owner_kind'] == row['kind'] and e['owner_id'] == entity.id
        and e['world'] == world and e['enabled'] for e in game.economy_v2.get('estates', {}).values())
    capacity /= 1 + estate_count
    capacity *= (1 + row.get('industry_level', 0) * .25) * row.get('industry_utilization', 1)
    from .basket_rules import index, candidates, raw_candidates
    from .basket_production import produce as workshop_produce
    credit = min(10**12, row.get('production_credit', 0) + capacity * years)
    earned = 0
    source = f'organization:{row["kind"]}:{entity.id}'
    index(market)
    goods = []
    for rank in range(max(working)+1,0,-1):
        goods.extend(raw_candidates(market,rank,limit=1))
    for category in ('material', 'training', 'medical', 'arms', 'energy', 'general'):
        for rank in range(max(working)+1, 0, -1):
            goods.extend(candidates(market, f'{category}:{rank}', limit=1))
    completed = 0
    from .production_allocation import quota, record
    for item in dict.fromkeys(goods):
        if row['produced'] >= 1000000:
            break
        product = market['commodities'][item]
        if product['reference'] > credit:
            continue
        room=max(0,int(product['target']*1.5-product['stock']))
        allowance=quota(game,market,source,item,room)
        quantity, net = workshop_produce(game, market, source, item,
            min(int(credit/product['reference']),allowance), labor_credit=credit)
        if not quantity:
            continue
        supplier_delivery(market, source, quantity, game=game, item=item)
        record(game,market,source,item,quantity)
        earned += net; credit -= quantity*product['reference']
        row['produced'] += quantity; row['commodity'] = item
        completed += 1
        if completed >= 4:
            break
    row['production_credit'] = max(0,credit)
    return earned
