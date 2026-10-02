"""Authoritative assembly quotes and the dedicated puppet materials shelf."""
import copy
import math
from ..puppet_content import FORMS, definitions
from ..rules import expected_combat_power, puppet_capacity
from .cultivation_ranks import rank_for, describe, body_rank


def inventory(player):
    defs=definitions()
    return [dict(defs[item.id],quantity=item.quantity) for item in player.inventory
            if item.id in defs and item.quantity>0]


def preview(player, form, core, shell, energy):
    if form not in FORMS:
        raise ValueError('请选择有效傀儡形态')
    available={r['id']:r for r in inventory(player)}
    selected=[]
    for slot,id_ in [('core',core),('shell',shell),('energy',energy)]:
        row=available.get(id_)
        if not row or row['slot']!=slot:
            raise ValueError('缺少对应核心、外材或能源，或材料类别不符')
        selected.append(row)
    c,s,e=selected
    if s['form']!=form:
        raise ValueError('傀儡外材与所选形态不符')
    # Each component owns one independent coordinate. All three contribute to power.
    realm,layer=e['tier'],3
    normal=min(100,rank_for(s['tier'],3))
    higher=5+(s['tier']-9)*20 if s['tier']>=9 else 0
    sense=rank_for(c['tier'],3)
    powers=[expected_combat_power(r['tier'],3)*r['quality'] for r in (c,s,e)]
    power=round(math.exp(sum(w*math.log(max(1,p)) for w,p in zip((.2,.4,.4),powers))),1)
    return dict(form=form,form_name=FORMS[form]['name'],name=FORMS[form]['name']+'机关傀儡',
                realm_index=realm,layer=layer,body_training=normal,immortal_body_level=higher,
                divine_sense_rank=sense,combat_power=power,original_power=power,
                cultivation_name=describe(rank_for(realm,layer))['name'],
                body_name=describe(body_rank(normal,higher))['name'],sense_name=describe(sense)['name'],
                components=[{k:v for k,v in row.items() if k!='quantity'} for row in selected],
                can_craft=player.alive and len(player.puppets)<puppet_capacity(player),
                reason='' if len(player.puppets)<puppet_capacity(player) else '神识可控傀儡数量已达上限')


def public(player):
    return dict(forms=[dict(id=k,**v) for k,v in FORMS.items()], materials=inventory(player),
                description='核心决定神识，外材决定炼体与形态，能源决定修为；三者共同决定总战力。各消耗一份，支持跨阶搭配。')


def market_offers(game,tier,market_name,location_id):
    p=game.player
    previous=[copy.deepcopy(r) for r in game.market_offers if r.get('kind')=='puppet_material'
              and r.get('locked') and not r.get('sold') and r.get('world')==p.world
              and r.get('location_id')==location_id][:1]
    held={r['content_id'] for r in previous}
    for r in definitions().values():
        if r['world']!=p.world or r['tier']!=tier or r['id'] in held:
            continue
        previous.append(dict(id=f"puppet-shop-{location_id}-{p.age}-{r['id']}",kind='puppet_material',
            content_id=r['id'],name=r['name'],description=r['description'],price=r['price'],tier=tier,
            tier_name=f'{tier}阶',world=p.world,location_id=location_id,market_name=market_name,
            sold=False,locked=False,rare_next_tier=False,component_slot=r['slot'],form=r['form']))
    return previous
