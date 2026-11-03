"""A successful paid release borrows the following round's active actions."""
import json,random
from dataclasses import replace
import pytest

from cultivation_life.system.combat.body_mechanisms import BodyMechanism
from cultivation_life.system.combat.contracts import CombatCapabilities,VoisinageEffect
from cultivation_life.system.combat.trials import dump_battle,load_battle
from cultivation_life.system.combat.voisinages import VoisinageBattle
from test_monster_body import encounter
from test_body_round_wuyun import m,start
from test_voisinage_effects import domain


def recovery_battle(**kwargs):
    b=encounter(release=.1,evade=0,reaction=False,**kwargs)
    s=b.units['player'];caps=s.unit.capabilities
    rows=tuple(replace(r,effects={**r.effects,'release_recovery':1}) if r.id=='feixue' else r for r in caps.body_mechanisms)
    s.unit=replace(s.unit,capabilities=replace(caps,body_mechanisms=rows))
    return b


def test_release_acts_now_rests_exactly_next_round_and_cannot_roll_over_recovery():
    b=recovery_battle();first=start(b)
    assert first.ordinary_player and b.units['player'].release_recovery_round==2
    assert b.units['player'].current==88
    second=start(b,2)
    assert not second.ordinary_player and b.units['player'].current==87
    assert b._dominated['player']=='enemy' and b.units['player'].release_recovery_round==2
    assert b.report()['release_recovery']=={'player':2}
    assert not any(r['kind']=='domination_release' and r.get('success') for r in b._light_trace)
    third=start(b,3)
    assert third.ordinary_player and b.units['player'].release_recovery_round==4
    assert b.units['player'].current==76


def test_recovery_blocks_base_extra_and_reactions_but_keeps_passive_evasion_and_maintenance():
    b=recovery_battle();start(b)
    s=b.units['player'];caps=s.unit.capabilities
    actions=domain(VoisinageEffect('strike',3,.1),VoisinageEffect('restore_body',3,.1,target='self'),strength=1,stability=1)
    rows=(*caps.body_mechanisms,m('extra',extra=3),m('nigu2',evade=1),
          BodyMechanism('liezang','烈脏',dict(retaliate_heal=1,retaliate_power=.1)))
    s.unit=replace(s.unit,capabilities=replace(caps,voisinages=(actions,),body_mechanisms=rows))
    before=s.current;body=s.body;vitality=s.vitality
    start(b,2)
    assert s.current==before-1 and s.body==body and s.vitality==vitality
    assert any(r['kind']=='field_evade' and r['success'] for r in b._light_trace)
    assert not any(r['kind'] in {'body_action','reaction_ready'} and r['owner']=='player' for r in b._light_trace)
    assert b._body_round.records['player']['extra']['triggered']
    assert s.active_voisinage=='test'


def test_recovery_still_blocks_ordinary_when_no_longer_dominated_and_expires():
    b=recovery_battle();start(b)
    enemy=b.units['enemy'];enemy.unit=replace(enemy.unit,capabilities=CombatCapabilities())
    own=b.units['player'];own.unit=replace(own.unit,capabilities=replace(own.unit.capabilities,voisinages=()))
    assert not start(b,2).ordinary_player
    assert 'player' not in b._dominated
    before=enemy.vitality;b.ordinary_damage(.1,0)
    assert enemy.vitality==before
    assert start(b,3).ordinary_player
    b.ordinary_damage(.1,0)
    assert enemy.vitality<before


@pytest.mark.parametrize('silenced,unaffordable',[(True,False),(False,True)])
def test_failed_or_silenced_release_never_schedules_recovery(silenced,unaffordable):
    b=recovery_battle(enemy_body=(m('qian',silence=1),) if silenced else ())
    if unaffordable:b.units['player'].current=5
    start(b,first='enemy')
    assert b.units['player'].release_recovery_round==0
    assert not any(r['kind']=='release_recovery_plan' for r in b._light_trace)


def test_recovery_survives_json_boundary_without_new_rolls_or_costs():
    b=recovery_battle();start(b)
    restored=load_battle(json.loads(json.dumps(dump_battle(b))))
    for n in (2,3,4):
        a=random.Random(71+n);c=random.Random(71+n)
        start(b,n,rng=a);start(restored,n,rng=c)
        assert json.loads(json.dumps(dump_battle(b)))==json.loads(json.dumps(dump_battle(restored)))
        assert b.report()==restored.report() and a.getstate()==c.getstate()


@pytest.mark.parametrize('value',[-1,True,.5,'2',1000000001])
def test_invalid_recovery_snapshot_is_rejected(value):
    raw=dump_battle(recovery_battle());raw['states']['player']['release_recovery_round']=value
    with pytest.raises(ValueError,match='release recovery'):load_battle(raw)


def test_frozen_old_battle_retains_explicit_release_without_new_penalty():
    b=encounter(release=.1,evade=0,reaction=False)
    raw=dump_battle(b)
    for row in raw['states'].values():row.pop('release_recovery_round')
    restored=load_battle(raw)
    assert start(restored).ordinary_player and start(restored,2).ordinary_player
    assert restored.units['player'].release_recovery_round==0


def test_enemy_npc_uses_the_same_recovery_rule_as_the_player():
    original=recovery_battle()
    b=VoisinageBattle([replace(s.unit,id='npc' if k=='player' else 'player',
        side='enemy' if k=='player' else 'player') for k,s in original.units.items()])
    assert start(b).ordinary_enemy
    assert b.units['npc'].release_recovery_round==2
    assert not start(b,2).ordinary_enemy
    assert b.report()['release_recovery']=={'npc':2}


@pytest.mark.parametrize('value',[.5,True,2,-1])
def test_recovery_channel_is_a_bounded_integer(value):
    with pytest.raises(ValueError):m('feixue',release_recovery=value)
