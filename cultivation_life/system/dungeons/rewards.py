"""Frozen expedition rewards, original inventory/learning/equipment settlement."""
import copy
import hashlib
import json
from functools import lru_cache
from ...content_registry import TECHNIQUE_CATALOG, ITEM_CATALOG, WORLD_SYSTEMS, MARKET_GOODS, REALMS, ACTIONS
from ...models import Item, Technique
from ...rules import add_item, learn_technique, expected_combat_power
from ...technique_effect_generation import generate_effect, concordance_effect
from ...technique_effect_schema import describe, validate_effect
from .prose_expansion import NAMES as EXTRA_NAMES

THEMES = {'water':'沧溟','mountain':'山岳','fire':'离火','frost':'霜雪',
          'fort':'镇封','shadow':'寂灭','grove':'青木','ruins':'玄文'}

RELIC_FORMS = {
    '护道印':'印底的篆文磨得发亮，托在掌中还能摸出笔锋。',
    '镇灵环':'环身由两股银丝拧成，接口处扣着一粒乌金。',
    '承光镜':'镜背铸着一枝梅，迎光转动时，镜中花影比镜身慢上半拍。',
    '照影灯':'灯腹开了六扇小窗，火苗在窗纸上映出细细的竹叶。',
    '凝华佩':'佩上还系着一截旧绦，贴近手腕时，玉里的白絮便缓缓舒展。',
    '观星盘':'拨动外圈，盘上七枚银钉依次指向同一片星野。',
    '听泉铃':'铃舌是一颗磨圆的青石，摇响时像水珠落进深潭。',
    '引风幡':'幡尾缀着三枚鱼形铜片，风一起，鱼尾便齐齐转向。',
    '栖云伞':'将伞骨撑开一寸，伞面上绣的山影便退远一分。',
    '分水针':'针身细如松芒，一滴水沿针尖分成两股滑落。',
    '照夜剑':'剑脊上留着磨石走过的细痕，近锷处藏着一线青光。',
    '温玉鼎':'三只鼎足各衔一颗白石，鼎腹尚有淡淡松脂香。',
}


@lru_cache(maxsize=144)
def equipment_anchor(realm,world=None):
    """Use authored market grades; ordinary equipment has no grade:N tag."""
    rows=[r for r in MARKET_GOODS if r.get('kind')=='item' and r.get('tier')==realm
          and r.get('content_id') in ITEM_CATALOG]
    eligible=[r for r in rows if ITEM_CATALOG[r['content_id']].combat_bonus>0
              and 'pill' not in ITEM_CATALOG[r['content_id']].tags]
    local=[r for r in eligible if r.get('world')==world]
    candidates=local or eligible
    if not candidates:raise ValueError(f'缺少 {realm} 阶遗宝定标物品')
    return max((ITEM_CATALOG[r['content_id']] for r in candidates),key=lambda i:(i.combat_bonus,i.id))


def restorative_description(item):
    item['description']=(f"消耗一份恢复气血 {item['trial_restore_hp']:.0%}（最多 {item['recovery_hp_limit']:g}）、"
        f"法力 {item['trial_restore_mp']:.0%}（最多 {item['recovery_mp_limit']:g}），"
        f"获得 {item['opportunity_bonus']:g} 机缘。")


def bounded_recipe(reward,quality='ordinary',world=None):
    """New blueprints only: single resonating relic and consumable restorative loot."""
    if reward['kind']=='artifact':
        item=reward['item'];item['tags'].append('dungeon_relic')
        item['description']+=' 同类遗宝由战力最高的一件共鸣生效。'
    elif reward['kind']=='pill':
        item=reward['item'];amount=item.pop('permanent_intrinsic_hp_bonus')
        factor=amount/max(.001,expected_combat_power(reward['realm'],9)*.02)
        hp=max((i.trial_restore_hp for i in ITEM_CATALOG.values()),default=.25) if quality=='legendary' else .25
        mp=max((i.trial_restore_mp for i in ITEM_CATALOG.values()),default=.25) if quality=='legendary' else .25
        hp=min(1,hp*factor);mp=min(1,mp*factor)
        item.update(hp_bonus=0,mp_bonus=0,trial_restore_hp=hp,trial_restore_mp=mp,
            opportunity_bonus=round(REALMS[reward['realm']].opportunity_base*(1 if quality=='legendary' else .5)*factor,2))
        definition=REALMS[reward['realm']];anchor=equipment_anchor(reward['realm'],world)
        # Freeze a same-grade untrained body plus its actual equipment budget.
        item['recovery_hp_limit']=round((100+int(definition.base_power**.5*16)+definition.layers*8+anchor.hp_bonus)*hp,2)
        item['recovery_mp_limit']=round((40+int(definition.base_power**.5*20)+definition.layers*11+anchor.mp_bonus)*mp,2)
        item['tags'].append('dungeon_restorative')
        restorative_description(item)


