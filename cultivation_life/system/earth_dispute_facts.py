"""Read authorized original assets only; report registration is an explicit command."""
import math
from ..content_registry import ITEM_CATALOG, restricted_acquisition
from .earth_temple_rules import state, temple, city
from .building_assets import local_rows
from . import building_projects as projects
from .economy.enterprise_state import estates, owner_allowed
from .economy.state import local_market
from .earth_temple_facilities import fingerprint


def sources(game, maps):
    p = game.player
    result = {}
    for row in estates(game).values():
        if (row['world'] == p.world and row['location'] == p.location_id and row['kind'] == 'farm'
                and row.get('building_status') != 'destroyed'
                and owner_allowed(game,row['owner_kind'],row['owner_id'],row['world'])):
            result['water'] = dict(target=row['id'], title='本地药田', evidence='原药田仍在此地，经营权可核验；放水会暂停新投产并延后在制批次。')
            break
    market = local_market(game)
    if market and (market['world'],market['location']) == (p.world,p.location_id):
        products = [(k,v) for k,v in market['commodities'].items() if k in ITEM_CATALOG
                    and not restricted_acquisition('item',k) and v['stock'] < v['target']*.5
                    and v['tier'] <= p.realm_index+1]
        if products:
            key,row = min(products,key=lambda pair:(pair[1]['stock']/max(1,pair[1]['target']),pair[0]))
            result['supply'] = dict(target=key, title=ITEM_CATALOG[key].name, market=market['id'],
                quantity=min(20,max(1,math.ceil(row['target']*.5-row['stock']))), evidence='原市场库存低于目标的一半；只能交付本人实际持有的商品，不凭空补货。')
    if maps:
        for road in maps.worlds.get(p.world,{}).get('routes',[]):
            if p.location_id not in (road['from'],road['to']): continue
            other = road['to'] if road['from']==p.location_id else road['from']
            if maps.travel_plan(p.world,p.location_id,other,p.realm_index).status != 'ok': continue
            result['road'] = dict(target=other, edge=[p.location_id,other], title=maps.location(p.world,other)['name'],
                evidence='登记后该原道路本期塌方生效：普通地图远行额外5年。清障可恢复，缓行方案仍多耗2年；传送不受影响。')
            break
    row = temple(game)
    if row and projects.owns(game,row):
        result['property'] = dict(target=row['id'],title=row['name'],evidence='庙契归主持所有，街坊请求开放公共使用；本案须明确开放范围，土地庙产权保持不变。')
    for row in p.formation_ground_arrays:
        if (row.get('owner_kind')=='player' and row.get('owner_id')=='player' and row.get('creator_id')==game.id
                and row.get('world')==p.world and row.get('location_id')==p.location_id and row.get('durability',100)<100):
            result['guard'] = dict(target=row['id'],title=row['name'],evidence=f"镇地阵完整度为{row['durability']:g}%；须筹措修阵资源，或暂停本庙护境承诺。")
            break
    for row in local_rows(game):
        if row['status']=='destroyed' and row.get('subtype')!='temple' and (projects.owns(game,row) or row['type']=='city' and row.get('public')):
            result['rebuild'] = dict(target=row['id'],title=row['name'],evidence='原建筑确为遗址；完整重建沿原报价与权限，旧库存及领取次数保留。')
            break
    return result


def original(game, case):
    kind, identity = case['kind'], case['target']
    if kind=='water':
        row=estates(game).get(identity)
        if row and row['world']==game.player.world and row['location']==game.player.location_id and row.get('building_status')!='destroyed' and owner_allowed(game,row['owner_kind'],row['owner_id'],row['world']): return row
    elif kind=='supply':
        market=local_market(game)
        if market and market['id']==case['market']:
            return market['commodities'].get(identity)
    elif kind=='guard':
        return next((a for a in game.player.formation_ground_arrays if a['id']==identity and a.get('creator_id')==game.id
                     and a.get('owner_kind')=='player' and a.get('owner_id')=='player'
                     and a['world']==game.player.world and a['location_id']==game.player.location_id),None)
    elif kind in {'rebuild','property'}:
        return next((r for r in local_rows(game) if r['id']==identity and
                     (projects.owns(game,r) or kind=='rebuild' and r['type']=='city' and r.get('public'))),None)
    elif kind=='road': return case
    return None


def stale_reason(game, case):
    row=original(game,case)
    if row is None: return '原对象或权限已经失效；可撤回本案，不能代造对象完成'
    if case['kind']=='rebuild' and row['status']!='destroyed': return '原建筑已由其他途径修复，可撤回已消解事项'
    if case['kind']=='guard' and row.get('durability',100)>=100: return '原镇地阵已修复，可撤回已消解事项'
    if case['kind']=='supply' and row['stock']>=row['target']*.5: return '原市场已不缺货，可撤回已消解事项'
    return ''
