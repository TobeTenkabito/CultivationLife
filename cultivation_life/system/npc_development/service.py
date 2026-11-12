"""Pure quotes and explicit writes to existing NPC/asset authorities."""
import copy
from ...content_registry import REALMS, WORLD_SYSTEMS, ROOT_DEFINITIONS, ITEM_CATALOG
from ...npc_development_content import allowed, TIERS, SENSE_LIMITS
from ...rules import can_practice_technique, remove_item
from ...npc_custody import sync_offspring
from ...models import HistoryRecord
from ..combat.actor_state import read, _write
from .targets import resolve, require, write
from .growth import quote as owned_quote, facts as normalize_facts
from .upper import require_upper, grow_ledger, conversion_plan

def quote(game,kind,identity,axis,method='infuse',batches=1,*,_target=None,stock=None):
    inherited = method in ('inherit_infuse', 'inherit_material')
    requested_method = method
    if inherited:
        from ..mentorship_advanced import precision
        if kind != 'npc' or not precision(game, identity): raise ValueError('传承精修只对有本周期额度的亲传、嫡传开放')
        method = method.removeprefix('inherit_')
    target=_target if _target is not None else resolve(game,kind,identity)
    require(game,target,axis)
    specialized=isinstance(axis,str) and axis.startswith('body_art:')
    technique=isinstance(axis,str) and axis.startswith('technique:')
    domain=isinstance(axis,str) and (axis=='domain' or axis.startswith('domain:'))
    if (axis not in ('cultivation','body','sense','conversion') and not specialized and not domain and not technique) or method not in ('infuse','material','family'):
        raise ValueError('培养方向或方式尚未开放')
    if type(batches) is not int or batches not in (1,5,10):raise ValueError('培养轮数须为1、5、10')
    facts=normalize_facts(target.facts(game));p=game.player;r=int(facts.get('realm_index',0));layer=int(facts.get('layer',1))
    if not 1<=r<len(REALMS):raise ValueError('该人物尚未踏入可培养的修行阶段')
    tier=TIERS.get(p.world,0)
    if not tier:raise ValueError('当前空间未开放NPC主动培养')
    cap={1:5,2:8,3:12}[tier]
    if r>cap:raise ValueError('当前界面无法承载目标真实修为')
    upper_growth=axis=='cultivation' and (r>=9 or r==8 and layer>=REALMS[8].layers and tier==3)
    if upper_growth or axis=='conversion':require_upper(game,target,facts)
    path=facts.get('path')
    if axis=='cultivation' and kind!='puppet' and facts.get('spirit_root')=='none':raise ValueError('目标没有可承接修为培养的灵根')
    if axis=='body' and method!='material':
        from ..combat.actor_state import has_body
        if not has_body(p):raise ValueError('神游期间不能以原肉身传授炼体')
    teacher=copy.copy(p)
    if method=='family':
        if axis!='cultivation' or batches!=1 or not set(target.relations)&{'后代','族人'}:
            raise ValueError('家族灌顶只适用于本家后代修为')
        limit=1+tier+int(ROOT_DEFINITIONS.get(facts.get('spirit_root'),{}).get('tier')=='天灵根')
        if facts.get('spirit_root')=='none' or (r,layer)>=(limit,REALMS[limit].layers):
            raise ValueError('已达到家族灌顶上限或没有灵根')
        if (r,layer)>=(p.realm_index,p.layer):raise ValueError('灌顶者修为须严格高于后代')
        teacher.realm_index=r;teacher.layer=layer+1
        if teacher.layer>REALMS[r].layers:teacher.realm_index=r+1;teacher.layer=1
    if method=='material':
        if kind!='puppet' and path not in ('dao','demonic','monster','ghost'):raise ValueError('该道途专材尚未开放')
        teacher.realm_index=cap;teacher.layer=REALMS[cap].layers
        teacher.body_training=100
        teacher.divine_sense_rank=SENSE_LIMITS[-1]
        teacher.immortal_body=copy.deepcopy(teacher.immortal_body)
        teacher.immortal_body['level']=50
    if axis=='body' and int(facts.get('body_training') or 0)>=100:
        require_upper(game,target,facts)
        if r<9:raise ValueError('须先达到上境修为才能培养高阶肉身')
    # Stop before a boundary requiring a world transition, tribulation or new route.
    if axis=='cultivation':
        if p.world=='human' and r==5 and layer>=3:
            raise ValueError('已到人界飞升关口，须沿原人物跨界规则离开')
        growth_cap=cap if upper_growth else min(cap,8)
        if layer>=REALMS[r].layers and (r>=growth_cap or p.world=='human' and r==4):
            raise ValueError('已到跨境关口，须由原突破／跨界规则处理')
        boundary=4 if p.world=='human' and r<5 else growth_cap
        if teacher.realm_index>boundary:
            teacher.realm_index=boundary;teacher.layer=REALMS[boundary].layers
        if method=='family' and layer==REALMS[r].layers and r<4:
            teacher.realm_index=r+1;teacher.layer=1
        if p.world=='human' and r==5 and teacher.realm_index==5:
            teacher.layer=min(teacher.layer,3)
    teacher.body_training=min(teacher.body_training,{1:60,2:100,3:100}[tier])
    teacher.divine_sense_rank=min(teacher.divine_sense_rank,SENSE_LIMITS[tier-1])
    if axis=='body' and method!='material':
        from ..possession_system import is_possessed
        from ..monster_body import enabled_for as monster_enabled,active_level
        from ..wuyun import enabled_for as wuyun_enabled
        high=(int(p.ghost_host_body.get('immortal_body_level') or 0) if is_possessed(p) else
              active_level(p,player=True) if monster_enabled(p) else
              int(p.asura_cultivation.get('body_level',0)) if wuyun_enabled(p) else int(p.immortal_body.get('level',0)))
        teacher.immortal_body={**p.immortal_body,'level':high}
        teacher.asura_cultivation={**p.asura_cultivation,'body_level':high}
    if axis=='body' and facts['body_training']<100:
        # Reaching 100 in a batch cannot bootstrap a new high-body qualification.
        teacher.immortal_body={**teacher.immortal_body,'level':0}
        teacher.asura_cultivation={**teacher.asura_cultivation,'body_level':0}
    if axis=='body' and int(facts.get('body_training') or 0)>=100 and tier<3:
        raise ValueError('高阶肉身须在对应上界培养')
    if axis=='body' and int(facts.get('body_training') or 0)>=100:
        require_upper(game,target,facts)
    # A batch stops at its material stage; it never pays a lower recipe for the next.
    next_realm=r+1 if layer>=REALMS[r].layers else r
    if method=='material':
        if axis=='cultivation' and next_realm<=4 and teacher.realm_index>4:
            teacher.realm_index=4;teacher.layer=REALMS[4].layers
        if axis=='body' and int(facts.get('body_training') or 0)<60:teacher.body_training=min(teacher.body_training,60)
        if axis=='sense':
            rank=int(facts.get('divine_sense_rank') or 0)
            teacher.divine_sense_rank=min(teacher.divine_sense_rank,next((limit for limit in SENSE_LIMITS if rank<limit),SENSE_LIMITS[-1]))
    teacher.opportunity=10**30;teacher.mp=10**30
    from .domains import plan as domain_plan
    from .body import plan as body_plan
    from .techniques import plan as technique_plan
    plan=(technique_plan(game,target,facts,axis,batches,method) if technique else body_plan(game,target,facts,axis,batches,method) if specialized else domain_plan(game,target,facts,batches,method,axis) if domain else conversion_plan(game,target,facts,batches) if axis=='conversion' else
          owned_quote(teacher,facts,axis,batches,legacy_costs=False,upper_simplified=upper_growth))
    if not plan['rounds']:
        raise ValueError('已达当前界面或阶段的培养上限' if method=='material' else plan['reason'])
    if upper_growth:
        grow_ledger(game,target,facts,plan['result'])
    # Use the target axis, including every actually completed step in the batch.
    from .costs import reference_cost
    reference=plan['specialized_reference'] if specialized or technique else plan['domain_reference'] if domain else reference_cost(facts,plan['result'],axis)
    # Each axis prices its own growth coordinates, never the teacher's rank.
    discount=1-min(.35,max(0.,float(facts.get('breakthrough_bonus',0))))
    cost=round(reference*.015*discount,2)
    plan.update(method=method,kind=kind,target_id=identity,mp=0.,opportunity=cost,
                reference_units=round(reference,2),reference_version=1,material_id=None,material_count=0,
                revision=game.updated_at,can_train=True,reason='')
    if kind=='npc':
        # Free people use the real combat builder after settlement, not an asset multiplier.
        plan.pop('power_before',None);plan.pop('power_after',None)
    if method=='material':
        if axis=='conversion' or domain or specialized:stage=3
        elif technique:stage=1 if r<=4 else 2 if r<=8 else 3
        elif axis=='body':stage=1 if int(facts.get('body_training') or 0)<60 else 2 if int(facts.get('body_training') or 0)<100 else 3
        elif axis=='sense':stage=1 if facts['divine_sense_rank']<SENSE_LIMITS[0] else 2 if facts['divine_sense_rank']<SENSE_LIMITS[1] else 3
        else:stage=1 if next_realm<=4 else 2 if next_realm<=8 else 3
        material_axis='technique' if technique else 'body_art' if specialized else 'domain' if domain else axis
        material=f'npc_training_{"puppet" if kind=="puppet" else path}_{material_axis}_{stage}'
        if not allowed(material,p.world):raise ValueError('当前界面不允许使用该品阶／道途专材')
        plan.update(opportunity=0.,material_id=material,material_count=plan['rounds'])
        plan['result']['breakthrough_bonus']=facts.get('breakthrough_bonus',0)
        held=sum(i.quantity for i in p.inventory if i.id==material) if stock is None else stock.get(material,0)
        plan.update(material_name=ITEM_CATALOG[material].name,material_owned=held)
        if held<plan['material_count']:plan.update(can_train=False,reason='NPC专材不足，可从坊市、交易或探宝取得')
    elif p.opportunity<cost:plan.update(can_train=False,reason='机缘不足')
    if inherited:
        import math
        plan.update(method=requested_method, inheritance=True, can_train=True, reason='')
        if plan['material_id']:
            plan['material_count'] = math.ceil(plan['material_count'] / 2)
            if plan['material_owned'] < plan['material_count']: plan.update(can_train=False, reason='NPC专材不足')
        else:
            plan['opportunity'] = round(plan['opportunity'] * .5, 2)
            if p.opportunity < plan['opportunity']: plan.update(can_train=False, reason='机缘不足')
    return plan

