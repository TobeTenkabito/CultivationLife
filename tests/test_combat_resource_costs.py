"""Real combat resources must buy endurance instead of taxing larger pools."""
import copy
import random
from pathlib import Path

import pytest

from cultivation_life.combat_costs import technique_cost
from cultivation_life.content_registry import TECHNIQUE_CATALOG
from cultivation_life.engine import GameEngine
from cultivation_life.rules import max_hp, max_mp
from cultivation_life.system.combat.contracts import Combatant, CombatCapabilities
from cultivation_life.system.combat.ordinary import exchange_damage
from cultivation_life.system.combat.trials import dump_battle, load_battle
from cultivation_life.system.combat.voisinages import VoisinageBattle
from tests.test_fixed_technique_combat import step


def low_book():
    original=next(t for t in TECHNIQUE_CATALOG.values() if t.grade==1 and t.combat_effect.get('payload')=='finite_shield')
    e=copy.deepcopy(original.combat_effect)
    e.update(trigger='paid_preparation',covenant='observed_event_once',clauses=[],uses=1,delivery='next_window')
    return dict(id=original.id,name=original.name,level=1,effect=e,
                cost_model=dict(grade=1,realm=5,fixed=e['mana_cost']))


def with_capacity(book, capacity):
    return VoisinageBattle([Combatant('player','施法者','player',100.,capabilities=CombatCapabilities(
        mana_capacity=capacity,mana_initial=capacity,technique_effects=[book])),
        Combatant('enemy','敌人','enemy',100.)])


@pytest.mark.parametrize('capacity',[10.,100.,10000.,1e8])
def test_same_low_book_cost_is_absolute_and_survives_resume(capacity):
    book=low_book();b=with_capacity(book,capacity)
    step(b,1)
    assert capacity-b.units['player'].mana_current==pytest.approx(book['effect']['mana_cost'])
    b=load_battle(dump_battle(b))
    step(b,2)
    assert capacity-b.units['player'].mana_current==pytest.approx(book['effect']['mana_cost'])


def test_insufficient_absolute_mana_cannot_buy_full_effect():
    book=low_book();b=with_capacity(book,book['effect']['mana_cost']/2)
    step(b,1)
    assert not next(iter(b.techniques.catalog.records.values()))['receipts']
    assert b.units['player'].mana_current==book['effect']['mana_cost']/2


def test_overlevel_must_afford_the_sum_not_either_part_alone():
    book=low_book();book['cost_model'].update(realm=0,fixed=99.)
    b=with_capacity(book,100.);step(b,1)
    assert technique_cost(book,100.)>100
    assert b.units['player'].mana_current==100.
    assert not next(iter(b.techniques.catalog.records.values()))['receipts']


def test_fixed_payment_snapshot_rejects_old_percentage_forgery():
    book=low_book();b=with_capacity(book,10000.)
    step(b,1)
    snapshot=dump_battle(b)
    record=next(iter(snapshot['technique_runtime']['catalog']['records'].values()))
    record['paid']=record['receipts'][0]['paid']=10000*book['effect']['cost_bp']/10000
    with pytest.raises(ValueError):load_battle(snapshot)


def test_started_legacy_battle_keeps_its_frozen_payment_contract():
    book=low_book();book.pop('cost_model');book['effect'].pop('mana_cost')
    b=with_capacity(book,100.)
    step(b,1)
    assert b.units['player'].mana_current==pytest.approx(100-book['effect']['cost_bp']/100)
    assert load_battle(dump_battle(b)).techniques.dump()==b.techniques.dump()


def test_taiyuan_upgrade_reduces_fixed_cost_without_pool_tax():
    t=TECHNIQUE_CATALOG['TECH_COMMON_GUI'];book=dict(id=t.id,name=t.name,level=1,effect=t.combat_effect,
        cost_model=dict(grade=4,realm=8,fixed=t.combat_effect['mana_cost']))
    assert technique_cost(book,1000.)==technique_cost(book,1e9)==pytest.approx(55.68)
    book['level']=9
    assert technique_cost(book,1e9)==pytest.approx(55.68*.84)


