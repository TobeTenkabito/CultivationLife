"""The base decision/lifecycle helper contains no optional-gameplay dependencies."""
import copy
import pytest
from cultivation_life.system import institution_petitions as p
from cultivation_life.institution_petitions_schema import validate


def test_bounded_original_case_and_attributable_promise():
    scope=dict(id='base:institution',revision=0)
    case=p.open_case(scope,kind='repair',period=1,now=100,deadline=200,actor='original-npc',
                     evidence=dict(target='original-building'),witnesses=[])
    assert case and not p.open_case(scope,kind='repair',period=1,now=100,deadline=200,actor='original-npc',evidence={},witnesses=[])
    p.endorse(scope,case,'player','fund')
    with pytest.raises(ValueError):p.endorse(scope,case,'player','reject')
    p.submit(scope,case)
    with pytest.raises(ValueError):p.submit(scope,case)
    p.close(scope,case,now=110,status='resolved',decision='fund',result='Original account pays through its own adapter.')
    with pytest.raises(ValueError):p.close(scope,case,now=110,status='resolved',decision='fund',result='again')
    assert not p.open_case(scope,kind='repair',period=1,now=120,deadline=220,actor='original-npc',evidence={},witnesses=[])
    validate(scope['petitions'],scope['id'])
    assert scope['petitions']['history'][0]['pledge']==dict(actor='player',choice='fund')


def test_decision_filters_unaffordable_and_invalid_facts_without_mutation():
    choices=[dict(id='fund',cost=100,priority=90),dict(id='impossible',cost=0,priority=999,reason='No original person'),dict(id='decline',cost=0,priority=10)]
    saved=copy.deepcopy(choices)
    assert p.choose(choices,budget=99,preferred='fund')=='decline'
    assert p.choose(choices,budget=100)=='fund'
    assert p.choose([choices[1]],budget=10**12) is None
    assert saved==choices
