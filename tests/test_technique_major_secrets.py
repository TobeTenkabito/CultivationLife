"""All six paths, actual fees, optional trial routes and ascension damage."""
import copy
import random

import pytest

from test_technique_secrets import base, prepare, act
from cultivation_life.content_registry import TECHNIQUE_CATALOG, MARKET_GOODS, REALMS
from cultivation_life.rules import assign_technique, learn_technique, opportunity_required, max_hp, max_mp
from cultivation_life.system.technique_secret_rules import catalog, bonus, major_probability_bonus
from cultivation_life.system.monster_bloodline_system import evolution_candidates


def test_new_books_exist_without_dlc_and_use_ordinary_same_grade_budget():
    from pathlib import Path
    from cultivation_life.content_registry import ContentRegistry
    from cultivation_life.system.extension_system import base_documents
    documents=base_documents(Path(__file__).resolve().parents[1]/'content')
    registry=ContentRegistry._from_documents(documents)
    new=[b for b in registry.techniques.values() if b.id.startswith('TECH_SECRET_')]
    assert len(new)==16
    for book in new:
        template=next(t for t in registry.techniques.values() if t.id.startswith('TECH_OPEN_')
                      and t.path=='dao' and t.grade==book.grade and t.growth_preference=='support' and t.element=='neutral')
        assert book.combat_bonus==template.combat_bonus and book.opportunity_bonus==template.opportunity_bonus
        assert book.combat_effect['identity']==book.id
        assert sum(t.name==book.name for t in registry.techniques.values())==1
        assert book.active_in('reincarnation' if book.grade>=9 else 'hell')


@pytest.mark.parametrize('path', ['dao','demonic','ghost','monster','buddhist','confucian'])
@pytest.mark.parametrize('realm', range(1,12))
def test_every_real_major_gate_has_an_applicable_book(path,realm):
    effects = ({'cost_discount'} if path=='monster' and realm<=8 else
               {'ascension_guard'} if realm==8 else
               {'major_bonus','trial_guard','trial_breach','trial_sustain','trial_sense'} if realm>=9 else {'major_bonus'})
    matches=[a for a in catalog().values() if a['realm']==realm and a['effect'] in effects
             and TECHNIQUE_CATALOG[a['technique_id']].path==path]
    assert matches, (path,realm)
    # Existing books may be relic/story rewards. New support books must have
    # an actual market route rather than exist only in the secret-art catalog.
    for art in matches:
        if art['technique_id'].startswith('TECH_SECRET_'):
            assert any(g['content_id']==art['technique_id'] for g in MARKET_GOODS)


@pytest.mark.parametrize('path',['dao','demonic','ghost','buddhist','confucian'])
def test_ascension_secret_reduces_real_thunder_only_and_cannot_repeat(base,path):
    e,original=base;identity=f'manual_gate_{path}_8'
    g=prepare(e,original,identity);p=g.player
    # Avoid the unrelated high-body mitigation cap in the general fixture.
    p.body_training=0;p.hp=max_hp(p);p.mp=max_mp(p);e.store.save(g)
    kind='asura_ascension' if path=='demonic' else 'celestial_ascension'
    normal=e._tribulation_damage_reduction(p,kind)
    ordinary=e._tribulation_damage_reduction(p,'periodic_thunder')
    act(e,g,identity);g=e.store.load(g.id);p=g.player
    assert e._tribulation_damage_reduction(p,kind)==pytest.approx(normal+.08)
    assert e._tribulation_damage_reduction(p,'periodic_thunder')==ordinary
    with pytest.raises(ValueError):act(e,g,identity)
    # Load and submit the real first three events, including the first thunder.
    plain=copy.deepcopy(g);plain.player.secret_art_state={}
    results=[]
    for game in (plain,g):
        game.player.layer=REALMS[8].layers
        game.player.hp=max_hp(game.player);game.player.mp=max_mp(game.player)
        game.player.opportunity=opportunity_required(game.player)
        e.store.save(game)
        begin=e.begin_asura_ascension if path=='demonic' else e.begin_celestial_ascension
        shown=begin(game.id)
        for _ in range(3):
            event=shown['pending_event']
            shown=e.choose(game.id,event['choices'][0]['id'],event_id=event['id'])
        after=e.store.load(game.id)
        assert after.active_trial['step_index']==3
        results.append((after.player.hp,after.player.mp))
    assert results[1][0]>results[0][0] and results[1][1]>results[0][1]
    receipt=copy.deepcopy(p.secret_art_state)
    p.technique=p.support_technique=None
    assert bonus(p,'ascension_guard')==0 and p.secret_art_state==receipt


