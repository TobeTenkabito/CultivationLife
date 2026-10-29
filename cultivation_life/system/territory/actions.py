"""Validated local decisions and paid physical construction."""
from ...content_registry import ITEM_CATALOG, WORLD_SYSTEMS
from ...economy_content import material_id
from ..economy import depot
from ..economy.organization_accounts import register, key, procure
from ..economy.ledger import balance, transfer_value
from ..economy.local_market import quote
from ..economy.state import ensure_regional_market, reprice
from .rules import POLICIES, permits, costs
from .state import validate_projection, snapshot, ensure, note
from .geography import contest_chance, change_claim

ACTIONS = {'expand_influence':'投放地方影响力','build_outpost':'新建地方据点','territory_policy':'地方治理政策','territory_spar':'边界论道比试','territory_harass':'边界袭扰'}

def participants(game,entity):
    """Available original members; deployed and researching members cannot duel."""
    from ...npc_custody import is_free
    from ...person_assignments import research_assignment
    from ..war.requirements import deployed_ids
    deployed={n for w in game.wars if w.get('status') in {'active','peace_ready'} for side in ('attacker','defender') for n in deployed_ids(w,side)}
    ranks=[(n.realm_index,n.layer) for n in entity.npcs if is_free(n) and n.world==entity.world and n.id not in deployed and not research_assignment(game,n.id)]
    p=game.player
    if p.alive and p.faction_id==entity.id and p.world==entity.world and 'player' not in deployed and not research_assignment(game,'player') and not any((p.imprisonment,p.ghost_captor,game.active_trial,game.pending_event)):
        ranks.append((p.realm_index,p.layer))
    return ranks

def construction_plan(game,maps,entity,location):
    pricing=costs(entity.world)
    grade=pricing['grade'];fee=pricing['outpost']
    market=game.economy_v2.get('markets',{}).get(f'{entity.world}:{location}',{})
    stores=depot.find(game,entity) if entity.location_id==location else None
    materials=[]; total=fee; available=True
    for role,count in [('ore_structure',6),('ore_conduct',2),('ore_store',2)]:
        identity=material_id(entity.world,grade,role)
        held=min(count,(stores or {}).get('stock',{}).get('item:'+identity,0)); missing=count-held
        product=market.get('commodities',{}).get(identity)
        bill=quote(product,'buy',missing)['total'] if missing and product and product['stock']>=missing else 0
        available &= not missing or bool(product and product['stock']>=missing)
        total+=bill
        materials.append(dict(id=identity,name=ITEM_CATALOG[identity].name,quantity=count,stored=held,purchase=missing,cost=bill))
    funds=int(game.intrigue_state.get('factions',{}).get(f'sect:{entity.id}',{}).get('resources',0))
    return dict(fee=fee,total=total,balance=funds,materials=materials,stock_available=bool(available),can_build=bool(available and funds>=total))

def validate(game,maps,entity,action,location,policy='',target=''):
    if action not in ACTIONS: raise ValueError('未知地方决议')
    validate_projection(game,maps,entity,location,existing=action=='territory_policy',occupies_slot=action!='territory_harass')
    row=snapshot(game,maps,entity.world).get(location,{}).get(entity.id,{})
    if action=='build_outpost' and row.get('outpost'): raise ValueError('当地已有本门据点')
    if action=='territory_policy' and not permits(policy,row.get('value',0)):
        raise ValueError('该政策不适用于当地影响力等级')
    if action in {'territory_spar','territory_harass'}:
        other=game.sects.get(target)
        if not other or other.extinct or other.world!=entity.world or other.id==entity.id:
            raise ValueError('须指定同界的其他宗门')
        rival=snapshot(game,maps,entity.world).get(location,{}).get(target)
        if not rival: raise ValueError('对方在当地没有影响力')
        if other.location_id==location and action=='territory_harass': raise ValueError('袭扰不能削弱对方固定驻地')
        minimum=costs(entity.world)['spar_realm'] if action=='territory_spar' else 0
        if not any(rank>=minimum for rank,_ in participants(game,entity)):
            raise ValueError('本门没有可出面的修士')
        if not any(rank>=minimum for rank,_ in participants(game,other)): raise ValueError('对方没有可应约的修士')
    return row

