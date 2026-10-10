"""Build at the actual local site, consuming local supplies and the owner treasury."""
from ..content_registry import ITEM_CATALOG, WORLD_SYSTEMS
from ..economy_content import material_id
from .economy import depot, organizations
from .economy.ledger import balance, transfer_value
from .economy.local_market import quote, require_access
from .economy.state import ensure_regional_market, reprice
from .organization_heritage import controls


def owners(game):
    return [s for s in [*game.sects.values(),*([game.family] if game.family else [])]
            if s.kind!='institution' and controls(game,s)]


def requirements(world):
    tier=WORLD_SYSTEMS['world_profiles'][world]['tier'];grade={1:2,2:6,3:9}[tier]
    return {material_id(world,grade,role):qty for role,qty in [('ore_structure',8),('ore_conduct',8),('ore_store',4)]}


def estimate(game,entity):
    p=game.player;tier=WORLD_SYSTEMS['world_profiles'][p.world]['tier']
    fee={1:25000,2:1250000,3:40000000}[tier]
    market=game.economy_v2.get('markets',{}).get(f'{p.world}:{p.location_id}',{})
    stores=depot.find(game,entity) if entity.location_id==p.location_id else None
    materials=[];total=fee;available=True
    for identity,qty in requirements(p.world).items():
        held=min(qty,(stores or {}).get('stock',{}).get('item:'+identity,0));missing=qty-held
        product=market.get('commodities',{}).get(identity)
        payable=quote(product,'buy',missing)['total'] if missing and product and product['stock']>=missing else 0
        available=available and (not missing or bool(product and product['stock']>=missing))
        total+=payable
        materials.append(dict(id=identity,name=ITEM_CATALOG[identity].name,quantity=qty,stored=held,purchase=missing,cost=payable))
    kind=depot.owner_kind(game,entity)
    funds=int(game.intrigue_state.get('factions',{}).get(f'{kind}:{entity.id}',{}).get('resources',0))
    return dict(owner_id=entity.id,owner_name=entity.name,fee=fee,total=total,balance=funds,
        materials=materials,can_build=available and funds>=total,stock_available=available)


def build(game,maps,identity,existing):
    require_access(game)
    entity=next((s for s in owners(game) if s.id==identity),None)
    if not entity: raise ValueError('建造传送阵须有本界宗门或家族控制权，决策权不足以建阵')
    p=game.player
    site=maps.location(p.world,p.location_id)
    if not site or site.get('min_realm_index',0)>p.realm_index: raise ValueError('当前地图不允许建阵')
    if p.location_id in existing: raise ValueError('当地已有传送阵，不能重复建造')
    organizations.register(game,depot.owner_kind(game,entity),entity.id,entity.world)
    ensure_regional_market(game,maps,p.world,p.location_id)
    plan=estimate(game,entity)
    if not plan['stock_available']: raise ValueError('当地资材不足，请先运入或等待补货；不会遥取异地库存')
    if not plan['can_build']: raise ValueError('势力府库灵石不足以支付建阵及当地资材采购')
    source=depot.treasury(game,entity);market=game.economy_v2['markets'][f'{p.world}:{p.location_id}']
    stores=depot.find(game,entity) if entity.location_id==p.location_id else None
    for r in plan['materials']:
        if r['stored']: stores['stock']['item:'+r['id']]-=r['stored']
        if r['purchase']:
            product=market['commodities'][r['id']];bill=quote(product,'buy',r['purchase'])
            transfer_value(game,source,f'market:{market["id"]}',bill['total'],'传送阵当地资材采购')
            transfer_value(game,f'market:{market["id"]}',f'operator:{market["id"]}',bill['fee'],'建阵资材采购手续费')
            product['stock']-=r['purchase'];product['volume']+=r['purchase']
            from .economy.market_power import record_trade
            record_trade(game,market,r['id'],source,'buy',r['purchase'])
            market['turnover']+=bill['gross'];market['fees']+=bill['fee'];reprice(game,market,product)
    organizations.procure(game,source,p.world,plan['fee'],'传送阵施工劳务')
    if stores: depot.record(stores,game,'当地建阵消耗原府库矿材，未占用申请预留物资')
    game.economy_v2.setdefault('teleport_arrays',{})[f'{p.world}:{p.location_id}']=dict(
        world=p.world,location=p.location_id,owner_id=entity.id,owner_kind=depot.owner_kind(game,entity),built_year=p.age)
    return f'{entity.name}实付{plan["total"]}灵石并消耗当地矿材，在{site["name"]}建成传送阵。通行仍遵守本界路线与境界限制。'
