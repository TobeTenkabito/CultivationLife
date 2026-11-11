"""Isolated release characters; no access to the user's save directory."""

def prepare_asura(engine, game_id, *, appoint=True):
    import json
    from cultivation_life.system.asura_court import change_rank
    from cultivation_life.system.asura_governorship import rules
    from cultivation_life.system import institution_authority as authority
    from cultivation_life.system.economy.state import ensure_regional_market
    engine.upper_institution_action(game_id,'join')
    g=engine._load(game_id);g.pending_event=None;g.active_trial=None
    change_rank(g,g.upper_institutions['asura'],1)
    g.upper_institutions['asura'].update(earned=100,regard=60,treasury=10**12)
    g.settings.update(silent_events=True,combat_popup=False)
    engine.store.save(g)
    if not appoint:return
    engine.upper_institution_action(game_id,'governorship',json.dumps(dict(
        action='request',city=rules.cities(g)[0]['id'],token=rules.token(g))))
    g=engine._load(game_id);row=rules.offices(g)[0]
    # Setup only: put the test character and original free people at their office.
    # Acceptance must still assume, construct, enlist, pay and march through commands.
    g.player.location_id=row['location'];g.pending_event=None
    ensure_regional_market(g,engine.maps,'asura',row['location'])
    authority.fund(g,row,rules.SOURCE,10**11)
    king=g.upper_institutions['asura']['court']['holders']['5']
    for n in [n for n in g.sects[rules.COURT].npcs if n.id!=king][:3]:
        n.location_id=row['location'];n.realm_index=9
    engine.store.save(g)


def issue_release_order(engine,game_id):
    from cultivation_life.system.asura_governorship import rules,military
    g=engine._load(game_id);military.issue(g,rules.offices(g)[0],military.CAPITAL);engine.store.save(g)


def advance_release_army(engine,game_id,years=1):
    from cultivation_life.system.asura_governorship import rules,military
    g=engine._load(game_id);row=rules.offices(g)[0]
    for _ in range(years):g.player.age+=1;military.advance(g,engine.maps,row)
    engine.store.save(g)


def support_release_commander(engine,game_id):
    from cultivation_life.system.asura_governorship import rules,politics
    from cultivation_life.system.institution_garrisons import active
    g=engine._load(game_id);row=rules.offices(g)[0]
    for unit in active(row):politics.remember(g,unit['person_id'],'player',20,'隔离验收履约',row['id'])
    engine.store.save(g)
