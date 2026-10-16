"""Fresh release-only initial states; the built product executes every command."""
import random


def prepare_strategic_release(engine, identity):
    from cultivation_life.engine.composition.strategic_war import bind
    from cultivation_life.system.strategic_war import lifecycle, dispatch
    from cultivation_life.race_diplomacy import relations_for
    from cultivation_life.system.economy import depot
    from cultivation_life.system.economy.ledger import balance
    game=engine._load(identity)
    game.pending_event=None;game.settings['silent_events']=True
    game.player.next_tribulation_age=None;game.player.lifespan=None
    game.player.faction_id='taixuan';game.sects['taixuan'].founded_by_player=True
    deps=bind(engine);row=lifecycle.start(deps,game,'human','woodborn')
    relations_for(game)['human|woodborn']=dict(status='war',affinity=-75)
    lifecycle.commit(deps,game,row,game.sects['taixuan'])
    row['commanders']['attacker']=dict(person_id='player',name=game.player.name,expires=game.player.age+100,votes=3,electorate=3)
    game.player.age+=1;lifecycle.advance(deps,game,random.Random(641))
    for child in game.wars:
        if child.get('strategic_war_id')!=row['id'] or child['attacker_id']!='taixuan':continue
        for org in game.sects.values():
            if org.world!=row['world'] or org.allegiance_race!=row['attacker']:continue
            try:side,journeys,route,cost=dispatch.plan(deps,game,row,child,org)
            except ValueError:continue
            engine._strategic_release_info=dict(identity=identity,campaign=child['id'],org=org.id,cost=cost,
                original_cash=balance(game,depot.treasury(game,org)))
            engine.store.save(game)
            return
    raise AssertionError('No actual approved reserve for native release acceptance')


def inspect_strategic_release(engine, identity):
    from cultivation_life.system.economy import depot
    from cultivation_life.system.economy.ledger import balance
    game=engine._load(identity);expected=engine._strategic_release_info
    assert expected['identity']==identity
    child=next(w for w in game.wars if w['id']==expected['campaign'])
    reinforcement=next(r for r in child['reinforcements'] if r['org']['id']==expected['org'])
    org=game.sects[expected['org']]
    assert balance(game,depot.treasury(game,org))==expected['original_cash']-expected['cost']
    assert balance(game,reinforcement['wallet'])==expected['cost']
    assert child['status']=='active' and reinforcement['paid']==expected['cost']
    assert not reinforcement['delivered'] and all(j['phase'] in {'outbound','stationed'}
        for j in child['journeys']['attacker'] if child['roster_owner'][j['person_id']]==org.id)
