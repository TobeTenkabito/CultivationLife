"""Disposable release scenarios; actual identities, charter and formal crossings.

Fixture preparation isolates unrelated annual society events, then releases the
save to the ordinary compiled engine. No production dependency is replaced.
"""
def prepare_heavens(engine, game_id):
    from dataclasses import replace
    from cultivation_life.rules import add_item, max_hp, max_mp
    from cultivation_life.system.economy import depot, organizations
    from cultivation_life.system.heavens import outpost_runtime as runtime
    from cultivation_life.system.heavens.calendar import year_step, YearContext
    from cultivation_life.system.heavens.state import initialize
    from cultivation_life.system.heavens.operations import command
    from cultivation_life.system.heavens.outpost_routes import profile, peers, ENDPOINTS, target_for
    g=engine.store.load(game_id);p=g.player;source=p.world;destination=peers(source)[0];terms=profile(source)
    p.location_id=ENDPOINTS[source];p.lifespan=None;p.next_tribulation_age=p.age+999999
    p.master,p.dao_companion,p.dao_friends,p.party=None,None,[],[]
    p.hp,p.mp=max_hp(p),max_mp(p)
    g.pending_event=g.active_trial=None;g.settings['silent_events']=True
    owner=next(e for e in g.sects.values() if e.world==source and e.kind=='sect' and len(e.npcs)>=2)
    owner.location_id=ENDPOINTS[source];owner.founded_by_player=True;owner.founder_player_id=g.id;p.faction_id=owner.id
    for n in owner.npcs:
        n.location_id=ENDPOINTS[source];n.realm_index=terms['maximum'];n.layer=1
        n.lifespan=n.age+999999;n.next_tribulation_age=n.age+999999
    organizations.register(g,'sect',owner.id,source)
    record=g.intrigue_state['factions']['sect:'+owner.id]
    record.update(resources=10**10*terms['scale'],controller_id='player')
    record.setdefault('positions',{})['leader']='player'
    depot.ensure(g,owner)['stock'].update({k:n*8 for k,n in runtime.materials(source).items()})
    add_item(p,'spirit_stone',10**6*terms['scale'])
    enemy=next(e for e in g.sects.values() if e.world==destination and e.kind=='sect' and e.npcs)
    site=next(loc for loc,_ in engine.maps._graphs[destination][ENDPOINTS[destination]] if not engine.maps.location(destination,loc).get('min_realm_index',0))
    enemy.location_id=site
    for n in enemy.npcs:
        n.location_id=ENDPOINTS[destination];n.realm_index=profile(destination)['minimum'];n.layer=1
        n.lifespan=n.age+999999;n.next_tribulation_age=n.age+999999
    enemy.npcs[0].location_id=site
    organizations.register(g,'sect',enemy.id,destination)
    g.intrigue_state['factions']['sect:'+enemy.id]['resources']=0
    initialize(g);engine.store.save(g)
    identity=target_for(owner.id,source,destination)
    deps=replace(engine._dependencies.heavens,load_game=engine.store.load,settle_activity_units=lambda *args,**kwargs:None)
    def advance(game,rng,news):
        runtime.year_step(deps,game)
        year_step(deps,game,YearContext(game.heavens_state['runtime']['last_year_key']+1))
        return True
    deps=replace(deps,advance_year=advance)
    def act(action,options=None):
        current=engine.store.load(game_id)
        return command(deps,game_id,current.heavens_state['command_seq']+1,current.heavens_state['revision'],action,identity,options or {})
    def ticks(years):
        current=engine.store.load(game_id)
        for _ in range(years):
            current.player.age+=1;runtime.year_step(deps,current)
        engine.store.save(current)
    act('outpost_authorize')
    for _ in range(2):
        current=engine.store.load(game_id)
        person=deps.outpost_candidates(current,current.sects[owner.id],destination)[0]['id']
        act('outpost_dispatch',dict(person_id=person))
    ticks(16);act('outpost_depart');ticks(10);act('outpost_return')
    current=engine.store.load(game_id);row=runtime.get(current,identity)
    assert current.player.world==source and row['status']=='active' and not row.get('military')
    return dict(id=identity,owner_id=owner.id,source=source,destination=destination,enemy_id=enemy.id,
                endpoint=ENDPOINTS[destination],site=site,terms=terms,
                people=[u['person_id'] for u in row['units']])


def inspect_heavens(engine,game_id,metadata,*,returned=False):
    from cultivation_life.system.heavens import outpost_runtime as runtime, outpost_conquest as conquest
    from cultivation_life.system.heavens.outpost_schema import validate_references
    g=engine.store.load(game_id);row=runtime.get(g,metadata['id']);validate_references(g)
    assert g.sects[metadata['owner_id']].world==metadata['source']
    assert g.player.world==(metadata['source'] if returned else metadata['destination'])
    if returned:
        assert row['visit']['status']=='returned' and not row['visit']['return_fare']
        assert conquest.current(g,row) is None
        war=conquest.wars(g,row)[-1]
        assert war['logistics']['sides']['attacker']['mobilized']==metadata['terms']['war_budget']
        assert all(g.world_npcs[i].world==metadata['destination'] and g.world_npcs[i].location_id==metadata['endpoint'] for i in metadata['people'])
    else:
        assert row['visit']['return_fare']==8*metadata['terms']['annual']
        assert row['status']=='active'
    return True
