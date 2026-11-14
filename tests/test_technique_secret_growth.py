"""Growth secrets award original progress once, without bypassing production or trials."""
import copy
import random
from dataclasses import replace

import pytest

from test_technique_secrets import base, prepare, act
from cultivation_life.cultivation_experience import body_progress_required
from cultivation_life.system.technique_secret_rules import catalog
from cultivation_life.system.technique_secrets import quote, execute
from cultivation_life.engine.composition.secret_arts import bind


@pytest.mark.parametrize('identity',['manual_earth_marrow','manual_spirit_return','manual_read_flame'])
def test_growth_is_permanent_and_never_reapplied_by_views_or_reequip(base,identity):
    e,original=base;g=prepare(e,original,identity);a=catalog()[identity]
    act(e,g,identity);g=e.store.load(g.id)
    before=(g.player.body_progress,copy.deepcopy(g.player.qi_experience),copy.deepcopy(g.player.art_experience))
    slot='technique' if a['slot']=='main' else 'support_technique'
    book=getattr(g.player,slot);setattr(g.player,slot,None);e.store.save(g)
    for _ in range(2):e.get_game(g.id)
    g=e.store.load(g.id);setattr(g.player,slot,book);e.store.save(g)
    with pytest.raises(ValueError,match='已经获得'):act(e,g,identity)
    p=e.store.load(g.id).player
    assert (p.body_progress,p.qi_experience,p.art_experience)==before


def test_body_grant_stops_at_current_layer_and_uses_original_breakthrough(base,monkeypatch):
    from cultivation_life.rules import max_hp
    e,original=base;identity='manual_earth_marrow';g=prepare(e,original,identity);p=g.player
    p.body_progress=body_progress_required(p)-7;p.awaiting_body_breakthrough=False;e.store.save(g)
    e.get_game(g.id);g=e.store.load(g.id);q=quote(g,catalog()[identity])
    assert q['growth']['gain']==7
    rank=g.player.body_training;hp=g.player.permanent_intrinsic_hp_bonus;capacity=max_hp(g.player)
    act(e,g,identity);g=e.store.load(g.id)
    assert g.player.body_training==rank and g.player.awaiting_body_breakthrough
    assert g.player.permanent_intrinsic_hp_bonus==hp
    class SuccessRandom(random.Random):
        def random(self):return 0.
    monkeypatch.setattr('cultivation_life.engine.actions.cultivation.decode_rng',lambda *a:SuccessRandom(11))
    e.body_breakthrough(g.id);g=e.store.load(g.id)
    assert g.player.body_training==rank+1 and g.player.body_progress==0
    assert max_hp(g.player)>capacity and g.player.hp==max_hp(g.player)
    with pytest.raises(ValueError):act(e,g,identity)


@pytest.mark.parametrize('change',['full','maximum','missing_book','destroyed_body'])
def test_body_unusable_conditions_do_not_pay(base,change):
    e,original=base;identity='manual_earth_marrow';g=prepare(e,original,identity);p=g.player
    token=quote(g,catalog()[identity])['token']
    if change=='full':p.body_progress=body_progress_required(p)
    elif change=='maximum':p.body_training=100
    elif change=='missing_book':p.body_technique=None
    else:p.spirit_state={'mode':'wandering','body_intact':False}
    before=copy.deepcopy(g.to_dict())
    with pytest.raises(ValueError):execute(replace(bind(e),load=lambda _:g),g.id,identity,revision=0,token=token)
    assert g.to_dict()==before


@pytest.mark.parametrize('identity',['manual_spirit_return','manual_demon_return','manual_yin_return','manual_monster_return'])
def test_qi_grants_only_the_named_pool_and_uses_real_level_curve(base,identity):
    from cultivation_life.technique_requirements import qi_levels
    e,original=base;g=prepare(e,original,identity);a=catalog()[identity]
    g.player.qi_experience={k:0. for k in ('spirit','demon','monster','yin')};e.store.save(g)
    act(e,g,identity);p=e.store.load(g.id).player
    assert p.qi_experience=={k:a['value'] if k==a['target'] else 0 for k in p.qi_experience}
    assert qi_levels(p)[a['target']]>0


