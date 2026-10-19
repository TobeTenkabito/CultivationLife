"""Fixed-site project quotes consume original inventory, never new resource pools."""
import hashlib
import json

from ..building_rules import config, ensure_state
from ..building_schema import address
from ..content_registry import ITEM_CATALOG, WORLD_SYSTEMS
from ..economy_content import BASE_PRICES, material_id
from ..rules import remove_item, combat_power, expected_combat_power, max_mp
from .economy.enterprise_state import owner_allowed

POPULATIONS = dict(cultivator='修士之城', mortal='凡人之城', mixed='混居之城')
USES = dict(military='军事型', economic='经济型', comprehensive='综合型')


def owns(game, row):
    owner=row['owner']
    return (owner==dict(kind='player',id=game.id) or row['type']=='industry' and
            owner_allowed(game,owner['kind'],owner['id'],row['address']['world']))


def grade(world):
    tier=WORLD_SYSTEMS['world_profiles'][world]['tier']
    return config()['city_material_grade'][str(tier)]


def quote(game, purpose, row=None):
    world=game.player.world
    materials={}
    reason=''
    if purpose in {'city','develop','govern'} or row and row['type']=='city':
        level=1 if purpose=='city' or purpose=='rebuild' else min(3,row['level']+1) if purpose=='develop' else row['level']
        rank=grade(world)
        for role, amounts in config()['city_materials'].items():
            materials[material_id(world,rank,role)]=amounts[level-1] if purpose!='govern' else max(1,amounts[0]//60)
        if row and purpose in {'develop','govern'} and 'works' in row.get('facilities',[]):
            materials={key:max(1,(n*4+4)//5) for key,n in materials.items()}
        coins=int(BASE_PRICES[rank-1]*config()['city_labor_units'][level-1])
        if purpose=='govern':coins=max(1,coins//20)
        if purpose=='city' and any(r['type']=='city' and r['address']==address(game)
                and owns(game,r) for r in game.building_state.get('records',{}).values()):
            reason='每处地域只能拥有一座自建城市，遗址须原址重建'
        if purpose=='develop':
            if row['level']>=3:reason='已是三级大都市'
            elif row.get('development',0)<config()['city_development'][row['level']-1]:reason='城市治理进度不足'
        if purpose=='govern':
            used=game.building_state.get('city_usage',{}).get(row['id'],{})
            if row['level']>=3:reason='城市已达三级'
            elif used.get('govern_year')==game.player.age:reason='本城本年已经办理治理，须在城外度过真实年份'
            elif row.get('development',0)>=config()['city_development'][row['level']-1]:reason='治理进度已足，请先扩建'
    elif row.get('subtype')=='cave':
        coins=int(config()['cave_prices'][row['quality']][row['level']-1])*WORLD_SYSTEMS['world_profiles'][world]['tier']
    elif row.get('subtype')=='temple':
        from .buddhist.rules import buddhist_config, buddhist_active
        cfg=buddhist_config()
        coins=int(cfg['temples'][1]['cost'])*cfg['temple_tier_scale']**(WORLD_SYSTEMS['world_profiles'][world]['tier']-1)
        if not buddhist_active(game):reason='须启用佛修扩展并由佛修主持重建'
    elif row['type']=='industry':
        from .economy.enterprise_rules import title_cost
        coins=title_cost(world,row['subtype'],row['level'])
    else:
        coins=1000*row['level']*WORLD_SYSTEMS['world_profiles'][world]['tier']
    if row and purpose in {'develop','govern'} and not owns(game,row):reason='只有城市所有者可以办理'
    if row and purpose=='rebuild' and row['status']!='destroyed':reason='建筑并未被摧毁'
    if row and purpose=='rebuild' and not (owns(game,row) or row['type']=='city' and row.get('public')):
        reason='没有重建权限，请先联系所有者'
    funds=sum(i.quantity for i in game.player.inventory if i.id=='spirit_stone')
    held={i.id:i.quantity for i in game.player.inventory}
    missing=[ITEM_CATALOG[key].name for key,n in materials.items() if held.get(key,0)<n]
    if not reason and (funds<coins or missing):reason='灵石或筑城材料不足'
    fingerprint=dict(purpose=purpose,world=world,location=game.player.location_id,coins=coins,materials=materials,
        identity=row['id'] if row else None,owner=row.get('owner') if row else None,
        level=row.get('level') if row else None,status=row.get('status') if row else None)
    token=hashlib.sha256(json.dumps(fingerprint,sort_keys=True).encode()).hexdigest()[:20]
    return dict(coins=coins,materials=materials,reason=reason,token=token)


def bill_text(bill):
    return f"灵石 {bill['coins']:,}" + ''.join(f"；{ITEM_CATALOG[key].name} ×{n:,}" for key,n in bill['materials'].items())


def pay(game,bill,reason):
    if bill['reason']:raise ValueError(bill['reason'])
    held={i.id:i.quantity for i in game.player.inventory}
    if held.get('spirit_stone',0)<bill['coins'] or any(held.get(k,0)<n for k,n in bill['materials'].items()):
        raise ValueError('灵石或工程材料不足')
    for key,n in bill['materials'].items():remove_item(game.player,key,n)
    remove_item(game.player,'spirit_stone',bill['coins'])
    from .economy.local_market import operator_account
    from .economy.ledger import record_external
    record_external(game,'player',operator_account(game),bill['coins'],reason)


def persist(game,row):
    import copy
    return ensure_state(game)['records'].setdefault(row['id'],copy.deepcopy(row))


def defense(row):
    world=row['address']['world']
    cap=WORLD_SYSTEMS['world_profiles'][world]['npc_realm_cap']
    floor={1:1,2:5,3:9}[WORLD_SYSTEMS['world_profiles'][world]['tier']]
    if row['type']=='city':
        rank=min(cap,floor+row['level']-1)
        if row.get('population')=='mortal':rank=max(0,floor-1)
        return expected_combat_power(rank,5 if rank else 1)*dict(military=1.5,economic=.8,comprehensive=1.)[row['subtype']]*row['level']*(1.25 if row['status']=='intact' and 'watch' in row.get('facilities',[]) else 1.)
    return expected_combat_power(floor,1)*row['level']


def demolition_reason(game,row):
    if row['type']=='scenery':return '自然景观不可摧毁'
    if row['status']=='destroyed':return '已经是遗址'
    if owns(game,row):return ''
    if combat_power(game.player)<defense(row):return '当前实际战力不足以破坏此处防御'
    if game.player.mp<max(1,round(max_mp(game.player)*.25)):return '强行摧毁需要至少四分之一法力'
    return ''
