"""Authored grants, bounded progression, real tribulations and paid combat."""
import copy
import json
import random

import pytest

from test_technique_secrets import base, prepare, act
from test_fixed_technique_combat import fight, step
from cultivation_life.content_registry import TECHNIQUE_CATALOG, REALMS, MARKET_GOODS
from cultivation_life.models import Technique
from cultivation_life.rules import add_item, add_technique_copy, upgrade_known_technique, combat_power
from cultivation_life.technique_evolution import FROST, WIND, evolve
from cultivation_life.system import clone_support
from cultivation_life.system.npc_development import service
from cultivation_life.system.technique_secret_rules import frost_bonus, trial_stats, catalog
from cultivation_life.system.technique_secrets import quote, project
from cultivation_life.system.technique_effect_provider import project as effects
from cultivation_life.system.combat.trials import dump_battle, load_battle


def promoted(g,rank=9,level=7):
    p=g.player;p.realm_index=rank;p.world='celestial';p.immortal_power_converted=True
    for b in [*p.known_techniques,*p.combat_techniques]:
        if b.id==FROST:b.level=level;evolve(b)
    p.duel_technique_ids=[FROST]


def test_books_sources_roots_and_finite_effects():
    for key,grade,root in [(WIND,4,'wind'),(FROST,8,'water')]:
        book=TECHNIQUE_CATALOG[key]
        assert book.grade==grade and book.required_affinities==[root]
        assert any(r['content_id']==key for r in MARKET_GOODS)
        assert sum(b.name==book.name for b in TECHNIQUE_CATALOG.values())==1
        assert book.combat_effect['identity']==key


def test_pair_claim_is_atomic_permanent_and_not_party_power(base,monkeypatch):
    e,original=base;g=prepare(e,original,'manual_demon_dance');power=combat_power(g.player)
    before=e.store._path(g.id).read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(e.store,'save',lambda *_:(_ for _ in ()).throw(OSError('disk full')))
        with pytest.raises(OSError):act(e,g,'manual_demon_dance')
    assert e.store._path(g.id).read_bytes()==before
    act(e,g,'manual_demon_dance');g=e.store.load(g.id)
    assert len(g.player.puppets)==2 and not g.player.party
    assert combat_power(g.player)==power
    for a in g.player.puppets:
        assert a['realm_index']==4 and a['layer']==1 and a['operating_energy']==0
        assert a['combat_power']==pytest.approx(REALMS[4].base_power*.35)
        assert clone_support.cultivation_cap(a)==8
    g.player.combat_techniques=[];e.store.save(g)
    assert not any(r['id']=='manual_demon_dance' for r in project(g)) and len(e.store.load(g.id).player.puppets)==2
    # Destroy/remove the assets and restore the slot: the receipt still forbids a second grant.
    g.player.puppets=[];g.player.combat_techniques=[copy.deepcopy(next(t for t in g.player.known_techniques if t.id==WIND))]
    e.store.save(g)
    with pytest.raises(ValueError):act(e,g,'manual_demon_dance')
    assert not e.store.load(g.id).player.puppets


@pytest.mark.parametrize('method',['infuse','material'])
def test_batch_training_stops_at_eight_and_never_changes_energy(base,method):
    e,original=base;g=prepare(e,original,'manual_demon_dance');clone_support.grant_dance_pair(g.player)
    p=g.player;p.realm_index=12;p.layer=9;p.world='celestial';p.location_id=e.maps.normalize_location(p.world,None)
    a=p.puppets[0];a.update(realm_index=8,layer=REALMS[8].layers-1,operating_energy=30)
    add_item(p,'npc_training_puppet_cultivation_2',20)
    q=service.quote(g,'puppet',a['id'],'cultivation',method,10)
    assert q['rounds']==1 and q['result']['realm_index']==8 and q['result']['layer']==REALMS[8].layers
    service.apply(g,'puppet',a['id'],'cultivation',method,10)
    assert a['realm_index']==8 and a['operating_energy']==30
    before=copy.deepcopy(p.to_dict())
    with pytest.raises(ValueError,match='8阶'):service.apply(g,'puppet',a['id'],'cultivation',method,10)
    assert p.to_dict()==before and not clone_support.units(g,trial=True)


