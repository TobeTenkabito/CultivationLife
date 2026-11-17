"""Real clock, competing submissions and audit projection equivalence."""
import copy
from concurrent.futures import ThreadPoolExecutor
import pytest
from test_seeded_dungeons import local, discover, act
from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.system.dungeons import generation


def test_real_elapsed_action_releases_global_cooldown(local):
    engine,game=local;discover(engine,game);act(engine,game,'enter');act(engine,game,'exit')
    discover(engine,game)
    saved=engine.store.load(game.id);site=list(saved.dungeon_state['instances'].values())[-1]
    payload=dict(dungeon_id=site['id'],revision=site['revision'])
    before=copy.deepcopy(saved.dungeon_state)
    with pytest.raises(ValueError,match='行动单位'):engine.dungeon_action(game.id,'enter',payload)
    assert engine.store.load(game.id).dungeon_state==before
    engine.advance(game.id,'rest',1)
    after=engine.store.load(game.id)
    assert after.player.age-saved.player.age==WORLD_SYSTEMS['time_units'][str(saved.player.realm_index)]
    view=engine.dungeon_action(game.id,'enter',payload)
    assert view['dungeons']['active']
    act(engine,game,'exit')


def test_competing_last_legend_slot_has_one_commit(local,monkeypatch):
    engine,game=local;cfg=copy.deepcopy(generation.config())
    scope=game.player.world+':'+game.player.location_id
    cfg['profiles'][scope]['weights']=[0,0,0,1]
    cfg['legendary_limit'][game.player.world]=1
    monkeypatch.setattr(generation,'config',lambda:cfg)
    payload=dict(world=game.player.world,location_id=game.player.location_id,slot=0)
    def submit():
        try:engine.dungeon_action(game.id,'discover',payload);return 'committed'
        except ValueError:return 'stale'
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:submit(),range(2)))
    assert sorted(results)==['committed','stale']
    state=engine.store.load(game.id).dungeon_state
    assert len(state['instances'])==1 and len(state['legends'][game.player.world])==1
    assert len(state['maps'][scope])==1


def test_compact_audit_projection_matches_native_command_and_save(local):
    engine,game=local;discover(engine,game)
    initial=engine.store.load(game.id).to_dict()
    full=act(engine,game,'enter');saved=engine.store.load(game.id).to_dict()
    from cultivation_life.models import GameState
    engine.store.save(GameState.from_dict(initial))
    project=engine.project_game
    try:
        engine.project_game=lambda prepared:dict(id=prepared._payload['id'],dungeons=prepared._payload['dungeons'])
        compact=act(engine,game,'enter')
    finally:engine.project_game=project
    # Frozen mappings/tuples compare through the ordinary JSON representation.
    from cultivation_life.engine.presentation.projection import _thaw
    assert _thaw(compact['dungeons'])==full['dungeons']
    compact_saved=engine.store.load(game.id).to_dict()
    saved.pop('updated_at');compact_saved.pop('updated_at')
    assert compact_saved==saved
