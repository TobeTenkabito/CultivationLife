"""Restoration thresholds choose actions without waiving fees or ordinary turns."""
import json
from dataclasses import replace
import pytest

from cultivation_life.system.combat.contracts import VoisinageEffect
from cultivation_life.system.combat.trials import dump_battle,load_battle
from cultivation_life.system.combat.voisinages import VoisinageBattle
from test_voisinage_effects import actor,caster,domain
from test_body_round_wuyun import start
from test_monster_body import encounter


@pytest.mark.parametrize('kind,attribute,small,large',[
 ('restore_body','body',.9,.8),('restore_body','vitality',.9,.8),
 ('restore_spirit','morale',90,80),('restore_spirit','pressure',.1,.2),
 ('restore_field','field_strain',.1,.2),
])
def test_minor_damage_keeps_attack_and_real_treatment_pays_and_consumes_ordinary(kind,attribute,small,large):
    d=domain(VoisinageEffect(kind,3,.1,target='self'),restore_threshold=.85)
    protection=domain(VoisinageEffect('seal',999,.1),strength=1000,stability=1000)
    b=VoisinageBattle([actor('player','player',caster(d)),actor('enemy','enemy',caster(protection,stance='protect'))])
    s=b.units['player'];setattr(s,attribute,small);s.active_voisinage='test'
    assert start(b).ordinary_player and s.current==99
    assert not any(r['kind']=='body_action' and r['owner']=='player' for r in b._light_trace)
    setattr(s,attribute,large)
    assert not start(b,2).ordinary_player and s.current==95
    assert any(r['kind']=='body_action' and r['owner']=='player' for r in b._light_trace)


def test_missing_snapshot_threshold_keeps_old_treatment_behaviour():
    d=domain(VoisinageEffect('restore_body',3,.1,target='self'))
    b=VoisinageBattle([actor('player','player',caster(d)),actor('enemy','enemy')]);b.units['player'].body=.99
    raw=json.loads(json.dumps(dump_battle(b)))
    raw['units'][0]['capabilities']['voisinages'][0].pop('restore_threshold')
    restored=load_battle(raw)
    assert not start(restored).ordinary_player and restored.units['player'].current==95


def test_free_liezang_healing_remains_event_driven_instead_of_auto_threshold():
    b=encounter();s=b.units['player'];s.body=s.vitality=.9
    caps=s.unit.capabilities
    s.unit=replace(s.unit,capabilities=replace(caps,voisinages=tuple(replace(d,restore_threshold=.5) for d in caps.voisinages)))
    start(b)
    assert s.body==1 and s.vitality==1
    assert any(r['kind']=='body_action' and r['free'] for r in b._light_trace)


@pytest.mark.parametrize('value',[True,0,-1,1.1,float('nan'),float('inf'),'85%'])
def test_threshold_is_finite_numeric_fraction(value):
    with pytest.raises((ValueError,TypeError)):domain(restore_threshold=value)