def test_frost_upgrade_uses_real_manual_and_switches_effect_once(base):
    e,original=base;g=prepare(e,original,'manual_frost_sky');act(e,g,'manual_frost_sky');g=e.store.load(g.id);p=g.player
    p.body_training=0
    before=e._tribulation_damage_reduction(p,'periodic_thunder')
    assert before>=.07 and frost_bonus(p)==.07
    book=next(t for t in p.known_techniques if t.id==FROST);add_technique_copy(p,book,level=6)
    unchanged=copy.deepcopy(p.to_dict())
    with pytest.raises(ValueError,match='仙阶'):upgrade_known_technique(p,FROST)
    assert p.to_dict()==unchanged
    p.realm_index=9;p.world='celestial';p.immortal_power_converted=True
    assert upgrade_known_technique(p,FROST)==7
    assert all(t.grade==9 and t.force_tier==2 and t.combat_effect['resource']=='energy' for t in [book,*p.combat_techniques])
    assert frost_bonus(p)==0 and frost_bonus(p,immortal=True)==.04
    assert e._tribulation_damage_reduction(p,'periodic_thunder')==pytest.approx(before-.07)
    restored=Technique(**copy.deepcopy(vars(book)))
    assert restored.level==7 and restored.grade==9 and restored.combat_effect==book.combat_effect
    p.combat_techniques=[]
    assert frost_bonus(p,immortal=True)==0
    p.combat_techniques=[restored];assert frost_bonus(p,immortal=True)==.04
    p.qi_experience={};assert frost_bonus(p,immortal=True)==0


@pytest.mark.parametrize('rank',[9,10,11,12])
def test_frost_all_six_stats_and_npc_paid_resource_projection(base,rank):
    e,original=base;g=prepare(e,original,'manual_frost_sky');p=g.player
    p.secret_art_state=dict(schema_version=1,revision=1,arts={},manuals={'manual_frost_sky':dict(activated=True,realms=[])})
    promoted(g,rank,9)
    stats={k:100. for k in ('might','guard','mobility','sense','sustain','breach')};trial_stats(p,stats,major=False)
    assert set(stats.values())=={104.}
    own=effects(g,p,player=True);assert len(own)==1 and own[0]['effect']['resource']=='energy'
    npc=dict(id='frost_npc',world='celestial',realm_index=rank,spirit_root='supreme_water',body_training=0,
        transcendence={'conversion':1},technique_levels={FROST:9},duel_technique_ids=[FROST])
    assert effects(g,npc)[0]['effect']['resource']=='energy'
    npc['transcendence']['conversion']=0;assert not effects(g,npc)
    npc['transcendence']['conversion']=1;npc['realm_index']=8;assert not effects(g,npc)


@pytest.mark.parametrize('key',[WIND,FROST])
def test_real_recipe_pays_both_sides_and_resumes_without_duplicate_budgets(key):
    t=TECHNIQUE_CATALOG[key]
    row=dict(id=key,name=t.name,level=1,effect=copy.deepcopy(t.combat_effect))
    # Cost model uses the real authored rate on a controlled same-grade 100-MP pool.
    row['cost_model']=dict(grade=t.grade,realm=t.grade,fixed=t.combat_effect['mana_cost'])
    b=fight([row],[row]);events=[]
    for n in range(1,7):
        step(b,n);events+=b.techniques.report()['events']
        if n==3:b=load_battle(json.loads(json.dumps(dump_battle(b))))
    for owner in ('player','enemy'):
        assert any(r['owner']==owner and r['event']=='paid' for r in events)
        assert b.units[owner].mana_current<100
    assert any(r['event'] in {'breach','absorbed','restored'} for r in events)
    empty=fight([row],[row],mana=0)
    for n in range(1,5):step(empty,n)
    assert not empty.techniques.report()['receipts']


@pytest.mark.parametrize('family',['immortal','demonic','ghost','monster'])
def test_real_trial_snapshot_boosts_self_not_mirrors_and_survives_resume(family,monkeypatch):
    from scripts import calibrate_upper_breakthroughs as calibration
    from cultivation_life.rules import learn_technique,assign_technique
    from cultivation_life.system.combat.trials import run_batch
    original=calibration.configure_field;enabled=False
    def configure(g,*args):
        result=original(g,*args);p=g.player;p.additional_roots=['water'];p.qi_experience['spirit']=1000000
        p.immortal_power_converted=True
        t=copy.deepcopy(TECHNIQUE_CATALOG[FROST]);t.level=9;evolve(t)
        learn_technique(p,t);assign_technique(p,t,'combat')
        if enabled:p.secret_art_state=dict(schema_version=1,revision=1,arts={},manuals={'manual_frost_sky':dict(activated=True,realms=[])})
        return result
    monkeypatch.setattr(calibration,'configure_field',configure)
    variant=calibration.variants(family)[0]
    normal,_=calibration.prepare(family,9,'ready',variant,14813)
    enabled=True;boosted,_=calibration.prepare(family,9,'ready',variant,14813)
    for k,v in normal['battle_state']['stats']['player'].items():assert boosted['battle_state']['stats']['player'][k]==pytest.approx(v*1.04)
    assert normal['battle_state']['stats']['enemy']==boosted['battle_state']['stats']['enemy']
    b=load_battle(boosted['snapshot']);state=copy.deepcopy(boosted['battle_state']);rng=random.Random(12)
    run_batch(b,state,rng,batch_size=1)
    restored=load_battle(json.loads(json.dumps(dump_battle(b))));state2=copy.deepcopy(state);rng2=random.Random();rng2.setstate(rng.getstate())
    assert run_batch(b,state,rng,batch_size=1)==run_batch(restored,state2,rng2,batch_size=1)
    assert state==state2