def bound_growth_budget(site):
    """All ordinary/rare/epic medicines share one finite blueprint budget."""
    if site['quality']=='legendary':return
    rewards=[n['reward'] for n in site['nodes']]+site['expedition']['bonuses']
    items=[r['item'] for r in rewards if r['kind']=='pill']
    total=sum(i['opportunity_bonus'] for i in items)
    if total<=0:return
    unit=WORLD_SYSTEMS['time_units'][str(site['realm'])]
    budget=sum(ACTIONS['cultivate']['opportunity'])/2*unit*WORLD_SYSTEMS['seeded_dungeons']['growth_action_units'][site['quality']]
    remaining=round(budget,2)
    for index,item in enumerate(items):
        amount=remaining if index==len(items)-1 else min(remaining,round(budget*item['opportunity_bonus']/total,2))
        item['opportunity_bonus']=amount;remaining=round(remaining-amount,2)
        restorative_description(item)


def resource_recipe(rng,identity,realm,world,path,quality):
    """Finite original cultivation materials, selected by their actual use grade."""
    choices=[r for r in WORLD_SYSTEMS['natal_artifact']['materials']
        if r.get('world')==world and r.get('minimum_realm',99)<=realm and r['item_id'].startswith('natal_') and r['item_id'] in ITEM_CATALOG]
    if quality=='legendary':choices=[r for r in choices if r.get('minimum_realm')==realm]
    from ...universal_manuals import identity as jade_identity
    jade = dict(id=jade_identity(path,realm), quantity={'ordinary':2,'rare':4,'epic':6,'legendary':9}[quality])
    items=[jade]
    highest=max((r['minimum_realm'] for r in choices), default=realm)
    choices=[r for r in choices if r['minimum_realm']==highest]
    if choices:items.append(dict(id=rng.choice(choices)['item_id'],quantity=1))
    if realm>=9 and path=='dao':items.append(dict(id='immortal_trace',quantity=rng.randint(40,60)*(realm-8)))
    return dict(id=identity,kind='resource',name='、'.join(ITEM_CATALOG[r['id']].name for r in items),
        realm=realm,fused=False,items=items)


