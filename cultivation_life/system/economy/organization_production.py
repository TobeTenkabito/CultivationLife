"""One realm histogram and a bounded local sales portfolio per organization."""
from collections import Counter
from ...npc_custody import is_free
from ...content_registry import WORLD_SYSTEMS
from ..faction_geography import faction_site
from .state import ensure_regional_market
from .industry import supplier_delivery
from ..intrigue.prison_state import is_imprisoned


def workforce(entity):
    # A single tally, not a business simulation per NPC. Only 13 realm buckets
    # enter the economic calculation; births/deaths are already authoritative.
    return Counter(n.realm_index for n in entity.npcs if is_free(n) and n.world == entity.world)


def annual_upkeep(groups, tier):
    """Aggregate member care follows the same realm/world scale as their work."""
    return sum(count * (25*tier + rank**2*8 + rank**3*tier)
               for rank, count in groups.items())


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
    positions=game.intrigue_state.get('factions',{}).get(f'sect:{entity.id}',{}).get('positions',{}) if row['kind']=='sect' else {}
    elder_ids={positions.get(role) for role in ('foreign_elder','war_elder')}
    effective_elder=False
    for npc in entity.npcs:
        if not is_free(npc) or npc.world != entity.world:continue
        groups[npc.realm_index]+=1
        if (not is_imprisoned(game,npc.id) and (npc.world,npc.id) not in deployed
                and not research_assignment(game,npc.id)):
            working[npc.realm_index]+=1
            effective_elder=effective_elder or (npc.id in elder_ids and npc.realm_index>=3)
    p=game.player
    if 'player' in elder_ids and p.alive and p.world==world and not p.imprisonment and not p.ghost_captor and not game.active_trial:
        effective_elder=effective_elder or (p.realm_index>=3 and (world,'player') not in deployed and not research_assignment(game,'player'))
    row['territory_elder_factor']=.7 if effective_elder else 1.
    tier = WORLD_SYSTEMS['world_profiles'][world]['tier']
    row['expected_upkeep'] = annual_upkeep(groups, tier)
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
    # Unpaid expansion maintenance suspends its bonus, not the ordinary labor
    # that can earn the money needed to recover from a temporary cash shortage.
    capacity *= 1 + row.get('industry_level', 0) * .25 * row.get('industry_utilization', 1)
    from ..territory.rules import enabled
    capacity *= 1 + (row.get('territory_production_bonus',0.) if enabled() else 0.)
    from .basket_rules import index, purpose_candidates, raw_candidates
    from .basket_production import produce as workshop_produce
    credit = min(10**12, row.get('production_credit', 0) + capacity * years)
    earned = 0
    source = f'organization:{row["kind"]}:{entity.id}'
    index(market)
    goods = []
    rotation=game.player.age//20
    for rank in range(max(working)+1,0,-1):
        goods.extend(raw_candidates(market,rank,limit=2,rotation=rotation))
    for category in ('repair', 'breakthrough', 'cultivation', 'longevity', 'healing', 'artifact', 'energy', 'general'):
        for rank in range(max(working)+1, 0, -1):
            goods.extend(purpose_candidates(market, f'{category}:{rank}', limit=1,rotation=rotation))
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
        before_turnover = market['turnover']
        quantity, net = workshop_produce(game, market, source, item,
            min(int(credit/product['reference']),allowance), labor_credit=credit)
        if not quantity:
            continue
        gross = market['turnover'] - before_turnover
        if extra:
            from .organization_accounts import book_turnover
            book_turnover(game, row, gross)
        else:
            row['turnover'] = row.get('turnover', 0) + gross
        supplier_delivery(market, source, quantity, game=game, item=item)
        record(game,market,source,item,quantity)
        earned += net; credit -= quantity*product['reference']
        row['produced'] += quantity; row['commodity'] = item
        completed += 1
        if completed >= 4:
            break
    row['production_credit'] = max(0,credit)
    return earned
