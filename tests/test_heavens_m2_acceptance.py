"""M2 closure: true perception versus usable power, all tiers and fixed years."""
import copy
from unittest.mock import Mock, patch

import pytest

from test_heavens_m1 import local
from cultivation_life.system.heavens import operations
from cultivation_life.system.heavens.calendar import year_step, YearContext, PARTICIPATION
from cultivation_life.system.heavens.definitions import CONTACT_SITES
from cultivation_life.system.heavens.state import get_echo


def years(local, count):
    game, deps = local[1:]
    for _ in range(count):
        year_step(deps, game, YearContext(game.heavens_state['runtime']['last_year_key']+1))


def draw(value):
    return patch('cultivation_life.system.heavens.calendar.sha256', return_value=Mock(
        digest=lambda: int(value*2**64).to_bytes(8,'big')+bytes(24)))


@pytest.mark.parametrize('realm,probability', list(enumerate([.02,.02,.02,.02,.08,.12,.16,.24,.32,.45,.65,.80,.90])))
@pytest.mark.parametrize('success', [False, True])
def test_all_thirteen_realms_respect_probability_boundary(local, realm, probability, success):
    engine, game, deps = local
    game.player.realm_index = realm
    if realm < 9:
        game.player.world, game.player.location_id = 'human', 'wudi_plain'
    before = game.rng_state
    with draw(probability-0.00001 if success else probability):
        years(local, 99)
        assert game.heavens_state['runtime']['rng_counter'] == 0
        years(local, 1)
    runtime = game.heavens_state['runtime']
    assert PARTICIPATION[realm] == probability
    assert runtime['rng_counter'] == 1 and game.rng_state == before
    assert bool(runtime['notifications']) is success
    if realm < 9:
        assert bool(runtime.get('omens')) is success
        assert not runtime.get('ruins') and not runtime.get('mirror')
        assert not game.player.formation_materials
    else:
        assert bool(get_echo(runtime)) is success


@pytest.mark.parametrize('contact', CONTACT_SITES, ids=lambda s:s.world)
@pytest.mark.parametrize('field', ['sealed_cultivation','cultivation_suppression'])
def test_true_rank_perceives_in_all_four_worlds_but_cannot_use_sealed_power(local, contact, field):
    engine, game, deps = local
    game.player.world, game.player.location_id = contact.world, contact.location_id
    game.player.realm_index = 5
    setattr(game.player, field, {'realm_index':12,'layer':1})
    before = game.rng_state
    with draw(.85): years(local, 100)
    assert get_echo(game.heavens_state['runtime'], contact.id)
    facts = deps.read_actor_facts(game, contact.id)
    assert facts['true_realm'] == 12 and facts['can_discover']
    assert facts['blocked_reason'] and not facts['can_apply']
    engine.store.save(game)
    disk = engine.store._path(game.id).read_bytes()
    for action, options in [('observe',{}), ('maintain',{'material_id':'missing'}), ('attune',{})]:
        with pytest.raises(ValueError): operations.preview(deps, game.id, action, contact.id, options)
    assert engine.store._path(game.id).read_bytes() == disk and game.rng_state == before


@pytest.mark.parametrize('field', ['sealed_cultivation','cultivation_suppression'])
def test_true_high_rank_senses_lower_world_omen_without_bypassing_anomaly_entry(local, field):
    engine, game, deps = local
    game.player.world, game.player.location_id, game.player.realm_index = 'human','muling_desert',3
    setattr(game.player, field, {'realm_index':11,'layer':1})
    with draw(.75): years(local,100)
    assert 'sand_glimmer' in game.heavens_state['runtime']['omens']
    assert deps.read_omen_facts(game,'sand_glimmer')['true_realm'] == 11
    engine.store.save(game)
    with pytest.raises(ValueError): operations.preview(deps,game.id,'mirror_enter','mirror_field',{})


@pytest.mark.parametrize('realm', [2,5,9,10,11,12])
def test_equal_five_centuries_not_more_attempts_for_larger_action_units(local, realm):
    game = local[1]
    game.player.realm_index = realm
    if realm < 9: game.player.world,game.player.location_id='human','wudi_plain'
    with draw(.99): years(local,500)
    runtime = game.heavens_state['runtime']
    assert runtime['processed_years'] == 500 and runtime['last_discovery_window'] == 4
    assert runtime['rng_counter'] == 5 and not runtime['notifications']
    saved = copy.deepcopy(game.heavens_state)
    year_step(local[2],game,YearContext(500))
    assert game.heavens_state == saved


@pytest.mark.parametrize('block', ['dead','custody','location','space','closed','capacity'])
def test_perception_still_requires_actual_free_local_presence_and_budget(local, block):
    from cultivation_life.system.heavens.state import create_echo, visible_notice
    game = local[1]
    game.player.realm_index=5
    game.player.sealed_cultivation={'realm_index':12,'layer':1}
    if block=='dead': game.player.alive=False
    if block=='custody': game.player.imprisonment={'holder_id':'test'}
    if block=='location': game.player.location_id='elsewhere'
    if block=='space': game.spatial_state['current']='another-space'
    if block=='closed': game.heavens_state['generation_enabled']=False
    if block=='capacity':
        for contact in CONTACT_SITES[1:]:
            create_echo(local[2],game,contact.id)
            visible_notice(game,'known',contact.id)
    with draw(0): years(local,100)
    runtime = game.heavens_state['runtime']
    assert runtime['rng_counter']==0 and not get_echo(runtime)


def test_newly_sealed_effective_high_rank_cannot_apply_known_node(local):
    from cultivation_life.system.heavens.state import create_echo
    engine,game,deps=local
    echo=create_echo(deps,game)
    echo.update(observed_cycle=0,history_checked=True,exchanged=True)
    game.player.sealed_cultivation={'realm_index':12,'layer':1}
    assert deps.read_actor_facts(game)['can_discover']
    assert not deps.read_actor_facts(game)['can_apply']
    engine.store.save(game)
    with pytest.raises(ValueError): operations.preview(deps,game.id,'attune','sea_echo',{})
