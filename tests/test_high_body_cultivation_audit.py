"""Real API transactions reject body training while the owner is wandering."""
import pytest
from test_immortal_cultivation import prepared
from test_asura_manifestation import ready
from test_monster_body import ready_monster
from test_ghost_body import ready_ghost


@pytest.mark.parametrize('fixture_name,action,key',[
    ('prepared','train_body',None),('ready','train_body',None),
    ('ready_monster','monster_body_refine','xuanfu'),('ready_ghost','ghost_body_refine','wuxiang')])
def test_wandering_body_training_rejects_before_any_resources_rng_or_save_change(request,fixture_name,action,key):
    values=request.getfixturevalue(fixture_name);e,g=values[:2]
    g.player.immortal_body['level']=30
    if fixture_name=='ready_monster':g.player.immortal_body['monster']={'level':50}
    g.player.spirit_state=dict(mode='wandering',body_intact=True,entered=g.player.age,deadline=g.player.age+1000,
        address=dict(world=g.player.world,location_id=g.player.location_id,instance_id=None))
    e.store.save(g);e.get_game(g.id);path=e.store._path(g.id);before=path.read_bytes()
    with pytest.raises(ValueError,match='神游'):
        if fixture_name=='prepared':e.immortal_action(g.id,action)
        elif fixture_name=='ready':e.asura_action(g.id,action)
        else:e.upper_voisinage_action(g.id,action,key,expected_level=0)
    assert path.read_bytes()==before
