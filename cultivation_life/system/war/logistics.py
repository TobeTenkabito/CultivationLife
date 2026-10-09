"""Real treasury mobilisation, finite battlefield funds and local war spending."""
from math import ceil
from ...content_registry import WORLD_SYSTEMS, ITEM_CATALOG, CONTENT_DOCUMENTS
from ..faction_geography import faction_site, war_site
from ..economy import depot
from ..economy.organizations import register
from ..economy.ledger import account, balance, transfer_value
from ..economy.state import ensure_state, ensure_regional_market, reprice
from ..economy.local_market import quote

SIDES = ('attacker', 'defender')
from . import supply
from . import requirements


def entities(game, war, side):
    ids = {r['id'] for r in war.get('coalitions', {}).get(side, [])} or {war[f'{side}_id']}
    pool = [*game.sects.values(), *([game.family] if game.family else [])]
    return [e for e in pool if not e.extinct and e.kind != 'institution' and (
        e.id in ids if war['kind']=='sect' else e.world==war['world'] and e.allegiance_race in ids)]


def cash(game, entity):
    return max(0, int(game.intrigue_state.get('factions', {}).get(f'{depot.owner_kind(game,entity)}:{entity.id}', {}).get('resources',0)))


def weight(entity):
    from ..economy.organization_production import workforce
    return max(1, sum(n*(rank+1)**4 for rank,n in workforce(entity).items()))


def need(game, war, side):
    row = war.get('logistics', {}).get('sides', {}).get(side, {})
    market = game.economy_v2.get('markets', {}).get(f"{row.get('world',war['world'])}:{row.get('location',war.get('location_id'))}")
    if market:
        value=min(10**9, requirements.reference_need(game,war,side,market))
        return value
    return max(100, requirements.energy(game,war,side))


def ready_to_attack(game, kind, identity, world):
    war = dict(kind=kind, world=world, attacker_id=identity)
    from ...npc_custody import is_free
    from ...person_assignments import research_assignment
    from ..economy.state import commodity_catalog
    pool=entities(game,war,'attacker')
    people=sorted((n for e in pool for n in e.npcs if is_free(n) and n.world==world and not research_assignment(game,n.id)),
                  key=lambda n:(-n.realm_index,-n.layer,n.id))[:24]
    war['roster']={'attacker':[n.id for n in people]}
    # Prewar estimate uses the same grade rules without adopting a remote
    # market or minting assets. The final cost uses the actual combat roster.
    catalog=commodity_catalog(world)
    market=dict(commodities={k:dict(tier=r['tier'],reference=r['base_price']) for k,r in catalog.items()})
    required=requirements.reference_need(game,war,'attacker',market)
    eligible={k for group in requirements.physical(game,war,'attacker') for k in requirements.suitable(market,group)}
    funds=sum(cash(game,e)+sum(depot.unit_value(game,r,k)*n for k,n in r['stock'].items() if k.startswith('item:') and k[5:] in eligible)
              for e in pool for r in [depot.find(game,e) or {'stock':{}}])
    return funds>=required*3


def wallet(war, side):
    return f'war-supply:{war["id"]}:{side}'


def front(game, maps, war, side):
    pool = entities(game,war,side)
    worlds = {e.world for e in entities(game,war,'attacker')+entities(game,war,'defender')}
    if len(worlds)>1 and pool:
        entity=next((e for e in pool if e.id==war[f'{side}_id']),pool[0])
        return entity.world, faction_site(entity)['id'], 0
    site=war_site(maps,war)['id']
    candidates=[]
    for entity in pool:
        if entity.world != war['world']:
            continue
        origin=faction_site(entity)['id']
        if origin==site:
            candidates.append((0,origin));continue
        plan=maps.travel_plan(entity.world,origin,site,0)
        if plan.status=='ok':candidates.append((plan.base_years,origin))
    distance,home=min(candidates) if candidates else (1000,site)
    return war['world'],home,distance


def initialize(game,maps,war):
    if 'logistics' in war:
        return
    ensure_state(game)
    war['logistics']=dict(version=1,round=0,intel={},actions={},sides={})
    for side in SIDES:
        account(game,wallet(war,side))
        world,location,distance=front(game,maps,war,side)
        ensure_regional_market(game,maps,world,location)
        war['logistics']['sides'][side]=dict(world=world,location=location,distance=distance,
            mobilized=0,spent=0,purchased=0,destroyed=0,transport_loss=0,coverage=1.,contributions={},items={},consumed_items={},cross_realm=False,
            stationing_year=game.player.age,stationing_credit=0.,stationing_paid=0,stationing_shortfall=0,mobilization_paid=0)
    for side in SIDES:
        requirements.refresh(game, war, side)
        replenish(game,maps,war,side,need(game,war,side)*3)
        row=war['logistics']['sides'][side]
        row['reference_need']=need(game,war,side)
        due=ceil(need(game,war,side)*.1)
        paid=min(due,balance(game,wallet(war,side)))
        transfer_value(game,wallet(war,side),f'background:{row["world"]}',paid,'一次性战争动员劳务')
        row['mobilization_paid']=paid