def test_ordinary_damage_has_no_percent_floor_and_still_hurts_peers():
    def hit(attack):return exchange_damage(attack,1e6,attack/1e6,1.,coefficient=.135,minimum=.045,maximum=.42)
    assert hit(0)==0
    assert 0<hit(1)<hit(100)<.001
    assert .1<hit(1e6)<.2


@pytest.fixture(scope='module')
def combat_game(tmp_path_factory):
    e=GameEngine(Path(__file__).resolve().parents[1],tmp_path_factory.mktemp('combat-resource-cost'))
    g=e.store.load(e.create_game('耗费对照','supreme_metal','dao',6741,preset_id='core')['id'])
    g.pending_event=None
    p=g.player;p.realm_index=5;p.layer=1;p.body_training=0
    p.combat_techniques=[];p.duel_technique_ids=[]
    p.hp=max_hp(p);p.mp=max_mp(p)
    return e,g


def engage(e,original,*,extra_hp=0.,extra_mp=0.,opponent_ratio=None):
    g=copy.deepcopy(original);p=g.player
    p.permanent_intrinsic_hp_bonus+=extra_hp;p.permanent_intrinsic_mp_bonus+=extra_mp
    p.hp=max_hp(p);p.mp=max_mp(p)
    before=(p.hp,p.mp)
    power=e._player_battle_power(g)
    target=dict(target_name='练气对照' if opponent_ratio is None else '同阶对照',
        target_power=200. if opponent_ratio is None else power*opponent_ratio,
        target_realm_index=1 if opponent_ratio is None else 5,target_layer=1,
        combat_type='cultivator',path='dao',action='spar',single_combat=True)
    e._combat(g,target,False,random.Random(17))
    return before[0]-p.hp,before[1]-p.mp,g,power


@pytest.mark.parametrize('opponent_ratio',[None,.9])
def test_extra_hp_mp_buys_endurance_in_actual_engine(combat_game,opponent_ratio):
    e,g=combat_game
    hp,mp,baseline,power=engage(e,g,opponent_ratio=opponent_ratio)
    more_hp,more_mp,boosted,boost_power=engage(e,g,extra_hp=100000,extra_mp=100000,opponent_ratio=opponent_ratio)
    assert boost_power==pytest.approx(power)
    assert more_hp<=hp*1.1+.01
    assert more_mp<=mp*1.1+.01
    if hp>0:
        assert more_hp/max_hp(boosted.player)<hp/max_hp(baseline.player)
    else:
        assert more_hp==0
    assert 0<more_mp/max_mp(boosted.player)<mp/max_mp(baseline.player)
    print('resource comparison',opponent_ratio,'base',(hp,mp),'extra 100000 HP/MP',(more_hp,more_mp))


def test_spirit_cultivator_vs_qi_uses_less_than_one_percent_mana(combat_game):
    e,g=combat_game
    hp,mp,result,_=engage(e,g)
    assert 0<mp<max_mp(g.player)*.01
    assert hp<max_hp(g.player)*.01
    assert result.last_combat_report['outcome']=='victory'


@pytest.mark.parametrize('realm',[0,1,5])
@pytest.mark.parametrize('capacity',[100.,10000.])
@pytest.mark.parametrize('level',[1,9])
def test_three_branches_pay_the_exact_hybrid_total_and_resume(realm,capacity,level):
    book=low_book();book['cost_model']['realm']=realm;book['level']=level
    fixed=book['effect']['mana_cost'];percent=capacity*book['effect']['cost_bp']/10000
    expected=(fixed if realm>1 else percent if realm==1 else fixed+percent)*(1-.02*(level-1))
    b=with_capacity(book,capacity);step(b,1)
    assert capacity-b.units['player'].mana_current==pytest.approx(expected)
    assert load_battle(dump_battle(b)).techniques.dump()==b.techniques.dump()


