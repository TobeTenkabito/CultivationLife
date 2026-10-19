"""Isolated native fixture setup; actual visits use WebView touch controls."""
from cultivation_life.rules import add_item
from cultivation_life.building_rules import config
from cultivation_life.system.economy.enterprise_view import public_estates


def prepare_visits(engine,identity):
    game=engine._load(identity)
    game.pending_event=None;game.player.path='buddhist'
    game.settings.update(silent_events=True,combat_popup=False)
    game.player.next_tribulation_age=None
    add_item(game.player,'spirit_stone',10**8);engine.store.save(game)
    offer=next(row for row in public_estates(game,engine.maps)['offers'] if row['kind']=='mine')
    engine.fleet_action(identity,dict(action='estate_buy',kind='mine',cost=offer['cost']))


def scenic_visit(engine,identity):
    game=engine.store.load(identity)
    assert not game.pending_event and not game.building_state.get('scene')
    game.player.location_id=config()['scenery'][game.player.world][0]['location_id']
    engine.store.save(game)


def inspect_visits(engine,identity):
    game=engine.store.load(identity)
    claims=game.building_state['visit_usage']
    assert len(claims)==2 and all(row==dict(insight=1) for row in claims.values())
    assert not game.pending_event and not game.building_state.get('scene')
    original=next(row for row in game.economy_v2['estates'].values() if row['owner_id']==identity)
    assert original['produced']==0 and not original['stock'] and original['job'] is None
