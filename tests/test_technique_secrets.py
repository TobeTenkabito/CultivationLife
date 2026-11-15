"""Actual manual slots, one-time resources, permanent receipts and frozen trials."""
import copy
import json
import random
from pathlib import Path

import pytest

from cultivation_life.content_registry import TECHNIQUE_CATALOG, MARKET_GOODS, REALMS
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item, assign_technique, learn_technique, max_hp, max_mp, divine_sense_breakthrough_cost, breakthrough_opportunity_required
from cultivation_life.secret_art_schema import decode_state
from cultivation_life.system.formation_system import formation_material_definitions, make_formation_material_instance
from cultivation_life.system.technique_secret_rules import catalog, bonus
from cultivation_life.system.technique_secrets import project, quote

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def base(tmp_path_factory):
    engine=GameEngine(ROOT,tmp_path_factory.mktemp('linked-secret'))
    g=engine.store.load(engine.create_game('功法秘术','supreme_water','dao',14731,preset_id='core')['id'])
    return engine,g


def prepare(engine, original, identity, *, resources=True):
    g=copy.deepcopy(original);p=g.player;art=catalog()[identity]
    g.pending_event=g.active_trial=None
    p.realm_index=art['realm'];p.layer=1;p.path=TECHNIQUE_CATALOG[art['technique_id']].path
    p.world=('human' if p.realm_index<=5 else {'dao':'spirit','demonic':'true_demon','ghost':'hell','monster':'monster_realm','buddhist':'spirit','confucian':'spirit'}[p.path]) if p.realm_index<9 else {'dao':'celestial','demonic':'asura','ghost':'reincarnation','monster':'nether','buddhist':'celestial','confucian':'celestial'}[p.path]
    p.location_id=engine.maps.normalize_location(p.world,None)
    p.immortal_power_converted=True;p.immortal_conversion_stage=5
    p.asura_cultivation.update(conversion=5)
    p.additional_roots=['metal','wood','water','fire','earth','wind','thunder','yin','yang']
    p.body_training=80;p.divine_sense_rank=40;p.divine_sense_experience=500
    p.heart_demon=50;p.qi_experience={k:0 for k in ('spirit','demon','monster','yin')}
    p.qi_experience[{'dao':'spirit','demonic':'demon','ghost':'yin','monster':'monster','buddhist':'spirit','confucian':'spirit'}[p.path]]=1000000
    p.opportunity=1e12;p.inventory=[];p.formation_materials=[];p.crafting_materials=[]
    p.formation_active_bindings=[];p.formation_ground_arrays=[]
    p.secret_art_state={};p.technique=p.support_technique=None;p.combat_techniques=[];p.known_techniques=[]
    p.sealed_cultivation=p.cultivation_suppression=None
    book=copy.deepcopy(TECHNIQUE_CATALOG[art['technique_id']]);book.level=6 if book.id=='TECH_HUNDRED_THOUSAND_FROST' else 9
    learn_technique(p,book);assign_technique(p,book,art['slot'])
    if art['effect']=='body_progress':
        body=copy.deepcopy(next(t for t in TECHNIQUE_CATALOG.values() if t.category=='body' and t.grade<=p.realm_index))
        learn_technique(p,body);assign_technique(p,body,'body')
        p.body_progress=0.;p.awaiting_body_breakthrough=False
    p.hp=max_hp(p);p.mp=max_mp(p);p.lifespan=p.age+10000
    if resources:
        add_item(p,'spirit_stone',100000000)
        for row in art['cost'].get('essences',[]):add_item(p,f'secret_{row["kind"]}_{row["nature"]}_{row["tier"]}')
        for row in art['cost'].get('formations',[]):
            definition=next(d for d in formation_material_definitions().values() if d['nature']==row['nature'] and d['tier']>=row['tier'])
            p.formation_materials.append(make_formation_material_instance(definition,source='验收原材料',origin_world=definition['world']))
    engine.store.save(g)
    engine.get_game(g.id)
    return engine.store.load(g.id)