def apply(game,kind,identity,axis,method='infuse',batches=1,*,_target=None,stock=None):
    plan=quote(game,kind,identity,axis,method,batches,_target=_target,stock=stock)
    if not plan['can_train']:raise ValueError(plan['reason'])
    target=_target if _target is not None else resolve(game,kind,identity)
    if plan['material_id']:
        if stock is None:
            if not remove_item(game.player,plan['material_id'],plan['material_count']):raise ValueError('NPC专材不足')
        else:
            key=plan['material_id'];stock[key]-=plan['material_count']
            if not stock[key]:stock.pop(key)
    game.player.opportunity-=plan['opportunity']
    write(target,plan['result'])
    if plan.get('inheritance'):
        from ..mentorship_advanced import spend_precision
        spend_precision(game, identity)
    from ..mentorship import benefit
    benefit(game, identity, 'train:' + axis, min(6, plan['rounds'] * 2))
    if target.person and kind!='puppet':sync_offspring(game,target.person)
    summary=f"为{read(target.owner,'name','人物')}{plan['label']}：{plan['before']} → {plan['after']}。"
    summary+=(f"消耗{plan['material_name']}×{plan['material_count']}；未消耗玩家机缘。" if plan['material_id'] else f"机缘 -{plan['opportunity']:g}。")
    game.history.append(HistoryRecord('SYS_NPC_DEVELOPMENT',1,game.player.age,'NPC培养',axis,'trained',summary,
        {'target_id':identity,'kind':kind,'method':method,'rounds':plan['rounds']},['system','training']))
    return summary