def test_repeated_refund_cannot_exceed_receipt_capacity_limit():
    book=low_book();book['cost_model']['fixed']=50.
    b=with_capacity(book,100.);step(b,1,dealt=0,received=0)
    runtime=b.techniques.catalog;key=next(iter(runtime.records))
    for _ in range(10):runtime.refund(key,0,.05)
    assert runtime.records[key]['receipts'][0]['refunded']==pytest.approx(1.)
    load_battle(dump_battle(b))


def test_projection_freezes_actual_player_and_npc_realm(combat_game):
    from cultivation_life.models import SectNpc
    from cultivation_life.system.technique_effect_provider import project
    from cultivation_life.rules import learn_technique,assign_technique
    from cultivation_life.system.duel_techniques import select
    _,base=combat_game;g=copy.deepcopy(base);book=copy.deepcopy(TECHNIQUE_CATALOG['TECH_BASIC_QI'])
    learn_technique(g.player,book);assign_technique(g.player,book,'combat');select(g.player,book.id)
    projected=project(g,g.player,player=True)[0]
    assert projected['cost_model']==dict(grade=1,realm=5,fixed=book.combat_effect['mana_cost'])
    npc=SectNpc('fee-owner','原修士','',1,1,30,None,spirit_root='supreme_metal',
                duel_technique_ids=[book.id],technique_levels={book.id:1})
    npc_book=project(g,npc)[0]
    assert npc_book['cost_model']['realm']==1
    assert technique_cost(npc_book,1000.)==pytest.approx(1000*book.combat_effect['cost_bp']/10000)
    npc.realm_index=5
    assert technique_cost(project(g,npc)[0],1000.)==pytest.approx(book.combat_effect['mana_cost'])
    assert npc_book['cost_model']['realm']==1  # Frozen encounter is not repriced.


@pytest.mark.parametrize('realm',[8,9,10])
def test_lineage_energy_uses_same_hybrid_rule(realm):
    from tests.test_technique_effect_foundation import manual,actor,begin
    book=manual();book['cost_model']=dict(grade=9,realm=realm,fixed=20.)
    b=VoisinageBattle([actor('player','player',[book],capacity=200.,current=200.),actor('enemy-0','enemy')])
    begin(b,1)
    expected=20 if realm>9 else 4 if realm==9 else 24
    assert b.units['player'].current==pytest.approx(200-expected)
    load_battle(dump_battle(b))


def test_payment_terms_do_not_alias_the_source_projection():
    book=low_book();fee=book['effect']['mana_cost'];b=with_capacity(book,10000.)
    book['cost_model'].update(realm=0,fixed=1000.)
    step(b,1)
    assert 10000-b.units['player'].mana_current==pytest.approx(fee)
    load_battle(dump_battle(b))


@pytest.mark.parametrize('change',[{'realm':True},{'realm':13},{'grade':0},{'fixed':float('nan')},{'fixed':-1},{'free':True}])
def test_invalid_hybrid_terms_cannot_enter_battle(change):
    book=low_book();book['cost_model'].update(change)
    with pytest.raises(ValueError):with_capacity(book,10000.)


@pytest.mark.parametrize('realm',[1,5])
def test_existing_burst_uses_fixed_low_tier_and_proportional_peer_prices(combat_game,realm):
    e,original=combat_game;g=copy.deepcopy(original)
    g.player.realm_index=realm
    g.player.combat_techniques=[copy.deepcopy(TECHNIQUE_CATALOG['TECH_BASIC_QI'])]
    g.player.combat_plan=dict(manual=True,burst='early',mp_reserve=0.)
    _,normal,base,_=engage(e,g)
    _,enlarged,boosted,_=engage(e,g,extra_mp=100000.)
    for battle in (base,boosted):
        assert any('预案自动发动' in event for row in battle.last_combat_report['rounds'] for event in row['events'])
    if realm==5:
        assert enlarged==pytest.approx(normal,abs=.05)
    else:
        assert enlarged>normal*10  # The user explicitly keeps peer casts proportional.
