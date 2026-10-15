"""Fresh isolated release games only; actions are executed by the built product."""
import copy
import random


def prepare_followup(engine, identity, case):
    from cultivation_life.models import SectNpc, SectState
    from cultivation_life.rules import add_item
    from cultivation_life.system.economy import organizations
    from cultivation_life.system.economy.ledger import transfer_value
    game=engine._load(identity)
    game.pending_event=None
    game.settings['silent_events']=True
    game.player.next_tribulation_age=None
    if case=='inheritance':
        from cultivation_life.content_registry import WORLD_SYSTEMS
        from cultivation_life.system.spirit_voisinage import catalog, grant
        from cultivation_life.system.spirit_sources import origin
        from cultivation_life.system.crafting_system import crafting_material_definitions, make_crafting_material_instance
        p=game.player
        p.opportunity=10**10;p.immortal_traces=10000
        add_item(p,'spirit_stone',10**8)
        book=next(b for b in catalog(game).values() if origin(b.spirit_voisinage_id)=='asura')
        grant(game,book.id,9)
        if p.world!='celestial':
            definition=crafting_material_definitions()[WORLD_SYSTEMS['upper_voisinages']['worlds'][p.world]['material_id']]
            p.crafting_materials.append(make_crafting_material_instance(definition,random.Random(1),source='隔离发行验收',origin_world=p.world))
        if p.path=='demonic':
            p.asura_cultivation.update(route='yaksha',conversion=5,souls=10000,level=4,domain_rank=3,domain_power=2,domain_name='本命')
        elif p.path=='monster':
            from cultivation_life.system import monster_true_form as form
            p.monster_evolution_id='SERPENT_NETHER_TRUE_1'
            form.configure(p,'true_form_confirm',form.public(p)['choices'][0])
        elif p.path=='ghost':
            from cultivation_life.system import ghost_soul_form as form
            cause,route=next(iter(form.catalog()['forms'])).split('.')
            form.confirm(game,cause,route)
        engine.store.save(game)
        return book.id
    member=SectNpc('followup_member','验收门人','弟子',3,1,20,100000,
        world='human',location_id=game.player.location_id,spirit_root='supreme_water',affinity=80,faction_id='followup_org')
    game.sects['followup_org']=SectState('followup_org','发行验收宗','human',[member],kind='sect',
        founded_by_player=True,founder_player_id=game.id,location_id=game.player.location_id)
    game.player.faction_id='followup_org'
    organizations.register(game,'sect','followup_org','human')
    transfer_value(game,'background:human',organizations.key('sect','followup_org'),1000000,'隔离发行验收预算')
    if case=='guard':
        from cultivation_life.system.formation_system import formation_material_definitions, make_formation_material_instance
        definitions=formation_material_definitions()
        for key in ('human_greenwood_stake','human_red_sun_sand','human_xuanyin_stone'):
            game.player.formation_materials.append(make_formation_material_instance(definitions[key],source='隔离发行验收',origin_world='human'))
    engine.store.save(game)


def prepare_guard_defense(engine,identity):
    from cultivation_life.content_registry import CONTENT_DOCUMENTS
    game=engine._load(identity)
    assert game.player.formation_ground_arrays[0]['location_id']!=game.sects['followup_org'].location_id
    event=copy.deepcopy(CONTENT_DOCUMENTS['player_faction_events.json']['events'][0])
    event['runtime']=dict(sect_id='followup_org',required_power=1,stage=1)
    game.pending_event=event
    engine.store.save(game)


def inspect_followup(engine,identity,case):
    game=engine._load(identity)
    if case=='guard':
        array=game.player.formation_ground_arrays[0]
        assert array['battles']==0 and array['durability']==100
        assert array['location_id']!=game.sects['followup_org'].location_id
        assert game.sects['followup_org'].pressure==1
    elif case=='production':
        assert 'followup_member' in game.intrigue_state['npc_prisons']
        row=game.economy_v2['organizations']['organization:sect:followup_org']
        assert row['labor_capacity']==row['produced']==row['turnover']==0, {
            'age':game.player.age,'workforce':row.get('workforce'),
            'labor':row.get('labor_capacity'),'produced':row.get('produced'),'income':row.get('income'),
            'members':[(n.id,n.realm_index) for n in game.sects['followup_org'].npcs]}
        # Territory shares settle after production from real local operator funds;
        # they remain lawful income when the only production worker is jailed.
        assert row['income']==row.get('territory_income',0), row
        assert row['expected_upkeep']>0
    elif case=='supply':
        from cultivation_life.system.war.requirements import groups
        war=next(w for w in game.wars if w['attacker_id']=='followup_org')
        assert 3 not in groups(game,war,'attacker')
        row=war['logistics']['sides']['attacker']
        market=game.economy_v2['markets']['human:'+row['location']]
        assert not any(n and market['commodities'][k]['tier']==3 for k,n in row['consumed_items'].items())
    elif case=='inheritance':
        p=game.player
        if p.world=='celestial':assert game.doctrine_state['player']['spirit_inheritances']
        elif p.path=='demonic':assert p.asura_cultivation['spirit_inheritance'] and p.asura_cultivation['domain_rank']==3
        elif p.path in {'monster','ghost'}:
            assert p.world_voisinages[p.world]['spirit_bindings']
        else:assert p.world_voisinages[p.world]['spirit_inheritances']