def charge(game,kind,identity,source=None):
    target=resolve(game,kind,identity);require(game,target)
    if kind!='puppet':raise ValueError('只有傀儡需要补充储能')
    from ..puppet_energy import charge_quote,replace
    if source is None:
        plan=charge_quote(game,target.owner)
        if not plan['can_charge']:raise ValueError(plan['reason'])
        source='bag:'+plan['material_id']
    if not isinstance(source,str):raise ValueError('能源选择无效')
    summary=replace(game,target.owner,source)
    game.history.append(HistoryRecord('SYS_PUPPET_CHARGE',1,game.player.age,'傀儡充能',None,'charged',summary,
        {'target_id':identity},['system','training','puppet']))
    return summary

def teach(game,kind,identity,book_id,*,slot=None,family=False):
    if slot not in (None,'main','body','sense','support','combat','transformation'):
        raise ValueError('功法配置栏目无效')
    target=resolve(game,kind,identity);require(game,target)
    family=family or bool(set(target.relations)&{'后代','族人'})
    book=next((t for t in game.player.known_techniques if t.id==book_id),None)
    if not book:raise ValueError('只能传授自己已掌握的功法')
    facts=normalize_facts(target.facts(game))
    if kind=='puppet' and facts.get('type')!='living':raise ValueError('只有活傀能学习人物功法')
    root=facts.get('spirit_root')
    if root not in ROOT_DEFINITIONS or not can_practice_technique(root,book):raise ValueError('目标灵根未确认或无法修习此功法')
    if book.required_body_training>int(facts.get('body_training') or 0):raise ValueError('目标炼体尚未达到功法要求')
    if book.requires_immortal_power and (facts.get('transcendence') or {}).get('conversion', 0) < 1:
        raise ValueError('目标尚未完成仙灵力转化')
    from ..npc_techniques import learn,levels
    owner=target.person if kind=='prisoner' else target.owner
    if book_id in levels(owner) and (slot is None or (slot=='main' and read(owner,'main_technique_id')==book_id) or read(owner,'technique_slots',{}).get(slot)==book_id):raise ValueError('该人物已掌握并配置此功法')
    newly_learned = book_id not in levels(owner)
    expected={'spiritual':'main','body':'body','divine_sense':'sense','transformation':'transformation','combat':'combat','support':'support'}.get(book.category)
    if slot is not None and slot!=expected and not (slot == 'combat' and book.category == 'spiritual'):
        raise ValueError('功法类别与配置栏目不符')
    if slot == 'combat' and book.grade > facts['realm_index']:
        raise ValueError('目标境界不足以配置此斗法功法')
    if kind=='puppet':
        from ...content_registry import TECHNIQUE_CATALOG
        o=target.owner
        if book.category!='spiritual':raise ValueError('活傀当前只支持主修功法')
        previous=TECHNIQUE_CATALOG.get(o.get('main_technique_id'))
        base=o.get('technique_power_base',max(1.,o.get('combat_power',1)-(previous.combat_bonus*.1 if previous else 0)))
        scale=o.get('technique_power_scale',1.)
        o.update(main_technique_id=book.id,main_technique_level=1,technique_power_base=base,technique_power_scale=scale,
                 combat_power=round(base+book.combat_bonus*.1*scale,1))
    else:
        learn(owner,book,slot=slot if family else slot or expected)
        if family:
            traits=read(owner,'family_traits',{})
            learned=traits.setdefault('techniques',{})
            previous=learned.get(book.id,0);bonus=max(0.,book.combat_bonus)
            _write(owner,'family_combat_bonus',read(owner,'family_combat_bonus',0)+max(0.,bonus-previous));learned[book.id]=max(previous,bonus)
            _write(owner,'family_traits',traits)
        if target.person:sync_offspring(game,target.person)
    if newly_learned:
        from ..mentorship import benefit
        benefit(game, identity, 'teach:' + book_id, 4)
    return f"向{facts['name']}传授《{book.name}》。"

