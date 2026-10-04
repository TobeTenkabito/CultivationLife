import copy
from pathlib import Path
from unittest.mock import patch
import pytest
from cultivation_life.engine import GameEngine
from cultivation_life.rules import max_mp
from cultivation_life.system.owned_training import quote, public
from cultivation_life.system import asura

@pytest.fixture
def ready(tmp_path):
    engine = GameEngine(Path(__file__).resolve().parents[1], tmp_path)
    game = engine.store.load(engine.create_game('培养', 'supreme_metal', 'demonic', 631)['id'])
    p = game.player
    p.world = 'true_demon'
    p.location_id = engine.maps.default_location(p.world)
    p.realm_index, p.layer, p.body_training, p.divine_sense_rank = 8, 9, 100, 110
    p.opportunity, p.mp = 1e12, max_mp(p)
    game.pending_event = None
    return engine, game

@pytest.mark.parametrize('kind', ['prisoner', 'mechanical', 'living', 'corpse'])
@pytest.mark.parametrize('axis', ['cultivation', 'body', 'sense'])
def test_all_owned_types_train_three_independent_axes_without_dlc(ready, kind, axis):
    engine, g = ready
    target = dict(id='t', name='目标', realm_index=2, layer=1, body_training=10,
                  immortal_body_level=0, divine_sense_rank=17, combat_power=100, type=kind, alive=True)
    collection = g.player.prisoners if kind == 'prisoner' else g.player.puppets
    collection.append(target)
    q = quote(g.player, target, axis, 5)
    age, opp, mp = g.player.age, g.player.opportunity, g.player.mp
    engine.store.save(g)
    with patch.object(asura, 'enabled', return_value=False):
        engine.train_owned(g.id, 't', 'prisoner' if kind == 'prisoner' else 'puppet', axis, 5)
    loaded = engine.store.load(g.id)
    row = (loaded.player.prisoners if kind == 'prisoner' else loaded.player.puppets)[0]
    assert row['combat_power'] == q['power_after'] > 100
    assert loaded.player.age == age
    assert loaded.player.opportunity == pytest.approx(opp-q['opportunity'])
    assert loaded.player.mp == pytest.approx(mp-q['mp'])
    if axis != 'body': assert row['body_training'] == 10
    if axis != 'sense': assert row['divine_sense_rank'] == 17
    if axis == 'body':
        assert row['body_training'] == 60
        assert asura.public_body(row)['eligible']
    # The same year can fund another training operation.
    engine.train_owned(g.id, 't', 'prisoner' if kind == 'prisoner' else 'puppet', axis, 1)


def test_cap_partial_billing_and_high_body(ready):
    _, g = ready
    p = g.player
    p.body_training = 65
    t = dict(body_training=60, realm_index=2, layer=1, combat_power=100, divine_sense_rank=10)
    q = quote(p, t, 'body', 10)
    assert q['rounds'] == 1 and q['result']['body_training'] == 65
    assert q['mp'] == quote(p,t,'body',1)['mp']
    p.body_training = 100
    p.asura_cultivation['body_level'] = 20
    t.update(body_training=100, immortal_body_level=18)
    q = quote(p,t,'body',10)
    assert q['rounds'] == 1 and q['result']['immortal_body_level'] == 20


def test_preview_readonly_and_atomic_rejection(ready):
    engine, g = ready
    t = dict(id='old',name='旧傀儡',type='corpse',combat_power=1)
    original = copy.deepcopy(t)
    public(g.player,t)
    assert t == original
    g.player.puppets=[t]
    g.player.mp=0
    engine.store.save(g)
    engine.get_game(g.id)  # Finish normal load-time world migration before rejection checks.
    snapshot=engine.store.load(g.id).to_dict()
    for batches in (1,0,-1,True,100,'5'):
        with pytest.raises(ValueError): engine.train_owned(g.id,'old','puppet','body',batches)
        assert engine.store.load(g.id).to_dict() == snapshot


def test_cultivation_stops_at_mentor_even_across_realm(ready):
    _,g=ready
    g.player.realm_index,g.player.layer=3,1
    t=dict(realm_index=2,layer=9,body_training=5,divine_sense_rank=10)
    q=quote(g.player,t,'cultivation',10)
    assert (q['result']['realm_index'],q['result']['layer'])==(3,1)
    assert q['rounds']==1


def test_body_training_preserves_explicit_zero_sense(ready):
    _,g=ready
    target=dict(realm_index=4,layer=1,body_training=0,divine_sense_rank=0,combat_power=100)
    q=quote(g.player,target,'body',1)
    assert q['result']['divine_sense_rank']==0
    assert q['result']['body_training']==10
