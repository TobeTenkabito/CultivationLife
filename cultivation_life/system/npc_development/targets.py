"""Resolve existing owners and reject unsafe access before computing a quote."""
from dataclasses import dataclass
from ...relationship_records import find_person
from ...spatial_people import accessible
from ...person_assignments import research_assignment
from ...puppet_state import usable, training_facts
from ..combat.actor_state import read, _write
from ..cultivation_guard import cultivation_blocked
from ...cultivation_coordinates import rank_for
from ..spatial_capabilities import site_key


def unrevealed(game,target):
    person=target.person if target.person is not None else target.owner
    return bool(target.kind=='npc' and read(person,'concealed_realm_index') is not None
                and game.player.divine_sense_rank<rank_for(read(person,'realm_index',0),read(person,'layer',1)))

def location(game,target):
    """Use the existing contact address without writing or relocating the person."""
    if target.person is None:
        return read(target.owner,'location_id')
    from ..faction_geography import person_site
    return person_site(game,target.person)

@dataclass
class Target:
    kind: str
    identity: str
    owner: object
    person: object
    relations: tuple
    bonus_owner: object = None

    def facts(self,game):
        if self.kind=='puppet':
            row=training_facts(game,self.owner)
            if self.person and self.owner.get('type')=='living':
                for key in ('race','gender','path','spirit_root','spirit_state','transcendence'):
                    row.setdefault(key,read(self.person,key))
            return row
        if self.kind=='prisoner':
            return {**dict(self.owner),**self.person.to_dict()}
        facts = self.owner.to_dict() if hasattr(self.owner,'to_dict') else dict(self.owner)
        if self.bonus_owner is not None:
            facts['breakthrough_bonus'] = self.bonus_owner.get('breakthrough_bonus', 0)
        return facts

def candidates(game):
    p=game.player;rows={}
    for label,entries in [('弟子',p.disciples),('后代',p.offspring),
                          ('道侣',[p.dao_companion] if p.dao_companion else [])]:
        for row in entries:
            identity=str(row.get('npc_id') or row.get('id',''))
            person=find_person(game,identity,include_inactive=True)
            if person:
                key=('npc',identity)
                labels=rows[key].relations+(label,) if key in rows else (label,)
                bonus = row if label == '弟子' else rows[key].bonus_owner if key in rows else None
                rows[key]=Target('npc',identity,person,person,labels,bonus)
            elif label=='后代':
                rows[('npc',identity)]=Target('npc',identity,row,None,(label,))
    if game.family:
        for person in game.family.npcs:
            if person.family_traits.get('kin'):
                rows.setdefault(('npc',person.id),Target('npc',person.id,person,person,('族人',)))
    for row in p.prisoners:
        identity=str(row.get('npc_id') or row.get('id',''))
        person=find_person(game,identity,include_inactive=True)
        if person:
            previous=rows.pop(('npc',identity),None)
            labels=previous.relations+('俘虏',) if previous else ('俘虏',)
            rows[('prisoner',identity)]=Target('prisoner',identity,row,person,labels)
    for row in p.puppets:
        identity=str(row.get('id',''));source=row.get('source_npc_id')
        person=find_person(game,source,include_inactive=True) if source else None
        if person:
            rows.pop(('npc',person.id),None);rows.pop(('prisoner',person.id),None)
        rows[('puppet',identity)]=Target('puppet',identity,row,person,('御傀',))
    from ..mentorship_avatar import avatar_person
    avatar = avatar_person(game)
    if avatar:
        rows[('npc',avatar.id)] = Target('npc',avatar.id,avatar,avatar,('身外化身',))
    return list(rows.values())

def resolve(game,kind,identity):
    if not isinstance(identity,str) or not identity or not isinstance(kind,str) or kind not in {'npc','prisoner','puppet'}:
        raise ValueError('培养对象类型或编号无效')
    found=next((r for r in candidates(game) if r.kind==kind and r.identity==identity),None)
    if not found:raise ValueError('培养对象不存在或已失去培养关系')
    return found

