"""Independent immortal-equipment grades, using the original owned equipment."""
import copy
import re
import uuid

from ..content_registry import ITEM_CATALOG, WORLD_SYSTEMS
from ..models import Item
from ..rules import has_item, remove_item

MATERIALS = (
    ('triple_forged_god_demon_iron', '三铸神魔铁'),
    ('yin_yang_hespring_steel', '阴阳和泉钢'),
    ('primordial_taiyi_silver', '原初太一银'),
    ('innate_yuanhe_alloy', '先天元合金'),
)
GRADE_NAMES = {5:'五品',4:'四品',3:'三品',2:'二品',1:'一品'}


def source_item(game):
    """Original standard natal item, not a second inventory/resource pool."""
    natal = game.natal_artifact
    if natal.get('source_item'):
        return Item.from_dict(copy.deepcopy(natal['source_item']))
    return copy.deepcopy(ITEM_CATALOG[natal['item_id']])


def tier(item):
    from .item_qualification import force_tier
    return force_tier(item)


def natal_tier(game):
    natal = game.natal_artifact
    if not natal:
        return 1
    if natal.get('crafted_artifact_id'):
        source = next((a for a in game.player.crafted_artifacts if a['id']==natal['crafted_artifact_id']), {})
        if not source:return 1
        return max(tier(source), int(natal.get('force_tier',1)))
    return max(tier(source_item(game)), int(natal.get('force_tier',1)))


def active_natal_tier(game):
    natal=game.natal_artifact
    if natal.get('crafted_artifact_id'):
        source=next((a for a in game.player.crafted_artifacts if a['id']==natal['crafted_artifact_id']),{})
        if source.get('tianji') and (not WORLD_SYSTEMS.get('tianji_artifacts',{}).get('enabled') or source['id'] not in game.player.equipped_crafted_artifact_ids):
            return 1
    return natal_tier(game)


def release_natal_item(game):
    item=source_item(game)
    natal=game.natal_artifact
    item.quantity=1
    promoted=int(natal.get('force_tier',1))>=2
    quality=natal.get('immortal_grade')
    if promoted or quality is not None:
        if not item.artifact_origin_id:
            item.artifact_origin_id=item.id
            item.id='refined:'+uuid.uuid4().hex
        item.force_tier=max(tier(item),int(natal.get('force_tier',1)))
        item.immortal_grade=quality or item.immortal_grade or 5
        if not {'artifact','equipment'} & set(item.tags):item.tags.append('equipment')
    return item


def refinement_count(game):
    natal = game.natal_artifact
    if 'refinement_count' in natal:
        return max(0,int(natal['refinement_count']))
    # Only explicit manual-temperature receipts since this actual binding count.
    # Neither an old level nor passive years is evidence of a paid refinement.
    count = 0
    for record in reversed(game.history):
        if record.event_id != 'SYS_NATAL_ARTIFACT':
            continue
        if record.result in {'bound','unbound'}:
            break
        state = record.state_diff.get('artifact', {})
        if state.get('item_id') != natal.get('item_id') or state.get('bound_age') != natal.get('bound_age'):
            continue
        if record.result == 'refined':
            count += 1
        elif record.result == 'refined_all':
            match = re.search(r'连续温养 (\d+) 次', record.summary)
            if match:count += int(match[1])
    return count


def promotion(game):
    count = refinement_count(game) if game.natal_artifact else 0
    reason = ('尚未认主本命法宝' if not game.natal_artifact else
              '已具备仙级伤害资格' if natal_tier(game)>=2 else
              '须实际温养超过36次（至少37次）' if count<37 else
              '需要三铸神魔铁×1' if not has_item(game.player,MATERIALS[0][0]) else '')
    if game.natal_artifact.get('crafted_artifact_id'):
        source=next((a for a in game.player.crafted_artifacts if a['id']==game.natal_artifact['crafted_artifact_id']),{})
        if source.get('tianji') and not WORLD_SYSTEMS.get('tianji_artifacts',{}).get('enabled'):
            reason='请先启用神机百变'
    reason=operation_reason(game) or reason
    return dict(refinement_count=count,damage_type='仙' if game.natal_artifact and natal_tier(game)>=2 else '凡',
                can_promote=not reason,promote_reason=reason,promote_material=MATERIALS[0][0],promote_quantity=1)


def promote_natal(game):
    reason=operation_reason(game)
    if reason:raise ValueError(reason)
    info=promotion(game)
    if not info['can_promote']:raise ValueError(info['promote_reason'])
    remove_item(game.player,MATERIALS[0][0])
    game.natal_artifact['refinement_count']=info['refinement_count']
    game.natal_artifact['force_tier']=2
    if game.natal_artifact.get('crafted_artifact_id'):
        artifact=next(a for a in game.player.crafted_artifacts if a['id']==game.natal_artifact['crafted_artifact_id'])
        artifact['force_tier']=2
    else:
        game.natal_artifact['immortal_grade']=game.natal_artifact.get('immortal_grade') or 5