def act(engine,g,identity,**overrides):
    engine.get_game(g.id)
    current=engine.store.load(g.id);q=quote(current,catalog()[identity])
    return engine.train_secret_art(g.id,identity,'awaken',**dict(revision=current.player.secret_art_state.get('revision',0),quote=q['token'])|overrides)


@pytest.mark.parametrize('identity',sorted(catalog()))
def test_every_authored_art_activates_through_real_command_once_and_roundtrips(base,identity):
    e,original=base;g=prepare(e,original,identity);p=g.player;art=catalog()[identity]
    q=quote(g,art);assert not q['reason'],(identity,q)
    old_rank=p.divine_sense_rank;old_exp=p.divine_sense_experience;old_heart=p.heart_demon;old_op=p.opportunity
    act(e,g,identity);saved=e.store.load(g.id);p=saved.player
    assert p.secret_art_state['manuals'][identity]['activated']
    assert decode_state(p.secret_art_state)==p.secret_art_state
    assert not p.formation_materials and not any('secret_core_' in i.id or 'secret_soul_' in i.id for i in p.inventory)
    assert p.opportunity==old_op-q['opportunity']
    if art['effect']=='sense_rank':assert p.divine_sense_rank==old_rank+1 and p.divine_sense_experience==old_exp
    elif art['effect']=='sense_experience':assert p.divine_sense_experience>old_exp
    elif art['effect']=='heart_relief':assert p.heart_demon==old_heart-art['value']
    elif art['effect']=='body_progress':assert p.body_progress==pytest.approx(q['growth']['before']+q['growth']['gain'])
    elif art['effect']=='qi_experience':assert p.qi_experience[art['target']]==pytest.approx(q['growth']['before']+q['growth']['gain'])
    elif art['effect']=='art_experience':assert p.art_experience[art['target']]==pytest.approx(q['growth']['before']+q['growth']['gain'])
    elif art['effect']=='clone_pair':assert len([a for a in p.puppets if a.get('source_secret')==identity])==2
    elif art['effect']=='frost_tribulation':
        from cultivation_life.system.technique_secret_rules import frost_bonus
        assert frost_bonus(p)==pytest.approx(.07)
    else:assert bonus(p,art['effect'])==pytest.approx(art['value'])
    before=e.store._path(g.id).read_bytes()
    with pytest.raises(ValueError):act(e,g,identity)
    assert e.store._path(g.id).read_bytes()==before


def test_new_books_have_real_sources_and_unique_names():
    for key in ('TECH_TIANYUAN_ART','TECH_HIGH_SKY_COLD_RAY'):
        t=TECHNIQUE_CATALOG[key]
        assert t.growth_preference=='support' and t.combat_effect['identity']==key
        assert {g['world'] for g in MARKET_GOODS if g['content_id']==key}=={'human','demon','spirit','true_demon','monster_realm','phantom_underworld','hell','celestial','asura','nether','reincarnation'}
    names=[t.name for t in TECHNIQUE_CATALOG.values()]
    for name in ('天元术','高天寒芒'):assert names.count(name)==1
    assert {(a['realm'],TECHNIQUE_CATALOG[a['technique_id']].path) for a in catalog().values()} >= {(r,p) for r in range(1,13) for p in ('dao','demonic','monster','ghost')}


def test_five_color_ice_uses_five_real_materials_and_increases_base_not_multiplier(base,monkeypatch):
    e,original=base;identity='manual_five_color_ice';g=prepare(e,original,identity)
    initial=e._breakthrough_chance(g.player,major=True)
    act(e,g,identity);g=e.store.load(g.id);p=g.player
    increased=e._breakthrough_chance(p,major=True)
    assert increased['base']-initial['base']==pytest.approx(.05)
    assert increased['technique_secret_bonus']==.05
    p.layer=REALMS[4].layers;p.hp=max_hp(p);p.mp=max_mp(p);e.store.save(g)
    class FailingRandom(random.Random):
        def random(self):return .999999
    monkeypatch.setattr('cultivation_life.engine.actions.cultivation.decode_rng',lambda *a:FailingRandom(77))
    e.breakthrough(g.id);g=e.store.load(g.id)
    assert g.player.realm_index==4
    assert e._breakthrough_chance(g.player,major=True)['technique_secret_bonus']==.05
    book=g.player.support_technique;g.player.support_technique=None
    assert not any(r['id']==identity for r in project(g))
    assert bonus(g.player,'major_bonus')==0
    g.player.support_technique=book
    assert bonus(g.player,'major_bonus')==.05
    g.player.realm_index=5
    assert bonus(g.player,'major_bonus')==0


