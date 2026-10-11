"""Deterministic setup; all tested actions subsequently use real UI commands."""
from cultivation_life.system.territory.state import ensure, snapshot, validate_projection
from cultivation_life.system.territory.actions import construction_plan
from cultivation_life.system.economy.organization_accounts import register,key
from cultivation_life.system.economy.ledger import transfer_value
from cultivation_life.system.economy.state import ensure_regional_market

def prepare(engine,identity):
    game=engine._load(identity);game.pending_event=None;game.active_trial=None
    entity=game.sects[game.player.faction_id]
    entity.location_id='expanse_human_1'
    for npc in entity.npcs:npc.realm_index=1;npc.world=entity.world;npc.location_id=entity.location_id
    register(game,'sect',entity.id,entity.world)
    transfer_value(game,'background:human',key('sect',entity.id),10000000,'地方原生验收拨款')
    book=ensure(game,engine.maps,'human')
    for loc in engine.maps.worlds['human']['locations']:
        if loc.get('min_realm_index',0) or entity.id in snapshot(game,engine.maps,'human').get(loc['id'],{}):continue
        try:validate_projection(game,engine.maps,entity,loc['id'])
        except ValueError:continue
        destination=loc['id'];break
    game.player.location_id=destination
    ensure_regional_market(game,engine.maps,'human',destination)
    market=game.economy_v2['markets'][f'human:{destination}']
    for r in construction_plan(game,engine.maps,entity,destination)['materials']:market['commodities'][r['id']]['stock']=50
    engine.store.save(game)
    return dict(id=identity,owner=entity.id,destination=destination,source=entity.location_id)

def assert_outpost(engine,identity):
    game=engine.store.load(identity);entity=game.sects[game.player.faction_id]
    row=snapshot(game,engine.maps,'human')[game.player.location_id][entity.id]
    assert row['outpost'] and row['floor']==50
    assert game.intrigue_state['resolutions'][-1]['result']=='passed'

def assert_relocated(engine,identity):
    game=engine.store.load(identity);entity=game.sects[game.player.faction_id]
    assert entity.location_id==game.player.location_id
    assert snapshot(game,engine.maps,'human')[entity.location_id][entity.id]['value']==100
