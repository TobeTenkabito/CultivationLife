"""Owned puppet operating charge. No regeneration or inferred past refills."""
from ..npc_development_content import TIERS, definitions as training_materials
from ..puppet_content import definitions as components

CAPACITY = 100
ACTION_COST = 5


def current(asset):
    return max(0., min(CAPACITY, float(asset.get('operating_energy', 0))))


def stage(asset):
    realm = int(asset.get('realm_index', 0))
    return 1 if realm <= 5 else 2 if realm <= 8 else 3


def attack_cost(asset):
    return 10. * max(1, int(asset.get('realm_index', 9)) - 8)


def source_definition(identity):
    row=training_materials().get(identity)
    if row and row['path']=='puppet' and row['axis']=='energy':
        return dict(id=identity,name=row['name'],stage=row['tier'],rank=row['rank'],force_tier=2 if row['rank']>=9 else 1)
    row=components().get(identity)
    if row and row['slot']=='energy':
        return dict(id=identity,name=row['name'],rank=row['tier'],stage=1 if row['tier']<=5 else 2 if row['tier']<=8 else 3,
                    force_tier=2 if row['tier']>=9 else 1)
    return None


def source_id(asset):
    if 'energy_source_id' in asset:return asset['energy_source_id']
    return next((row['id'] for row in asset.get('components',[]) if row.get('slot')=='energy'),None)


def force_tier(asset):
    return (source_definition(source_id(asset)) or {}).get('force_tier',1)


def operation(asset, definition=None):
    definition=definition or source_definition(source_id(asset)) or dict(rank=1)
    rank=definition['rank'];realm=max(1,int(asset.get('realm_index',1)))
    gap=realm-rank
    reason=('仙阶能源超出凡阶傀儡承载极限' if rank>=9 and realm<9 else
            '能源低于傀儡三阶及以上，无法驱动' if gap>=3 else '')
    cost=0 if reason else (5,20,60)[gap] if gap>=0 else 2 if gap==-1 else 1 if gap==-2 else .5
    return dict(rank=rank,compatible=not reason,reason=reason,cost=cost)


def can_deploy(player,asset):
    from .combat_plan import effective_plan
    use=operation(asset)
    return (use['compatible'] and current(asset)>=use['cost']) or effective_plan(player)['puppet_supply']


def replacements(game,asset):
    rows=[];world_tier=TIERS.get(game.player.world,0)
    for item in game.player.inventory:
        definition=source_definition(item.id)
        if definition and item.quantity>0:
            use=operation(asset,definition)
            rows.append(dict(definition,key='bag:'+item.id,durability=CAPACITY,quantity=item.quantity,
                cost=use['cost'],reason=use['reason'],allowed=world_tier>=definition['stage'] and use['compatible']))
    for saved in asset.get('energy_spares',[]):
        definition=source_definition(saved.get('source_id')) or dict(id=None,name='未标定能源',stage=1,rank=1,force_tier=1)
        use=operation(asset,definition)
        rows.append(dict(definition,key='spare:'+saved['id'],durability=saved['durability'],quantity=1,
            cost=use['cost'],reason=use['reason'],allowed=world_tier>=definition['stage'] and use['compatible']))
    return rows


def replace(game,asset,key):
    from ..rules import remove_item
    from uuid import uuid4
    choice=next((r for r in replacements(game,asset) if r['key']==key),None)
    if not choice:raise ValueError('所选能源不存在或已经用完')
    if not choice['allowed']:raise ValueError(choice['reason'] or '当前界面不能安装该品阶能源')
    if key.startswith('bag:') and source_id(asset)==choice['id'] and current(asset)>=CAPACITY:
        raise ValueError('同类能源耐久已满，无需更换')
    previous=dict(id=uuid4().hex,source_id=source_id(asset),durability=current(asset))
    if key.startswith('bag:'):
        if not remove_item(game.player,choice['id'],1):raise ValueError('缺少所选能源')
    else:
        asset['energy_spares']=[r for r in asset.get('energy_spares',[]) if 'spare:'+r['id']!=key]
    if previous['durability']>0:asset.setdefault('energy_spares',[]).append(previous)
    asset['energy_source_id']=choice['id'];asset['operating_energy']=choice['durability']
    return f"为{asset.get('name','傀儡')}装上{choice['name']}，能源耐久{choice['durability']:g}/{CAPACITY}；卸下的未耗尽能源保留原耐久。"


def charge_quote(game, asset):
    tier = stage(asset)
    if TIERS.get(game.player.world, 0) < tier:
        raise ValueError('当前界面不能为该品阶傀儡充能')
    rank=max(1,int(asset.get('realm_index',1)))
    identity=next(row['id'] for row in training_materials().values() if row.get('rank')==rank and row['axis']=='energy')
    owned = sum(i.quantity for i in game.player.inventory if i.id == identity)
    before = current(asset)
    return dict(material_id=identity, material_count=1, material_owned=owned,
                before=before, after=CAPACITY, can_charge=before < CAPACITY and owned > 0,
                reason='储能已满' if before >= CAPACITY else '' if owned else '缺少傀儡能源晶')