def test_know_heaven_once_per_actual_realm_survives_unequip_drop_and_crossworld(base):
    e,original=base;identity='manual_know_heaven';g=prepare(e,original,identity)
    rank=g.player.divine_sense_rank;experience=g.player.divine_sense_experience
    act(e,g,identity);g=e.store.load(g.id);book=g.player.support_technique
    g.player.support_technique=None;e.store.save(g);g=e.store.load(g.id)
    assert g.player.divine_sense_rank==rank+1 and g.player.divine_sense_experience==experience
    g.player.support_technique=book;g.player.realm_index=3;e.store.save(g)
    act(e,g,identity);g=e.store.load(g.id)
    assert g.player.divine_sense_rank==rank+2
    assert g.player.secret_art_state['manuals'][identity]['realms']==[2,3]
    for realm,world in ((2,'human'),(3,'spirit')):
        g.player.realm_index=realm;g.player.world=world;g.player.location_id=e.maps.normalize_location(world,None);e.store.save(g)
        with pytest.raises(ValueError,match='本大境界'):act(e,g,identity)
    assert e.store.load(g.id).player.divine_sense_rank==rank+2
    # Arrange a legal origin, then actually descend and return through the
    # authoritative transition plan; neither sealing nor return resets uses.
    g.player.realm_index=8;g.player.layer=9
    receipts=copy.deepcopy(g.player.secret_art_state)
    e._apply_world_transition(g,e._plan_world_transition(g,'human','sealed_descent'))
    assert g.player.secret_art_state==receipts and g.player.sealed_cultivation
    assert quote(g,catalog()[identity])['reason']
    e._apply_world_transition(g,e._plan_world_transition(g,'spirit','sealed_return'))
    assert g.player.secret_art_state==receipts and not g.player.sealed_cultivation
    assert g.player.divine_sense_rank==rank+2


@pytest.mark.parametrize('change',['wrong_slot','not_learned','wrong_root','low_material','missing_material','pending','suppression','trial','no_opportunity'])
def test_bad_prerequisites_are_rejected_without_payment(base,change):
    e,original=base;identity='manual_know_heaven' if change=='no_opportunity' else 'manual_five_color_ice'
    g=prepare(e,original,identity);p=g.player;q=quote(g,catalog()[identity])
    if change=='wrong_slot':p.technique=p.support_technique;p.support_technique=None
    elif change=='not_learned':p.known_techniques=[]
    elif change=='wrong_root':p.spirit_root='supreme_metal';p.additional_roots=[]
    elif change=='low_material':
        for r in p.formation_materials:r['acquired_tier']=4
    elif change=='missing_material':p.formation_materials.pop()
    elif change=='pending':g.pending_event=e._instantiate_event(e.events_by_id['EVT_SECT_FIRST_WARNING_001'],g,random.Random(1))
    elif change=='suppression':p.cultivation_suppression={'test':True}
    elif change=='trial':g.active_trial={'kind':'traditional'}
    else:p.opportunity=0
    # Invalid fixture markers need no save decoding: the public domain command
    # sees the original owned state, and its failure must not mutate that state.
    from cultivation_life.engine.composition.secret_arts import bind
    from dataclasses import replace
    from cultivation_life.system.technique_secrets import execute
    deps=replace(bind(e),load=lambda _:g)
    before=copy.deepcopy(g.to_dict())
    with pytest.raises(ValueError):execute(deps,g.id,identity,revision=0,token=q['token'])
    assert g.to_dict()==before