def available(game):
    return int(WORLD_SYSTEMS['world_profiles'].get(game.player.world,{}).get('tier',0))==3 and not game.guixu_state.get('player_session')


def title(game):
    from .. import content_registry as registry
    names={'demonic':('official.asura-manifestation','魔器'),
           'monster':('official.monster-bloodlines','妖器'),
           'ghost':('official.ghost-reincarnation','魂器'),
           'buddhist':('official.buddhist-dharma','佛器'),
           'confucian':('official.sage-way','儒器')}
    owner,name=names.get(game.player.path,('', '仙器'))
    return name if any(r.get('id')==owner and r.get('status')=='loaded' for r in registry.EXTENSION_REPORT) else '仙器'


def entries(game):
    bag={i.crafted_artifact_id for i in game.player.inventory if i.quantity>0 and i.crafted_artifact_id}
    natal=game.natal_artifact
    for item in game.player.inventory:
        if item.quantity>0 and not item.crafted_artifact_id and {'artifact','equipment'} & set(item.tags) and tier(item)>=2:
            yield 'bag:'+item.id,item,'bag'
    for artifact in game.player.crafted_artifacts:
        if artifact.get('tianji') and not WORLD_SYSTEMS.get('tianji_artifacts',{}).get('enabled'):continue
        if artifact['id'] in bag and tier(artifact)>=2:
            yield 'crafted:'+artifact['id'],artifact,'crafted'
    if natal and not natal.get('crafted_artifact_id') and natal_tier(game)>=2:
        yield 'natal:'+natal['item_id'],natal,'natal'


def grade(row):
    value=row.get('immortal_grade') if isinstance(row,dict) else row.immortal_grade
    if value is None:return 5
    if type(value) is not int or not 1 <= value <= 5:raise ValueError('仙器品阶无效')
    return value


def operation_reason(game):
    from .soul_actions import blocked
    if blocked(game):return '请先处理事件、试炼、拘禁或修为封印'
    if game.map_journey:return '请先完成当前旅行'
    runtime=game.heavens_state.get('runtime')
    if runtime:
        from .heavens.state import active_task
        if active_task(runtime):return '请先继续或结束当前诸天亲自任务'
    return ''


def public(game):
    active=available(game)
    quantities={i.id:i.quantity for i in game.player.inventory}
    rows=[]
    if active:
        blocked=operation_reason(game)
        for identity,item,kind in entries(game):
            rank=grade(item)
            material=MATERIALS[5-rank] if rank>1 else None
            reason=blocked or ('已达一品' if rank==1 else '' if quantities.get(material[0],0)>=3 else f'需要{material[1]}×3')
            rows.append(dict(id=identity,name=item['name'] if isinstance(item,dict) else item.name,
                             source=kind,grade=rank,grade_name=GRADE_NAMES[rank],damage_type='仙',
                             next_grade=rank-1 if rank>1 else None,material_id=material[0] if material else None,
                             material_name=material[1] if material else None,cost=3 if material else 0,
                             can_refine=not reason,reason=reason))
    return dict(available=active,title=title(game),revision=game.updated_at,equipment=rows,
                materials=[dict(id=k,name=n,quantity=quantities.get(k,0)) for k,n in MATERIALS])


def cultivate(game,identity,expected_grade):
    if not available(game):raise ValueError('只有三级普通界面可以培养仙器')
    reason=operation_reason(game)
    if reason:raise ValueError(reason)
    found=next(((item,kind) for key,item,kind in entries(game) if key==identity),None)
    if not found:raise ValueError('仙器不在原持有记录中，或伤害类型不为仙，请刷新')
    item,kind=found
    rank=grade(item)
    if type(expected_grade) is not int or expected_grade!=rank:raise ValueError('仙器品阶已变化，请刷新后再培养')
    if rank<=1:raise ValueError('仙器已达一品')
    material,name=MATERIALS[5-rank]
    if not has_item(game.player,material,3):raise ValueError(f'需要{name}×3')
    remove_item(game.player,material,3)
    if kind=='bag':
        # Split one real unit; later purchases can never inherit this grade.
        original=item.id
        if not item.artifact_origin_id:
            refined=Item.from_dict(item.to_dict())
            refined.quantity=1
            refined.artifact_origin_id=original
            refined.id='refined:'+uuid.uuid4().hex
            if game.player.ghost_attachment and game.player.ghost_attachment.get('item_id')==original:
                game.player.ghost_attachment['item_id']=refined.id
            remove_item(game.player,original)
            game.player.inventory.append(refined)
            item=refined
        item.immortal_grade=rank-1
    else:
        item['immortal_grade']=rank-1
    return f'消耗{name}×3，{item["name"] if isinstance(item,dict) else item.name}由{GRADE_NAMES[rank]}培养至{GRADE_NAMES[rank-1]}；原战力不变。'