def require(game,target,axis=None):
    p=game.player;n=target.person;o=target.owner
    from ...npc_development_content import TIERS
    if p.world not in TIERS and p.world not in {'lost', 'rift'}:
        raise ValueError('未知界面不能进行人物培养')
    if not target.identity:raise ValueError('该对象缺少有效身份编号')
    if cultivation_blocked(game) or p.sealed_cultivation or p.cultivation_suppression:
        raise ValueError('当前状态无法培养，请先处理事件、劫战或身体限制')
    if game.map_journey or game.guixu_state.get('player_session'):
        raise ValueError('请先结束行旅或离开归墟，再当面培养')
    if game.heavens_state.get('runtime'):
        from ..heavens.state import active_task
        if active_task(game.heavens_state['runtime']):raise ValueError('请先结束诸天亲自任务')
    if n and (n.custody or {}).get('kind')=='second_nascent':raise ValueError('第二元婴须由专属身魂系统培养')
    if n and not n.alive and not (target.kind=='puppet' and o.get('type')=='corpse'):
        raise ValueError('该活傀原人物已陨落，躯体已经毁坏' if target.kind=='puppet' else '该人物已陨落')
    if target.kind=='puppet':
        if not usable(o,game):raise ValueError('该傀儡已经毁坏或陨落')
        if o.get('type')=='living' and o.get('source_npc_id') and (n is None or (n.custody or {}).get('kind')!='living_puppet'
                  or (n.custody or {}).get('holder_id')!=game.id):
            raise ValueError('活傀控制关系已失效')
    else:
        person=n if n is not None else o
        if not read(person,'alive',True):raise ValueError('人物已不可用')
        if read(person,'age',0)<16:raise ValueError('须满16岁才能接受培养')
        if target.kind=='npc':
            if '身外化身' in target.relations:
                from ..mentorship_avatar import avatar_person, avatar_reason
                reason = avatar_reason(game, command=True)
                if avatar_person(game) is not n or reason: raise ValueError(reason or '化身控制关系失效')
            else:
                if read(person,'roster_state','active')!='active' or read(person,'custody'):raise ValueError('受控或离册人物不能接受自由培养')
                if not accessible(game,person):raise ValueError('当前无法接触该人物')
                address=location(game,target)
                if not address or address!=site_key(game):
                    raise ValueError('须确认人物与你在同一实际地点')
        elif not n.custody or n.custody.get('kind')!='prisoner' or n.custody.get('holder_id')!=game.id:
            raise ValueError('俘虏控制关系已失效')
    identity=n.id if n else target.identity
    if research_assignment(game,identity) or identity in game.intrigue_state.get('npc_prisons',{}):
        raise ValueError('该人物已被任务或监禁占用')
    if unrevealed(game,target):raise ValueError('当前神识尚未探明人物的真实修为')
    if axis=='body' or (isinstance(axis,str) and axis.startswith('body_art:')):
        from ..combat.actor_state import has_body
        if not has_body(target.facts(game)):raise ValueError('当前没有可培养的实际肉身')
    if axis=='cultivation':
        spirit=read(o,'spirit_state',{}) or {}
        if spirit.get('stagnant') or spirit.get('cultivation_stagnant'):
            raise ValueError('修为永久停滞，无法培养修为')

def write(target,result):
    fields=('realm_index','layer','cultivation_progress','body_training','immortal_body_level',
            'divine_sense_rank','lifespan','breakthrough_bonus','transcendence','body_attainments','technique_levels','main_technique_level','family_traits','family_combat_bonus')
    for key in fields:
        if key == 'breakthrough_bonus' and target.bonus_owner is not None:
            if key in result: target.bonus_owner[key] = result[key]
            continue
        owner=target.person if target.kind=='prisoner' and key!='breakthrough_bonus' else target.owner
        if key in result and (isinstance(owner,dict) or hasattr(owner,key)):
            _write(owner,key,result[key])
    if target.kind in {'puppet','prisoner'}:
        for key in ('combat_power','technique_power_base','technique_power_scale','realm_name'):
            if key in result:target.owner[key]=result[key]
    if target.kind=='puppet' and 'age' in result:target.owner['age']=result['age']