def gift(game,kind,identity,item_id,relation=None):
    target=resolve(game,kind,identity);require(game,target)
    item=ITEM_CATALOG.get(item_id)
    if not item:raise ValueError('赠予物品无效')
    recipient=relation if relation is not None else target.owner
    if not isinstance(recipient,dict):raise ValueError('该人物尚无赠予物品托管入口')
    if not remove_item(game.player,item_id):raise ValueError('物品栏中没有这件物品')
    items=recipient.setdefault('items',{});items[item_id]=int(items.get(item_id,0))+1
    if '弟子' in target.relations and 'pill' in item.tags:
        recipient['breakthrough_bonus']=min(.35,float(recipient.get('breakthrough_bonus',0))+
            float(WORLD_SYSTEMS['demonic_cultivation']['pill_breakthrough_bonus']))
    from ..mentorship import benefit
    benefit(game, identity, 'gift:' + item_id, 2)
    return item


def equip(game,identity,item_id,equipment_quote):
    target=resolve(game,'npc',identity);require(game,target)
    if not set(target.relations)&{'后代','族人'}:raise ValueError('当前赠装入口限本家成员使用')
    p=game.player;owner=target.owner
    item=next((i for i in p.inventory if i.id==item_id and i.quantity>0),None)
    quoted=equipment_quote(p,item) if item else None
    if not quoted:raise ValueError('请选择可转移装备；本命法宝及天机神兵不能直接赠与')
    if game.natal_artifact and item_id==game.natal_artifact.get('item_id'):raise ValueError('本命法宝不能赠与')
    bonus,artifact=quoted
    if artifact:
        from ..crafting_system import remove_crafted_artifact
        remove_crafted_artifact(p,artifact)
    else:remove_item(p,item_id)
    traits=read(owner,'family_traits',{})
    traits.setdefault('equipment',[]).append(dict(id=item.id,name=item.name,power=bonus,artifact=copy.deepcopy(artifact)))
    _write(owner,'family_traits',traits)
    _write(owner,'family_combat_bonus',read(owner,'family_combat_bonus',0)+bonus)
    if target.person:sync_offspring(game,target.person)
    return f"你赠予{read(owner,'name')}{item.name}，其战力增加{bonus:,.0f}。"


def feed_pill(game,identity,item_id):
    target=resolve(game,'puppet',identity);require(game,target)
    item=ITEM_CATALOG.get(item_id)
    if not item or 'pill' not in item.tags:raise ValueError('需要选择并持有一枚丹药')
    bonus=float(target.owner.get('breakthrough_bonus',0))
    if bonus>=.35:raise ValueError('丹药培养减免已达上限，无需继续消耗')
    if not remove_item(game.player,item_id):raise ValueError('需要选择并持有一枚丹药')
    gain=float(WORLD_SYSTEMS['demonic_cultivation']['pill_breakthrough_bonus'])
    target.owner['breakthrough_bonus']=min(.35,bonus+gain)
    return f"赐予{target.owner['name']}{item.name}，下次机缘培养费用减免提升至{target.owner['breakthrough_bonus']:.0%}。"