def replenish(game,maps,war,side,amount=None):
    state=war['logistics']['sides'][side]
    world,location,distance=front(game,maps,war,side)
    # A newly joined ally or relocated headquarters never teleports an existing pool.
    state['distance']=distance
    world,location=state['world'],state['location']
    ensure_regional_market(game,maps,world,location)
    desired=amount if amount is not None else supply.procurement_budget(game,war,side)
    remaining=max(0,int(desired));pool=[e for e in entities(game,war,side) if e.world==world]
    for entity in pool:register(game,depot.owner_kind(game,entity),entity.id,entity.world)
    paid=0
    # Proportional levy with saturation: depleted contributors are removed and
    # their shortfall is redistributed to remaining contributors, at most N passes.
    for _ in range(len(pool)+1):
        if not pool or not remaining:break
        weights={e.id:weight(e) for e in pool};total=sum(weights.values());progress=0;target=remaining
        for entity in pool:
            if entity.location_id!=location:
                plan=maps.travel_plan(world,entity.location_id,location,0)
                if plan.status!='ok':continue
                shipping=distance+plan.base_years
            else:shipping=distance
            share=min(remaining,max(1,ceil(target*weights[entity.id]/total)))
            take=supply.mobilize(game,maps,war,side,entity,share,shipping)
            contributions=state['contributions'];contributions[entity.id]=contributions.get(entity.id,0)+take
            remaining-=take;progress+=take;paid+=take
        if not progress:break
        pool=[e for e in pool if cash(game,e)>0 or depot.worth(game,e)>0]
    state['mobilized']+=paid
    reserve=requirements.energy(game,war,side)*4
    supply.purchase(game,maps,war,side,world,location,max(0,balance(game,wallet(war,side))-reserve))
    return paid


def burn(game,war,side,amount,reason):
    return supply.consume(game,war,side,amount,reason,cash_only=True)


def factor(war,side):
    ratio=war.get('logistics',{}).get('sides',{}).get(side,{}).get('coverage',1.)
    return 1. if ratio>=1 else .95 if ratio>=.75 else .8 if ratio>=.5 else .55 if ratio>=.25 else .25


def strategy(game,maps,war,side,action,rng):
    if action not in {'scout','forage','resupply'}:raise ValueError('未知军需策略')
    initialize(game,maps,war)
    book=war['logistics'];turn=book['round'];key=f'{side}:{action}'
    if book['actions'].get(key)==turn:raise ValueError('本轮已经执行过此项军需策略')
    enemy='defender' if side=='attacker' else 'attacker'
    cost=max(1,ceil(need(game,war,side)*(.03 if action=='scout' else .08)))
    if action=='resupply':
        if supply.turns(game,war,side)>=3.999:raise ValueError('军需已达到四场会战储备')
        before=supply.total(game,war,side)
        paid=replenish(game,maps,war,side)
        received=max(0,supply.total(game,war,side)-before)
        message=f'拨付 {paid} 灵石折值，送达军需现值 {received}；采购价差与运输损耗已结算。'
    else:
        if balance(game,wallet(war,side))<cost:raise ValueError('军需不足以派出侦察或劫粮队伍')
        burn(game,war,side,cost,'侦察军费' if action=='scout' else '劫粮军费')
        own=sum(weight(e) for e in entities(game,war,side));other=sum(weight(e) for e in entities(game,war,enemy))
        probability=min(.85,max(.2,.5+.2*(own-other)/max(1,own+other)))
        success=rng.random()<probability
        if action=='scout':
            if success:book['intel'][side]=dict(value=supply.total(game,war,enemy),round=turn,need=need(game,war,enemy),base=book['sides'][enemy]['location'],turns=supply.turns(game,war,enemy))
            message='侦察成功，获得敌方军需快照。' if success else '侦察失败，敌方军需仍不明。'
        elif action=='forage':
            amount=supply.raid(game,war,side,need(game,war,side)) if success else 0
            message=f'因粮于敌成功，缴获军需折值 {amount}。' if success else '劫粮失败，出击军费已经消耗。'
        else:raise ValueError('未知军需策略')
    book['actions'][key]=turn
    return message