def test_stale_quote_save_failure_and_forged_receipts_cannot_spend(base,monkeypatch):
    e,original=base;identity='manual_five_color_ice';g=prepare(e,original,identity)
    stale=quote(g,catalog()[identity])['token']
    g.player.formation_materials[0]['name']='原材料状态已变'
    g.player.support_technique.level=8
    next(t for t in g.player.known_techniques if t.id==g.player.support_technique.id).level=8
    e.store.save(g);e.get_game(g.id)
    before=e.store._path(g.id).read_bytes()
    with pytest.raises(ValueError,match='已变化'):act(e,g,identity,quote=stale)
    assert e.store._path(g.id).read_bytes()==before
    with monkeypatch.context() as patch:
        patch.setattr(e.store,'save',lambda *_:(_ for _ in ()).throw(OSError('disk full')))
        with pytest.raises(OSError):act(e,g,identity)
    assert e.store._path(g.id).read_bytes()==before
    for payload in ({'activated':True,'realms':[2,2]}, {'activated':True,'realms':[True]}, {'activated':True,'realms':[]}, {'activated':True,'realms':[2],'extra':1}):
        with pytest.raises(ValueError):decode_state(dict(schema_version=1,revision=0,arts={},manuals={'manual_know_heaven':payload}))
    with pytest.raises(ValueError):decode_state(dict(schema_version=1,revision=0,arts={},manuals={'manual_authored_fake':dict(activated=True,realms=[])}))


@pytest.mark.parametrize('identity,effect',[('manual_wanmo','cost_discount'),('manual_soul_lamp_canon','sense_discount'),('manual_crimson_furnace','body_bonus')])
def test_existing_quotes_use_live_slot_effects(base,identity,effect):
    e,original=base;g=prepare(e,original,identity);p=g.player
    getter=(breakthrough_opportunity_required if effect=='cost_discount' else divine_sense_breakthrough_cost if effect=='sense_discount' else lambda p:e._body_breakthrough_chance(p)['final'])
    before=getter(p);act(e,g,identity);p=e.store.load(g.id).player;after=getter(p)
    assert after<before if effect.endswith('discount') else after>before
    p.support_technique=None
    assert getter(p)==before


def test_combat_slot_loses_qi_eligibility_without_losing_activation(base):
    e,original=base;identity='manual_tianjian';g=prepare(e,original,identity)
    act(e,g,identity);p=e.store.load(g.id).player
    assert bonus(p,'major_bonus')>0
    previous=copy.deepcopy(p.qi_experience);p.qi_experience={}
    assert bonus(p,'major_bonus')==0
    p.qi_experience=previous
    assert bonus(p,'major_bonus')==catalog()[identity]['value']


@pytest.mark.parametrize('succeed',[False,True])
def test_discounted_breakthrough_keeps_unspent_opportunity_on_success_and_failure(base,monkeypatch,succeed):
    from cultivation_life.content_registry import WORLD_SYSTEMS
    from cultivation_life.rules import opportunity_required
    e,original=base;identity='manual_wanmo';g=prepare(e,original,identity)
    act(e,g,identity);g=e.store.load(g.id);p=g.player
    p.opportunity=opportunity_required(p);p.heart_demon=0
    amount=breakthrough_opportunity_required(p);before=p.opportunity;layer=p.layer
    e.store.save(g)
    class ResultRandom(random.Random):
        def random(self):return 0.0 if succeed else .999999
    monkeypatch.setattr('cultivation_life.engine.actions.cultivation.decode_rng',lambda *a:ResultRandom(77))
    e.breakthrough(g.id);saved=e.store.load(g.id).player
    retained=0 if succeed else amount*float(WORLD_SYSTEMS['breakthrough']['minor_failure_retention'])
    assert saved.opportunity==pytest.approx(before-amount+retained)
    assert saved.layer==layer+(1 if succeed else 0)
    assert saved.secret_art_state['manuals'][identity]['activated']


@pytest.mark.parametrize('scope',['active','ground'])
def test_bound_materials_are_never_sacrificed(base,scope):
    from cultivation_life.system.formation_system import available_formation_candidates, _extract_candidate
    e,original=base;g=prepare(e,original,'manual_five_color_ice');p=g.player
    held=_extract_candidate(p,available_formation_candidates(p)[0])
    if scope=='active':p.formation_active_bindings=[held]
    else:p.formation_ground_arrays=[dict(bindings=[held])]
    before=copy.deepcopy(p.to_dict())
    q=quote(g,catalog()['manual_five_color_ice'])
    assert q['reason'] and len(q['bill'])==4
    assert p.to_dict()==before


