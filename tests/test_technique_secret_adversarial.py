"""Replay, concurrency, real equipment, sealing/return and actual breakthrough audit."""
import copy
import random
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from test_technique_secrets import base, prepare, act
from cultivation_life.content_registry import TECHNIQUE_CATALOG, REALMS
from cultivation_life.rules import learn_technique, opportunity_required, breakthrough_opportunity_required, max_hp, max_mp
from cultivation_life.system.technique_secret_rules import catalog, bonus
from cultivation_life.system.technique_secrets import quote


@pytest.mark.parametrize('identity',['manual_five_color_ice','manual_know_heaven','manual_read_flame'])
def test_concurrent_replay_only_pays_and_awards_once(base,identity):
    e,original=base;g=prepare(e,original,identity);p=g.player;q=quote(g,catalog()[identity]);gate=Barrier(2)
    def submit():
        gate.wait()
        try:e.train_secret_art(g.id,identity,'awaken',revision=0,quote=q['token']);return 'ok'
        except ValueError:return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:submit(),range(2)))
    assert sorted(results)==['ok','rejected']
    saved=e.store.load(g.id).player
    assert saved.secret_art_state['revision']==1
    assert saved.opportunity==p.opportunity-q['opportunity']
    assert not saved.formation_materials
    if identity=='manual_know_heaven':assert saved.divine_sense_rank==p.divine_sense_rank+1
    if identity=='manual_read_flame':assert saved.art_experience['alchemy']==p.art_experience['alchemy']+q['growth']['gain']


def test_discounted_cost_enables_real_breakthrough_below_original_full_bar(base,monkeypatch):
    e,original=base;g=prepare(e,original,'manual_wanmo');act(e,g,'manual_wanmo');g=e.store.load(g.id)
    p=g.player;p.opportunity=breakthrough_opportunity_required(p)
    assert p.opportunity<opportunity_required(p)
    p.awaiting_minor_breakthrough=False;p.awaiting_major_breakthrough=False;e.store.save(g)
    shown=e.get_game(g.id)
    assert shown['breakthrough']['enabled'] and shown['breakthrough']['ready']
    layer=p.layer
    class SuccessRandom(random.Random):
        def random(self):return 0.
    monkeypatch.setattr('cultivation_life.engine.actions.cultivation.decode_rng',lambda *a:SuccessRandom(7))
    e.breakthrough(g.id);p=e.store.load(g.id).player
    assert p.layer==layer+1 and p.opportunity==0


@pytest.mark.parametrize('identity',['manual_void_origin_canon','manual_nether_10_main','manual_celestial_heritage_2'])
def test_real_seal_return_preserves_receipts_and_resources_and_reactivates(base,identity):
    e,original=base;g=prepare(e,original,identity);act(e,g,identity);g=e.store.load(g.id);p=g.player
    art=catalog()[identity];before=copy.deepcopy(p.secret_art_state);inventory=[i.to_dict() for i in p.inventory]
    source=p.world;destination={'spirit':'human','nether':'monster_realm','celestial':'spirit'}[source]
    assert bonus(p,art['effect'])==art['value']
    e._apply_world_transition(g,e._plan_world_transition(g,destination,'sealed_descent'))
    assert p.secret_art_state==before and bonus(p,art['effect'])==0
    e.store.save(g)
    with pytest.raises(ValueError):act(e,g,identity)
    g=e.store.load(g.id)
    e._apply_world_transition(g,e._plan_world_transition(g,source,'sealed_return'));e.store.save(g)
    p=e.store.load(g.id).player
    assert bonus(p,art['effect'])==art['value'] and p.secret_art_state==before
    assert [i.to_dict() for i in p.inventory]==inventory
    with pytest.raises(ValueError):act(e,g,identity)


def test_real_swap_stops_discount_without_repaying_or_erasing_receipt(base):
    e,original=base;g=prepare(e,original,'manual_wanmo');act(e,g,'manual_wanmo');g=e.store.load(g.id)
    learned=copy.deepcopy(TECHNIQUE_CATALOG['TECH_TIANYUAN_ART']);learn_technique(g.player,learned);e.store.save(g)
    receipt=copy.deepcopy(g.player.secret_art_state);op=g.player.opportunity
    e.equip_known_technique(g.id,learned.id,'support');p=e.store.load(g.id).player
    assert bonus(p,'cost_discount')==0 and p.secret_art_state==receipt
    e.equip_known_technique(g.id,catalog()['manual_wanmo']['technique_id'],'support');p=e.store.load(g.id).player
    assert bonus(p,'cost_discount')==.08 and p.secret_art_state==receipt and p.opportunity==op


def test_real_major_breakthrough_keeps_used_know_heaven_and_disables_old_realm_bonus(base,monkeypatch):
    e,original=base;g=prepare(e,original,'manual_blood_river');act(e,g,'manual_blood_river');g=e.store.load(g.id)
    learn_technique(g.player,copy.deepcopy(TECHNIQUE_CATALOG['TECH_TIANYUAN_ART']));e.store.save(g)
    e.equip_known_technique(g.id,'TECH_TIANYUAN_ART','support');act(e,g,'manual_know_heaven')
    g=e.store.load(g.id);p=g.player;p.layer=REALMS[2].layers;p.opportunity=opportunity_required(p)
    p.hp=max_hp(p);p.mp=max_mp(p);e.store.save(g);rank=p.divine_sense_rank
    class SuccessRandom(random.Random):
        def random(self):return 0.
    monkeypatch.setattr('cultivation_life.engine.actions.cultivation.decode_rng',lambda *a:SuccessRandom(7))
    e.breakthrough(g.id);g=e.store.load(g.id);p=g.player
    assert p.realm_index==3 and bonus(p,'major_bonus')==0
    assert p.secret_art_state['manuals']['manual_blood_river']['activated']
    assert p.secret_art_state['manuals']['manual_know_heaven']['realms']==[2]
    assert p.divine_sense_rank>=rank+1
    p.opportunity=opportunity_required(p);e.store.save(g);rank=p.divine_sense_rank
    act(e,g,'manual_know_heaven');p=e.store.load(g.id).player
    assert p.divine_sense_rank==rank+1 and p.secret_art_state['manuals']['manual_know_heaven']['realms']==[2,3]
    with pytest.raises(ValueError):act(e,g,'manual_know_heaven')


@pytest.mark.parametrize('slot',['main','support','combat','body','divine_sense','duel','duel_remove'])
def test_frozen_trial_cannot_swap_ordinary_slots(base,slot):
    e,original=base;g=prepare(e,original,'manual_five_color_ice');act(e,g,'manual_five_color_ice');g=e.store.load(g.id)
    # Actual trial creation, including its real pending event.
    e._start_breakthrough_trial(g,'traditional',4,5,'元婴',major=True,rng=random.Random(71))
    assert g.active_trial
    e.store.save(g);e.get_game(g.id)
    before=e.store.load(g.id).to_dict()
    with pytest.raises(ValueError):e.equip_known_technique(g.id,'TECH_HIGH_SKY_COLD_RAY',slot)
    assert e.store.load(g.id).to_dict()==before
