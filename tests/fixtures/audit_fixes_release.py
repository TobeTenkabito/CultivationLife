"""Isolated release fixtures; all resulting actions use ordinary UI/API commands."""
def prepare_audit_fixes(engine, identity, case):
    from cultivation_life.models import SectNpc
    from cultivation_life.content_registry import REALMS
    from cultivation_life.rules import max_hp, max_mp
    from cultivation_life.system.upper_institutions import definition, account
    game=engine._load(identity)
    game.pending_event=None
    game.settings['silent_events']=True
    game.player.next_tribulation_age=None
    game.player.hp,game.player.mp=max_hp(game.player),max_mp(game.player)
    if case=='return':
        for role,realm in [('master',8),('disciple',1)]:
            npc=SectNpc('release-'+role,role,'',realm,1,30,9000,world='spirit',spirit_root='supreme_metal')
            game.notable_npcs[npc.id]=npc
            relation=game.link_relationship(dict(id=npc.id))
            if role=='master':game.player.master=relation
            else:game.player.disciples.append(relation)
        game.player.faction_id='taixuan'
        game.player.faction_contribution=1234
    elif case=='training':
        npc=SectNpc('release-trained','培养俘虏','',5,REALMS[5].layers,1000,1001,world='spirit',spirit_root='supreme_metal')
        game.notable_npcs[npc.id]=npc
        game.player.prisoners.append(game.detain_person(dict(id=npc.id,combat_power=100)))
        from cultivation_life.system.owned_training import quote
        game.player.opportunity=quote(game.player,game.player.prisoners[-1],'cultivation',1)['opportunity']+10
    else:
        game.player.location_id=definition(game)['location']
        state=account(game,create=True)
        state['joined']=True
        game.player.institution_affiliations[definition(game)['id']]=dict(joined_age=game.player.age)
        state['job']=dict(years=100,progress=40,reward=100)
    engine.store.save(game)


def inspect_audit_fixes(engine,identity,case):
    game=engine._load(identity)
    if case=='training':
        npc=game.notable_npcs.get('release-trained') or game.inactive_npcs['release-trained']
        assert npc.realm_index>=6 and npc.lifespan is None and npc.alive
    elif case=='return':
        assert game.player.world=='spirit' and game.player.faction_id=='taixuan'
        assert game.player.faction_contribution==1234 and game.player.master['id']=='release-master'
        assert game.player.disciples[0]['id']=='release-disciple' and game.player.realm_index==8
