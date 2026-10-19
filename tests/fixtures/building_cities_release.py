"""Isolated release fixtures. Gameplay itself always goes through real controls."""
from cultivation_life.building_rules import ensure_state
from cultivation_life.rules import add_item,remove_item
from cultivation_life.system.building_projects import quote


def prepare_buildings(engine,identity):
    game=engine._load(identity)
    assert game.player.world=='human'
    game.pending_event=game.active_trial=None
    game.settings.update(silent_events=True,combat_popup=False,guixu_event_popup=False)
    game.player.next_tribulation_age=None
    add_item(game.player,'spirit_stone',10**14)
    for key in quote(game,'city')['materials']:add_item(game.player,key,100000)
    engine.store.save(game)


def shortage_buildings(engine,identity,restore=False):
    game=engine.store.load(identity)
    key=next(iter(quote(game,'city')['materials']))
    if restore:add_item(game.player,key,100000)
    else:remove_item(game.player,key,100000)
    engine.store.save(game)


def building_followup(engine,identity):
    import copy
    game=engine.store.load(identity)
    game.pending_event['_followup_event']=copy.deepcopy(engine.events_by_id['EVT_SECT_FIRST_WARNING_001'])
    engine.store.save(game)


def inspect_buildings(engine,identity):
    game=engine.store.load(identity)
    row=next(r for r in game.building_state['records'].values() if r['type']=='city')
    assert row['level']==1 and row['status']=='intact' and row['population']=='mixed'
    assert row['owner']==dict(kind='player',id=identity)
    used=game.building_state['city_usage'][row['id']]
    assert used['story']==1 and 'govern_year' in used
    assert 'scene' not in game.building_state and not game.pending_event


def visit_initial_city(engine,identity,index=0):
    from cultivation_life.building_rules import config
    game=engine.store.load(identity)
    assert not game.pending_event and not game.building_state.get('scene')
    game.player.location_id=config()['cities'][game.player.world][index]['location_id']
    engine.store.save(game)
