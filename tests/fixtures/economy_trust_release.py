"""Isolated native release fixture; runtime actions still use real UI/API paths."""
def prepare_economy_trust(engine, identity):
    from cultivation_life.models import SectState, SectNpc
    from cultivation_life.system.economy import organizations, caravans
    from cultivation_life.system.economy.ledger import transfer_value
    from cultivation_life.system.economy.fleet_network import new_fleet
    from cultivation_life.system.economy.enterprise_acquisition import acquire
    game = engine._load(identity)
    game.pending_event = None
    game.player.realm_index = 2
    game.player.next_tribulation_age = None
    game.player.lifespan = 10000
    game.settings['silent_events'] = True
    game.family = SectState('release_family', '验收沈氏', 'human',
        [SectNpc('release_heir','沈宁','族人',4,1,100,1000,world='human')],
        kind='family',founded_by_player=True,founder_player_id=game.id,location_id=game.player.location_id)
    organizations.ensure_organizations(game, engine.maps)
    transfer_value(game,'background:human','player',1000000,'隔离验收原始资金')
    transfer_value(game,'background:human','organization:family:release_family',20000,'隔离验收府库资金')
    game.player.age += 5
    organizations.advance_organizations(game,engine.maps)
    caravans.ensure_caravans(game,engine.maps)
    region = game.economy_v2['transport']['worlds']['human']
    fleet = new_fleet(game,region,'human','release_family','family',game.player.location_id,
                      '原组织护卫验收',identifier='human:release-trust-guard')
    transfer_value(game,'organization:family:release_family','caravan:'+fleet['id'],5000,'真实商队出资')
    fleet.update(investment=5000,trade_order={'mode':'hold'})
    row = acquire(game,engine.maps,'human',game.player.location_id,'mine','player',game.id,'player',2)
    transfer_value(game,'player','estate:'+row['id'],10000,'真实产业周转金')
    engine.store.save(game)