@pytest.mark.parametrize('source',['crafting_material','inventory'])
def test_shared_formation_material_uses_original_store(base,source):
    from cultivation_life.system.formation_system import formation_shared_definitions, available_formation_candidates
    from cultivation_life.system.crafting_system import crafting_material_definitions, make_crafting_material_instance
    e,original=base;identity='manual_five_color_ice';g=prepare(e,original,identity);p=g.player
    def tier(d):
        return crafting_material_definitions()[d['crafting_material_id']]['tier'] if source=='crafting_material' else d.get('tier',1)
    d=next(d for d in formation_shared_definitions().values() if d['source_kind']==source and d['nature'] in {'metal','wood','water','fire','earth'} and tier(d)>=5 and (source!='inventory' or d.get('item_id')))
    old=next(c for c in available_formation_candidates(p) if c['nature']==d['nature'])
    p.formation_materials=[r for r in p.formation_materials if r['id']!=old['storage_id']]
    if source=='inventory':add_item(p,d['item_id'],2)
    else:
        material=crafting_material_definitions()[d['crafting_material_id']]
        p.crafting_materials.append(make_crafting_material_instance(material,random.Random(7),source='原炼器库',origin_world=p.world))
    e.store.save(g);e.get_game(g.id);g=e.store.load(g.id)
    q=quote(g,catalog()[identity]);assert not q['reason']
    assert source in {r['candidate']['source_kind'] for r in q['bill']}
    act(e,g,identity);p=e.store.load(g.id).player
    if source=='inventory':assert next(i.quantity for i in p.inventory if i.id==d['item_id'])==1
    else:assert not p.crafting_materials


@pytest.mark.parametrize('family',['immortal','demonic','ghost','monster'])
@pytest.mark.parametrize('realm',[9,10,11])
def test_real_major_trials_apply_once_without_buffing_copies_and_resume(family,realm,monkeypatch):
    from scripts import calibrate_upper_breakthroughs as calibration
    from cultivation_life.system.combat.trials import load_battle,dump_battle,run_batch
    path='dao' if family=='immortal' else family
    art=next(a for a in catalog().values() if a['realm']==realm and a['effect'].startswith('trial_') and TECHNIQUE_CATALOG[a['technique_id']].path==path)
    original=calibration.configure_field;enabled=False
    def configure(game,*args):
        result=original(game,*args);book=copy.deepcopy(TECHNIQUE_CATALOG[art['technique_id']]);book.level=6 if book.id=='TECH_HUNDRED_THOUSAND_FROST' else 9
        game.player.qi_experience[{'dao':'spirit','demonic':'demon','ghost':'yin','monster':'monster'}[path]]=1000000
        learn_technique(game.player,book);assign_technique(game.player,book,art['slot'])
        if enabled:game.player.secret_art_state=dict(schema_version=1,revision=1,arts={},manuals={art['id']:dict(activated=True,realms=[])})
        return result
    monkeypatch.setattr(calibration,'configure_field',configure)
    variant=calibration.variants(family)[0]
    normal,_=calibration.prepare(family,realm,'ready',variant,14813)
    enabled=True;boosted,_=calibration.prepare(family,realm,'ready',variant,14813)
    stat=art['effect'][6:]
    assert boosted['battle_state']['stats']['player'][stat]==pytest.approx(normal['battle_state']['stats']['player'][stat]*(1+art['value']))
    assert boosted['battle_state']['stats']['enemy']==normal['battle_state']['stats']['enemy']
    b=load_battle(boosted['snapshot']);state=copy.deepcopy(boosted['battle_state']);rng=random.Random(71)
    run_batch(b,state,rng,batch_size=1)
    restored=load_battle(json.loads(json.dumps(dump_battle(b))));state2=copy.deepcopy(state);rng2=random.Random();rng2.setstate(rng.getstate())
    assert run_batch(b,state,rng,batch_size=1)==run_batch(restored,state2,rng2,batch_size=1)
    assert state==state2