def recipe(rng, identity, realm, path, theme, quality, core=False,world=None):
    """Legendary is benchmarked against top-grade finished goods, never player rank."""
    fused = quality == 'legendary' and core and rng.random() < WORLD_SYSTEMS['seeded_dungeons']['legendary_fusion_chance']
    family = 'technique' if fused or core else rng.choice(('artifact','pill','technique'))
    candidates = [t for t in TECHNIQUE_CATALOG.values() if t.grade == realm and t.path == path and t.category == 'spiritual'
                  and t.requires_immortal_power==(realm>=9 and path=='dao')]
    # Some paths have no authored book at their world's final grade. Borrow
    # same-grade numeric budgets only; generated sources and legal costs keep
    # the recipient path. HP/MP bonuses are ratios, never combat-power amounts.
    if not candidates:
        candidates=[t for t in TECHNIQUE_CATALOG.values() if t.grade==realm and t.path=='dao'
                    and t.category=='spiritual' and t.requires_immortal_power==(realm>=9)]
    if not candidates:raise ValueError(f'缺少 {realm} 阶传承定标功法')
    base = max(float(t.combat_bonus) for t in candidates)
    factor = rng.uniform(1.,1.1) if quality=='legendary' else rng.uniform(.8,1.05)*{'ordinary':.8,'rare':1.,'epic':1.2}[quality]
    name = rng.choice(('太微','玄照','归藏','承露','洞明','照夜','九霄','清寂','望舒','步虚','含章','抱元','明夷','问道','鸣霄','衍星','怀璧','凌霜','息尘','照微','流霞','凝真','枕月','观澜')+tuple(EXTRA_NAMES)) + THEMES[theme]
    if family == 'technique':
        key = identity + (':concordance' if fused else ':manual:1')
        effect = generate_effect(rng.randrange(2**32),identity,identity+':manual:1',feature='frugal',preference='main',theme=THEMES[theme])
        if fused:
            effect = concordance_effect([dict(growth_preference='main',combat_effect=effect)],
                seed=rng.randrange(2**32),doctrine_id=identity,feature='frugal',theme=THEMES[theme])
        source = {'demonic':'demon','ghost':'yin','monster':'monster'}.get(path,'spirit')
        if realm < 9:
            templates=[t.combat_effect for t in candidates if t.category=='spiritual' and t.combat_effect
                and t.combat_effect.get('version')==3 and not t.combat_effect.get('prestige')]
            if templates:
                effect=copy.deepcopy(rng.choice(templates))
                effect.update(identity=key,prestige=False,resource='mana')
                effect.pop('mana_cost',None)
                effect['strength_bp']=min(1000,max(1,round(effect['strength_bp']*rng.uniform(.9,1.1))))
            else:
                effect=dict(version=3,generator_version=3,identity=key,trigger='paid_preparation',
                    covenant='confirm_later',delivery='next_window',payload='finite_shield',clauses=[],clause='',
                    cost_bp=200,strength_bp=rng.randint(80,120),ward_bp=100,cooldown=1,uses=3,duration=2,
                    resource='mana',category='spiritual',signature='0'*64,prestige=False)
            if fused:effect['cost_bp']=max(100,effect['cost_bp']*4//5)
            effect['signature']=hashlib.sha256(json.dumps(effect,sort_keys=True).encode()).hexdigest()
        effect = validate_effect(effect)
        amount = base * factor
        hp = max(float(t.hp_bonus) for t in candidates)
        mp = max(float(t.mp_bonus) for t in candidates)
        opportunity = max(float(t.opportunity_bonus) for t in candidates)
        book = dict(id=key,name=name+(rng.choice(('归一真典','合元宝录','一炁真解','圆融道藏')) if fused else rng.choice(('秘经','真解','心诀','道书','玄章','宝录','灵枢篇','玉箓'))),path=path,grade=realm,level=1,
                    element='neutral',growth_preference='balanced',force_tier=2 if realm>=9 else 1,
                    combat_bonus=round(amount,3),hp_bonus=round(hp*factor,3),
                    mp_bonus=round(mp*factor,3),opportunity_bonus=round(opportunity*factor,3),
                    requires_immortal_power=realm>=9 and path=='dao',
                    immortal_power_cost=max((t.immortal_power_cost for t in candidates),default=.08) if realm>=9 and path=='dao' else 0,
                    sources={source:1.},combat_effect=effect,
                    description=('前人合练完成的完整真传，可直接研习。' if fused else '秘境中保存的完整修习之法。')+describe(effect))
        return dict(id=identity,kind=family,name=book['name'],realm=realm,fused=fused,book=book)
    anchor=equipment_anchor(realm,world)
    power = round(anchor.combat_bonus*factor,3)
    form=rng.choice(tuple(RELIC_FORMS) if family=='artifact' else ('回元露','凝神液','养灵丹','玉髓散','归真丸','蕴华膏'))
    item = dict(id=identity,name=name+form,
                force_tier=2 if realm>=9 else 1,description='古修留下的护道之物。' if family=='artifact' else '消耗一份固本培元；药力由遗境品阶确定。',
                tags=['equipment',f'grade:{realm}'] if family=='artifact' else ['pill',f'grade:{realm}'])
    if family=='artifact':
        item.update(combat_bonus=power,hp_bonus=round(anchor.hp_bonus*factor),mp_bonus=round(anchor.mp_bonus*factor))
        item['description']=RELIC_FORMS[form]+f"战力 +{power:g}，气血 +{item['hp_bonus']:g}，法力 +{item['mp_bonus']:g}。"
    else:
        item.update(permanent_intrinsic_hp_bonus=round(expected_combat_power(realm,9)*.02*factor,3))
        item['description']=f"服用后本体气血永久 +{item['permanent_intrinsic_hp_bonus']:g}；药力由遗境品阶确定。"
    return dict(id=identity,kind=family,name=item['name'],realm=realm,fused=False,item=item)


def grant(game, reward):
    if reward['kind']=='resource':
        if any(row['id'] not in ITEM_CATALOG for row in reward['items']):raise ValueError('原资源定义已不可用，保留未领取回执')
        for row in reward['items']:add_item(game.player,row['id'],row['quantity'])
    elif reward['kind']=='technique':
        book=Technique(**reward['book'])
        state=game.dungeon_state
        if book.id in state['manuals']:
            return '这部传承已收录，没有重复获得成长。'
        # Keep the original frozen book until lawful study; do not mark it learned.
        state['manuals'][book.id]=dict(book=copy.deepcopy(reward['book']),fused=reward['fused'],
            acquired=True,learned=False,level=1,study=None)
        add_item(game.player,Item(id='MANUAL_DUNGEON_'+book.id,name='《'+book.name+'》传承',
            description='从探幽寻宝的传承页研习；原配方与品阶已确定。',
            force_tier=book.force_tier,tags=['dungeon_manual']))
    else:
        add_item(game.player,Item(**reward['item']))
    return '获得'+reward['name']+'。'


def learning_reason(game, row):
    if not row or row['learned']:return '传承已学习，收录于已悟功法'
    book=Technique(**row['book'])
    from ...rules import can_player_practice_technique
    if game.player.realm_index<book.grade or not can_player_practice_technique(game.player,book):
        return '研习须达到此传承的修为、道途与灵根要求'
    if book.grade>=9 and not game.player.immortal_power_converted and game.player.path=='dao':
        return '请先完成仙灵力转化'
    if not any(i.id=='MANUAL_DUNGEON_'+book.id and i.quantity>0 for i in game.player.inventory):
        return '研习须持有传承原件'
    return ''


def learn(game, identity):
    row=game.dungeon_state.get('manuals',{}).get(identity)
    if reason:=learning_reason(game,row):raise ValueError(reason)
    book=Technique(**row['book'])
    from ...rules import remove_item
    if not remove_item(game.player,'MANUAL_DUNGEON_'+book.id):raise ValueError('传承原件已不在行囊')
    learn_technique(game.player,book)
    row['learned']=True
    return '已学会《'+book.name+'》Lv1。'