@pytest.mark.parametrize('identity',['manual_read_flame','manual_hear_metal','manual_array_pivots','manual_thunder_script','manual_beast_breath'])
def test_all_five_arts_follow_existing_modifiers_without_making_products(base,identity):
    e,original=base;g=prepare(e,original,identity);a=catalog()[identity]
    g.player.sage_effects.update(field_alchemy_multiplier=.5,crafting_formation_multiplier=.2,art_experience_multiplier=.25)
    before=copy.deepcopy(g.player.art_experience)
    specialized=1.5 if a['target']=='alchemy' else 1.2 if a['target'] in {'refining','formation'} else 1.
    expected=a['value']*specialized*1.25
    # Compare to the existing ordinary producer grant, including its modifiers.
    reference=copy.deepcopy(g.player);e._grant_art_experience(reference,a['target'],a['value'])
    assert reference.art_experience[a['target']]-before[a['target']]==pytest.approx(expected)
    token=quote(g,a)['token'];saved=[]
    deps=replace(bind(e),load=lambda _:g,save=saved.append,commit=lambda _:None,present=lambda x:x)
    result=execute(deps,g.id,identity,revision=0,token=token)
    assert result.player.art_experience==reference.art_experience
    assert [i.id for i in result.player.inventory if i.id!='spirit_stone']==[]
    assert not result.player.formation_materials
    assert g.player.art_experience==before


@pytest.mark.parametrize('identity',['manual_earth_marrow','manual_spirit_return','manual_read_flame'])
def test_changed_growth_inputs_and_failed_save_are_atomic(base,identity):
    e,original=base;g=prepare(e,original,identity);a=catalog()[identity]
    old=quote(g,a)['token']
    if a['effect']=='body_progress':g.player.body_progress+=1
    elif a['effect']=='qi_experience':g.player.qi_experience[a['target']]+=1
    else:g.player.sage_effects['art_experience_multiplier']=.5
    before=copy.deepcopy(g.to_dict());deps=replace(bind(e),load=lambda _:g)
    with pytest.raises(ValueError,match='变化'):execute(deps,g.id,identity,revision=0,token=old)
    assert g.to_dict()==before
    def failed_save(_):raise OSError('disk full')
    with pytest.raises(OSError):execute(replace(deps,save=failed_save),g.id,identity,revision=0,token=quote(g,a)['token'])
    assert g.to_dict()==before


def test_content_rejects_unknown_target_or_unbounded_growth():
    from cultivation_life.content_registry import ContentRegistry, TECHNIQUE_CATALOG
    from cultivation_life.technique_secret_content import validate
    config=ContentRegistry.loaded_documents['secret_arts.json']
    for effect,key,value in [('qi_experience','target','not_a_qi'),('art_experience','target','new_skill'),('body_progress','value',2),('qi_experience','value',1e20)]:
        bad=copy.deepcopy(config);a=next(a for a in bad['technique_arts'] if a['effect']==effect);a[key]=value
        with pytest.raises(ValueError):validate(bad,TECHNIQUE_CATALOG)


def test_qi_reward_unlocks_actual_combat_equipment_requirement(base):
    from cultivation_life.content_registry import TECHNIQUE_CATALOG
    from cultivation_life.rules import learn_technique
    from cultivation_life.technique_requirements import combat_requirement_met,qi_level
    e,original=base;g=prepare(e,original,'manual_spirit_return')
    g.player.qi_experience={k:0. for k in g.player.qi_experience}
    levels=dict(g.player.qi_experience,spirit=qi_level(900))
    book=copy.deepcopy(next(t for t in TECHNIQUE_CATALOG.values() if t.path=='dao' and t.grade<=3
        and t.category=='spiritual' and not combat_requirement_met(t.combat_requirements,g.player.qi_experience)
        and combat_requirement_met(t.combat_requirements,levels)))
    learn_technique(g.player,book);e.store.save(g)
    with pytest.raises(ValueError):e.equip_known_technique(g.id,book.id,'combat')
    act(e,g,'manual_spirit_return');e.equip_known_technique(g.id,book.id,'combat')
    assert book.id in {t.id for t in e.store.load(g.id).player.combat_techniques}