def test_monster_evolution_pays_discount_once_and_preserves_real_requirements(base):
    e,_=base
    original=e.store.load(e.create_game('存真验收','supreme_water','monster',14735,monster_species_id='serpent')['id'])
    g=prepare(e,original,'manual_gate_monster_1');act(e,g,'manual_gate_monster_1');g=e.store.load(g.id)
    p=g.player;p.monster_evolution_id='SERPENT_SPIRIT';p.monster_evolution_history=['SERPENT_BASE','SERPENT_SPIRIT']
    p.layer=REALMS[1].layers;p.awaiting_major_breakthrough=True
    full=opportunity_required(p);p.opportunity=full-1;e.store.save(g)
    target=next(r['id'] for r in evolution_candidates(p) if r['enabled'])
    before=e.store._path(g.id).read_bytes()
    with pytest.raises(ValueError):e.evolve_monster(g.id,target)
    assert e.store._path(g.id).read_bytes()==before
    p.opportunity=full;e.store.save(g)
    e.evolve_monster(g.id,target);saved=e.store.load(g.id).player
    import math
    assert saved.realm_index==2 and saved.opportunity==full-math.ceil(full*.9)
    assert bonus(saved,'cost_discount')==0
    assert saved.secret_art_state['manuals']['manual_gate_monster_1']['activated']
    with pytest.raises(ValueError):e.evolve_monster(g.id,target)


@pytest.mark.parametrize('identity',['manual_gate_buddhist_9','manual_gate_confucian_10','manual_reincarnation_11_main'])
def test_upper_probability_route_reads_same_activated_receipt(base,identity):
    e,original=base;g=prepare(e,original,identity);act(e,g,identity);p=e.store.load(g.id).player
    amount=catalog()[identity]['value']
    plain=copy.deepcopy(p);plain.secret_art_state={}
    assert major_probability_bonus(p)==pytest.approx(amount)
    assert e._breakthrough_chance(p,True)['base']-e._breakthrough_chance(plain,True)['base']==pytest.approx(amount)
    assert e._breakthrough_chance(p,False)['base']==e._breakthrough_chance(plain,False)['base']
    p.realm_index+=1
    assert major_probability_bonus(p)==0


@pytest.mark.parametrize('identity',['manual_five_color_ice','manual_blood_sea_embryo','manual_gate_confucian_4'])
def test_nascent_secret_does_not_follow_the_wearer_to_later_realms(base,identity):
    from cultivation_life.system.technique_secrets import project
    e,original=base;g=prepare(e,original,identity);act(e,g,identity)
    g=e.store.load(g.id);p=g.player;art=catalog()[identity]
    assert art['realm']==4 and art['effect']=='major_bonus'
    receipt=copy.deepcopy(p.secret_art_state)
    for realm in (4,5,6):
        p.realm_index=realm
        # Keep the same learned and equipped original book through save/load.
        e.store.save(g);g=e.store.load(g.id);p=g.player
        expected=art['value'] if realm==4 else 0.
        assert e._breakthrough_chance(p,True)['technique_secret_bonus']==pytest.approx(expected)
        assert e._breakthrough_chance(p,False)['technique_secret_bonus']==0
        assert p.secret_art_state==receipt
        row=next(row for row in project(g) if row['id']==identity)
        assert row['status']==('生效中' if realm==4 else '已激活·暂不生效')


@pytest.mark.parametrize('path',['buddhist','confucian'])
@pytest.mark.parametrize('realm',[9,10,11])
def test_new_upper_books_improve_real_trial_without_improving_mirror(path,realm,monkeypatch):
    from scripts import calibrate_upper_breakthroughs as calibration
    art=catalog()[f'manual_gate_{path}_{realm}']
    configure=calibration.configure_field;enabled=False
    def setup(game,*args):
        result=configure(game,*args);p=game.player;p.path=path
        book=copy.deepcopy(TECHNIQUE_CATALOG[art['technique_id']]);book.level=9
        learn_technique(p,book);assign_technique(p,book,art['slot'])
        if enabled:p.secret_art_state=dict(schema_version=1,revision=1,arts={},manuals={art['id']:dict(activated=True,realms=[])})
        return result
    monkeypatch.setattr(calibration,'configure_field',setup)
    variant=calibration.variants('immortal')[0]
    normal,_=calibration.prepare('immortal',realm,'ready',variant,14813)
    enabled=True;boosted,_=calibration.prepare('immortal',realm,'ready',variant,14813)
    assert boosted['battle_state']['stats']['player']['guard']==pytest.approx(normal['battle_state']['stats']['player']['guard']*(1+art['value']))
    assert boosted['battle_state']['stats']['enemy']==normal['battle_state']['stats']['enemy']