def begin_round(game,maps,war,rng,player_side=None):
    initialize(game,maps,war)
    book=war['logistics']
    if player_side is not None:war['player_side']=player_side
    for side in SIDES:
        requirements.refresh(game, war, side)
        if side!=player_side:
            if supply.turns(game,war,side)<2:replenish(game,maps,war,side)
            if supply.turns(game,war,side)<1 and book['actions'].get(f'{side}:forage')!=book['round']:
                if balance(game,wallet(war,side))>=ceil(need(game,war,side)*.08):strategy(game,maps,war,side,'forage',rng)
        required=need(game,war,side)
        row=book['sides'][side]
        row['reference_need']=required
        supply.purchase(game,maps,war,side,row['world'],row['location'],ceil(required*(.1 if row.get('cross_realm') and side=='attacker' else .2)))
        coverage=supply.consume_battle(game,war,side)
        book['sides'][side]['coverage']=coverage
        war['morale'][side]=max(0,war['morale'][side]-25*(1-coverage))
    book['round']+=1


def public(game,war,player_side):
    book=war.get('logistics');result={}
    for side in SIDES:
        row=(book or {}).get('sides',{}).get(side,{})
        visible=player_side is None or player_side==side
        intel=(book or {}).get('intel',{}).get(player_side,{}) if not visible else {}
        value=supply.total(game,war,side) if visible and book else None
        required=need(game,war,side)
        def label(world,location):
            return next((r['name'] for r in CONTENT_DOCUMENTS['maps.json']['worlds'].get(world,{}).get('locations',[]) if r['id']==location),location)
        result[side]=dict(known=visible,balance=value,
            snapshot=intel.get('value'),snapshot_round=intel.get('round'),round=(book or {}).get('round',0),
            snapshot_turns=intel.get('turns',intel.get('value',0)/max(1,intel.get('need',1))) if intel else None,
            snapshot_base=label(row.get('world'),intel.get('base')) if intel else None,
            turns=supply.turns(game,war,side) if value is not None and book else 0,
            factor=factor(war,side) if visible else None,
            base=label(row.get('world'),row.get('location')) if visible else None,
            loss=min(.7,.02+row.get('distance',0)*.003+(.2 if row.get('cross_realm') else 0)) if visible else None,
            items=[dict(id=k,name=ITEM_CATALOG[k].name if k in ITEM_CATALOG else k,quantity=n,value=round(supply.price(game,row,k)*n)) for k,n in row.get('items',{}).items() if n] if visible else [],
            need=need(game,war,side) if visible else None,
            coverage=row.get('coverage',1) if visible else None,
            realm_groups=dict(row.get('realm_groups', {})) if visible else {},
            purchased=row.get('purchased',0) if visible else None,destroyed=row.get('destroyed',0) if visible else None,
            distance=row.get('distance') if visible else None)
    return result


def action_quotes(game,war,side):
    if not side:return []
    book=war.get('logistics',{});required=need(game,war,side)
    cash=balance(game,wallet(war,side)) if book else 0
    rows=[]
    for action,name,ratio in [('deploy_half','半数动员',.5),('deploy_all','全员动员',1.)]:
        current=war.get('deployment',{}).get(side,1.)
        rows.append(dict(action=action,name=name,allowed=current!=ratio,reason='当前动员范围' if current==ratio else '',
                         description='调整原参战名册中的实际出战范围，同时改变战力、军需与劳动占用。'))
    for action,name,ratio in [('scout','侦察敌情',.03),('forage','因粮于敌',.08),('resupply','补充物资',0)]:
        cost=max(1,ceil(required*ratio)) if ratio else 0
        reason='本轮已执行' if book.get('actions',{}).get(f'{side}:{action}')==book.get('round',0) else ''
        if cost>cash:reason='前线灵石不足'
        if action=='resupply' and book and supply.turns(game,war,side)>=3.999:reason='已有四回合储备'
        rows.append(dict(action=action,name=name,allowed=not reason,reason=reason,
            description=f'消耗前线灵石 {cost}；可能失败，每回合一次。' if cost else '从真实府库拨付至四回合目标，按距离扣损。'))
    return rows


def refund(game,war):
    if not war.get('logistics') or war['logistics'].get('refunded'):return
    for side in SIDES:
        source=wallet(war,side);remaining=opening=balance(game,source)
        pool=entities(game,war,side);contributions=war['logistics']['sides'][side]['contributions']
        supply.return_items(game,war,side,pool)
        total=sum(contributions.get(e.id,0) for e in pool)
        for i,entity in enumerate(pool):
            amount=remaining if i==len(pool)-1 else min(remaining,int(opening*contributions.get(entity.id,0)/max(1,total)))
            register(game,depot.owner_kind(game,entity),entity.id,entity.world)
            transfer_value(game,source,depot.treasury(game,entity),amount,'停战退回未消耗军需')
            remaining-=amount
        if remaining:burn(game,war,side,remaining,'失去所属组织的战场辎重清算')
    war['logistics']['refunded']=True
