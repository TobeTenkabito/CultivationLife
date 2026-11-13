"""Support transfers retain the caster's one paid budget across unequal powers."""
import copy
import pytest
from tests.test_fixed_technique_combat import manual, step
from cultivation_life.system.combat.contracts import Combatant, CombatCapabilities
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.system.combat.trials import dump_battle, load_battle


def support_battle(payload, clause, source_power=10., recipient_power=10000., delivery='next_window'):
    book=manual(payload,clauses=[clause],uses=1,delivery=delivery)
    battle=VoisinageBattle([
        Combatant('player','施法者','player',source_power,capabilities=CombatCapabilities(
            mana_capacity=100.,mana_initial=100.,technique_effects=[book])),
        Combatant('ally','原同伴','player',recipient_power,capabilities=CombatCapabilities(
            technique_context=dict(corpse=True))),
        Combatant('enemy','敌手','enemy',10000.)])
    return battle,book


@pytest.mark.parametrize('powers',[(10.,10000.),(10000.,10.)])
@pytest.mark.parametrize('clause',['give_ally','split_ally','give_corpse'])
@pytest.mark.parametrize('payload',['finite_shield','interruptible_restore'])
def test_support_never_borrows_recipient_power_for_its_budget(powers,clause,payload):
    b,book=support_battle(payload,clause,*powers)
    events=[]
    for n in range(1,5):
        step(b,n,dealt=0,received=.02 if n==1 else 0)
        events.extend(b.techniques.catalog.events)
        b=load_battle(dump_battle(b))
    paid=sum(r['paid'] for r in b.techniques.catalog.records.values())
    actual=[e for e in events if e['event'] in {'absorbed','restored'}]
    assert paid>0 and any(e['target']=='ally' and e['amount']>0 for e in actual)
    total=sum(e['amount']*b.units[e['target']].unit.power for e in actual)
    assert 0<total<=powers[0]*book['effect']['ward_bp']/10000*(1+1e-8)
    if clause!='split_ally':
        assert all(e['target']=='ally' for e in actual)


def test_split_support_keeps_one_source_budget_across_resume_and_rejects_inflation():
    b,book=support_battle('finite_shield','split_ally',delivery='two_half_packets')
    step(b,1,dealt=0,received=.02)
    events=list(b.techniques.catalog.events)
    saved=dump_battle(b)
    b=load_battle(saved)
    step(b,2,dealt=0,received=.02)
    events.extend(b.techniques.catalog.events)
    total=sum(e['amount']*b.units[e['target']].unit.power for e in events if e['event']=='absorbed')
    assert total==pytest.approx(10*book['effect']['ward_bp']/10000)
    forged=copy.deepcopy(saved)
    packets=next(iter(forged['technique_runtime']['catalog']['records'].values()))['packets']
    packet=next(p for p in packets if p['recipient']=='ally' and p['share']>0)
    packet['amount']=book['effect']['ward_bp']/10000*packet['share']
    with pytest.raises(ValueError,match='分包额度'):load_battle(forged)


def test_very_unequal_support_snapshot_cannot_hide_in_absolute_epsilon():
    b,book=support_battle('finite_shield','give_ally',1.,1e20,delivery='two_half_packets')
    step(b,1,dealt=0,received=0)
    saved=dump_battle(b)
    load_battle(saved)
    packet=next(iter(saved['technique_runtime']['catalog']['records'].values()))['packets'][0]
    packet['amount']=1e-10
    with pytest.raises(ValueError,match='分包额度'):load_battle(saved)


def test_tiny_transferred_shield_consumes_relative_budget_and_breaks_only_when_empty():
    b,book=support_battle('finite_shield','give_ally',1.,1e20)
    step(b,1,dealt=0,received=0)
    runtime=b.techniques.catalog
    key=next(iter(runtime.records))
    packet=runtime.records[key]['packets'][0]
    assert runtime.ready(key,packet)
    initial=packet['amount']
    assert 0<initial<1e-12
    runtime.absorb('ally',initial/2,[('enemy',1.)])
    assert packet['share']==pytest.approx(.5)
    assert runtime.facts['ally'].get('broken_round',-1)!=runtime.round
    b=load_battle(dump_battle(b))
    runtime=b.techniques.catalog
    packet=runtime.records[key]['packets'][0]
    runtime.absorb('ally',packet['amount'],[('enemy',1.)])
    assert packet['share']==0
    assert runtime.facts['ally']['broken_round']==runtime.round
