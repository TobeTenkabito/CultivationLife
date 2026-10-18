"""Differential coverage against the released 2.16.1 account-routing algorithm."""
import copy
import hashlib
import importlib.util
from pathlib import Path
import random
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from cultivation_life.models import GameState
from cultivation_life.regional_context import CalendarGame
from cultivation_life.system.economy import deferred
from cultivation_life.engine.world import regions
from test_regional_calendar import regional

REFERENCE = Path(__file__).parent/'fixtures/deferred_2161.py'
spec = importlib.util.spec_from_file_location('cultivation_life.system.economy._released_deferred', REFERENCE)
released = importlib.util.module_from_spec(spec)
spec.loader.exec_module(released)
# Both algorithms participate in the same original posting transaction.
released._posting = deferred._posting


def fixture():
    return SimpleNamespace(world_simulation={'regions':dict.fromkeys(['human','spirit','celestial']),
        'deferred':{'cash_delta':{'organization:sect:test':30},'debts':{'organization:sect:test':5}}},
        economy_v2={'organization_aliases':{}}, player=SimpleNamespace(world='human',age=40),
        family=None, sects={'test':SimpleNamespace(id='test',world='spirit')})


def test_release_oracle_has_not_been_rewritten():
    assert hashlib.sha256(REFERENCE.read_bytes().replace(b'\r\n',b'\n')).hexdigest() == '3145c83c6ab69f2d35ac9c67339547bdb8fb79280c3bcdc7c74b124187fbed2e'


@pytest.mark.parametrize('key', ['player','background:human','background:spirit','market:spirit:town',
    'world:celestial','operator:human:town','alliance:spirit:test','transport:human',
    'organization:sect:test','organization:family:test','organization:sect:missing',
    'organization:court:heavenly','organization:yaochi:test','organization:upper:celestial',
    'organization:other:test','caravan:one','regional:escrow:spirit','unknown:account'])
@pytest.mark.parametrize('world', ['human','spirit','rift'])
def test_routing_and_projected_balance_match_release(key,world):
    game=fixture()
    game.player.world=world
    for view in (game,CalendarGame(game,'human',20),CalendarGame(game,'spirit',20)):
        for posting in (False,True):
            with deferred.posting() if posting else nullcontext():
                assert deferred.owner(view,key)==released.owner(view,key)
                assert deferred.frozen(view,deferred.owner(view,key))==released.frozen(view,released.owner(view,key))
                assert deferred.projected_balance(view,key,10)==released.projected_balance(view,key,10)


def test_warm_cache_observes_alias_entity_world_family_and_save_changes():
    game=fixture();other=fixture()
    key='organization:sect:test'
    assert deferred.owner(game,key)=='spirit'
    game.sects['test'].world='human'
    assert deferred.projected_balance(game,key,10)==10
    assert deferred.projected_balance(other,key,10)==35
    game.sects['test']=SimpleNamespace(world='celestial')
    assert deferred.owner(game,key)=='celestial'
    game.family=SimpleNamespace(id='test',world='human')
    assert deferred.owner(game,key)=='human'
    game.economy_v2['organization_aliases'][key]='market:spirit:town'
    assert deferred.owner(game,key)=='spirit'
    game.economy_v2['organization_aliases'][key]='caravan:one'
    assert deferred.owner(game,key) is None
    game.economy_v2['organization_aliases'].clear();game.family=None;game.sects.clear()
    assert deferred.owner(game,key) is None
    game.sects['test']=SimpleNamespace(world='spirit')
    assert deferred.owner(game,key)=='spirit'
    game.player.world='spirit'
    assert deferred.projected_balance(game,key,10)==10
    game.world_simulation={}
    assert not deferred.frozen(game,'celestial')


def test_posting_scope_restores_after_nested_failure_and_other_save():
    game=fixture();other=fixture()
    with pytest.raises(RuntimeError),deferred.posting():
        with deferred.posting():
            assert not deferred.frozen(game,'spirit')
            assert deferred.projected_balance(other,'organization:sect:test',10)==10
        assert not deferred.frozen(game,'spirit')
        raise RuntimeError('isolated rollback')
    assert deferred.frozen(game,'spirit') and deferred.frozen(other,'spirit')


def test_syntax_cache_is_bounded_and_contains_no_live_state():
    for index in range(4200): deferred._address('caravan:'+str(index))
    assert deferred._address.cache_info().currsize<=4096
    assert deferred._address('organization:sect:test')==('entity','test')


@pytest.mark.parametrize('seed',[123,789])
def test_mixed_tasks_exact_state_matches_release_after_reload_and_entry(regional,seed):
    from regional_scenario import prepare,check
    engine,_=regional
    with deferred.posting(): initial=prepare(engine,fixed_routes=True)
    initial.player.world='celestial'  # Isolated departure fixture only.
    def run(legacy):
        game=copy.deepcopy(initial)
        snapshots=[]
        with patch.multiple(deferred,**{name:getattr(released,name) for name in
                ('owner','frozen','projected_balance','transfer')}) if legacy else nullcontext():
            rng=random.Random(seed)
            for year in range(20):
                game.player.age+=1
                engine._advance_world_year(game,rng,[],encounters=False)
                if year==9:
                    game.diplomacy_unit+=1
                    engine._advance_wars_unit(game,rng)
                    game=GameState.from_dict(game.to_dict())
            snapshots.append(game.to_dict())
            for world in ['human','spirit','true_demon','demon']:
                regions.synchronize(engine._dependencies.regions,game,[world])
                check(game)
                snapshot=game.to_dict()
                regions.synchronize(engine._dependencies.regions,game,[world])
                assert game.to_dict()==snapshot
                snapshots.append(snapshot)
        return snapshots
    assert run(False)==run(True)
