"""Only isolated fixture provisioning; commands and rewards use normal entry points."""
from cultivation_life.building_rules import config
from cultivation_life.rules import add_item
from cultivation_life.system.building_projects import quote


def prepare_city_management(engine,identity):
    game=engine._load(identity);game.pending_event=None
    game.settings.update(silent_events=True,combat_popup=False,guixu_event_popup=False)
    game.player.next_tribulation_age=None
    add_item(game.player,'spirit_stone',10**12)
    for key in quote(game,'city')['materials']:add_item(game.player,key,100000)
    engine.store.save(game)


def landscape_management(engine,identity):
    game=engine.store.load(identity)
    assert not game.pending_event and not game.building_state.get('scene')
    game.player.location_id=config()['scenery']['human'][1]['location_id']
    engine.store.save(game)


def inspect_city_management(engine,identity):
    game=engine.store.load(identity)
    row=next(r for r in game.building_state['records'].values() if r['type']=='city')
    assert row['facilities']==['exchange']
    book=game.building_state['city_business'][row['id']]
    assert book['income']==2000 and book['expense']==13200 and book['last_year']==game.player.age
    assert game.building_state['landscape_usage']['scenery:human:reed_letter']==dict(ending='0:1')
    assert sum(i.quantity for i in game.player.inventory if i.id=='landscape_reed_letter')==1
    assert not game.pending_event and not game.building_state.get('scene')