def apply(game,maps,entity,action,location,rng,policy='',target=''):
    row=validate(game,maps,entity,action,location,policy,target)
    # Political actions do not adopt a full commodity market. Only real local
    # construction needs it; NPC decisions never multiply dormant markets.
    if action=='build_outpost':ensure_regional_market(game,maps,entity.world,location)
    register(game,'sect',entity.id,entity.world)
    source=key('sect',entity.id)
    fee=costs(entity.world)['action']
    if action=='build_outpost':
        plan=construction_plan(game,maps,entity,location)
        if not plan['can_build']: raise ValueError('府库灵石或当地资材不足以新建据点')
        market=game.economy_v2['markets'][f'{entity.world}:{location}']
        stores=depot.find(game,entity) if entity.location_id==location else None
        for item in plan['materials']:
            if item['stored']: stores['stock']['item:'+item['id']]-=item['stored']
            if item['purchase']:
                product=market['commodities'][item['id']]; bill=quote(product,'buy',item['purchase'])
                transfer_value(game,source,f'market:{market["id"]}',bill['total'],'地方据点当地资材采购')
                transfer_value(game,f'market:{market["id"]}',f'operator:{market["id"]}',bill['fee'],'据点资材采购手续费')
                product['stock']-=item['purchase'];product['volume']+=item['purchase']
                from ..economy.market_power import record_trade
                record_trade(game,market,item['id'],source,'buy',item['purchase'])
                market['turnover']+=bill['gross'];market['fees']+=bill['fee'];reprice(game,market,product)
        procure(game,source,entity.world,plan['fee'],'地方据点施工劳务')
    elif action!='territory_policy':
        if balance(game,source)<fee: raise ValueError('府库灵石不足以支付地方行动')
        procure(game,source,entity.world,fee,'地方联络与巡守劳务')
    book=ensure(game,maps,entity.world)
    owned=(book.get(location,{}).get(entity.id,dict(value=0.,outpost=False,policy='')) if action=='territory_harass'
           else book.setdefault(location,{}).setdefault(entity.id,dict(value=0.,outpost=False,policy='')))
    if action in {'territory_policy', 'build_outpost', 'expand_influence'}:
        change_claim(book, location, entity.id, action, policy=policy)
    else:
        def rank(s):return max(participants(game,s),default=(-1,0))
        other=game.sects[target]
        own,enemy=rank(entity),rank(other)
        chance=contest_chance(own,enemy)
        won=rng.random()<chance
        if won:
            if action=='territory_spar': change_claim(book, location, entity.id, action)
            else:
                rival=book[location][target]
                floor=snapshot(game,maps,entity.world)[location][target]['floor']
                rival['value']=max(floor,rival['value']-12)
                if rival['value']<=0: book[location].pop(target)
        if not owned['value'] and not owned['outpost']: book[location].pop(entity.id,None)
        from ...world_state import race_pair
        if action=='territory_harass':
            relation=game.sect_relations.setdefault(race_pair(entity.id,target),dict(status='neutral',affinity=0))
            relation['affinity']=max(-100,relation.get('affinity',0)-8)
        else:
            relation=game.sect_relations.setdefault(race_pair(entity.id,target),dict(status='neutral',affinity=0))
            relation['affinity']=min(100,relation.get('affinity',0)+2)
        note(game,f'{entity.name}在{maps.location(entity.world,location)["name"]}{ACTIONS[action]}：'+('得手' if won else '未能奏效'),entity.world)
        from .state import refresh_bonuses
        refresh_bonuses(game,entity.world)
        return
    if action=='expand_influence':
        from ...world_state import race_pair
        for rival in book.get(location,{}):
            if rival==entity.id:continue
            relation=game.sect_relations.setdefault(race_pair(entity.id,rival),dict(status='neutral',affinity=0))
            relation['affinity']=max(-100,relation.get('affinity',0)-4)
    note(game,f'{entity.name}在{maps.location(entity.world,location)["name"]}通过{ACTIONS[action]}'+(f'：{POLICIES[policy]["name"]}' if policy else ''),entity.world)
    from .state import refresh_bonuses
    refresh_bonuses(game,entity.world)
