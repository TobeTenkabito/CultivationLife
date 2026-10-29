"""Every same-tier directed pair uses original people, local wars and return."""
import copy
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item,max_hp,max_mp
from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.system.heavens import outposts,outpost_runtime as base,outpost_conquest as conquest
from cultivation_life.system.heavens.calendar import year_step,YearContext
from cultivation_life.system.heavens.state import initialize
from cultivation_life.system.heavens.outpost_routes import GROUPS,ENDPOINTS,SITE_NAMES,profile,peers,target_for
from cultivation_life.system.heavens.operations import command,preview
from cultivation_life.system.heavens.outpost_schema import validate_references,validate_outposts
from cultivation_life.system.economy import depot,organizations
from cultivation_life.system.economy.ledger import balance
from cultivation_life.system.territory import state as territory

ROOT=Path(__file__).resolve().parents[1]
PAIRS=[(a,b) for group in GROUPS for a in group for b in group if a!=b]


@pytest.fixture(scope='module')
def engine(tmp_path_factory):
    return GameEngine(ROOT,tmp_path_factory.mktemp('peer-worlds'))


@pytest.fixture(scope='module')
def origins(engine):
    result={}
    for group in GROUPS:
        for world in group:
            terms=profile(world)
            key=engine.create_game('同层开拓','supreme_metal','dao',7000+len(result),
                custom_start=dict(world=world,realm_index=terms['maximum'],layer=1))['id']
            g=engine.store.load(key);p=g.player
            p.location_id=ENDPOINTS[world];p.lifespan=None;p.next_tribulation_age=p.age+999999
            p.hp,p.mp=max_hp(p),max_mp(p)
            p.master,p.dao_companion,p.dao_friends,p.party=None,None,[],[]
            g.settings['silent_events']=True
            entity=next(e for e in g.sects.values() if e.world==world and e.kind=='sect' and len(e.npcs)>=2)
            entity.location_id=ENDPOINTS[world];entity.founded_by_player=True;entity.founder_player_id=key
            p.faction_id=entity.id
            for n in entity.npcs:
                n.location_id=ENDPOINTS[world];n.realm_index=terms['maximum'];n.layer=1;n.lifespan=n.age+999999;n.next_tribulation_age=n.age+999999
            organizations.register(g,'sect',entity.id,world)
            record=g.intrigue_state['factions']['sect:'+entity.id]
            record.update(resources=10**10*terms['scale'],controller_id='player')
            record.setdefault('positions',{})['leader']='player'
            store=depot.ensure(g,entity)
            for identity,qty in base.materials(world).items():store['stock'][identity]=qty*8
            add_item(p,'spirit_stone',10**6*terms['scale'])
            initialize(g)
            result[world]=(copy.deepcopy(g),entity.id)
    return result


def bundle_for(engine,origins,source,destination):
    original,owner=origins[source];g=copy.deepcopy(original)
    enemy=next(e for e in g.sects.values() if e.world==destination and e.kind=='sect' and e.npcs)
    # The existing organization and actual members occupy a legal neighboring
    # fixture headquarters; no gameplay movement, copy or alternate registry.
    site=next(loc for loc,_ in engine.maps._graphs[destination][ENDPOINTS[destination]] if not engine.maps.location(destination,loc).get('min_realm_index',0))
    enemy.location_id=site
    for n in enemy.npcs:
        n.location_id=ENDPOINTS[destination];n.realm_index=profile(destination)['minimum'];n.layer=1;n.lifespan=n.age+999999;n.next_tribulation_age=n.age+999999
    enemy.npcs[0].location_id=site
    organizations.register(g,'sect',enemy.id,destination)
    g.intrigue_state['factions']['sect:'+enemy.id]['resources']=0  # Real underfunded defense, never free war supplies.
    engine.store.save(g)
    deps=replace(engine._dependencies.heavens,load_game=engine.store.load,settle_activity_units=Mock())
    def advance(game,rng,news):
        base.year_step(deps,game)
        year_step(deps,game,YearContext(game.heavens_state['runtime']['last_year_key']+1))
        return True
    deps=replace(deps,advance_year=advance)
    return engine,g.id,deps,target_for(owner,source,destination),owner,enemy.id


def load(bundle):return bundle[0].store.load(bundle[1])


def act(bundle,action,options=None):
    g=load(bundle)
    return command(bundle[2],bundle[1],g.heavens_state['command_seq']+1,g.heavens_state['revision'],action,bundle[3],options or {})


def ticks(bundle,years,until=None):
    g=load(bundle);row=base.get(g,bundle[3])
    for _ in range(years):
        g.player.age+=1;base.year_step(bundle[2],g)
        if until and until(g,row):break
    bundle[0].store.save(g)
    return g,row


def establish(bundle):
    act(bundle,'outpost_authorize');act(bundle,'outpost_military_authorize')
    for _ in range(2):
        g=load(bundle);who=bundle[2].outpost_candidates(g,g.sects[bundle[4]],base.get(g,bundle[3])['destination'])[0]['id']
        act(bundle,'outpost_dispatch',dict(person_id=who))
    ticks(bundle,16)
    act(bundle,'outpost_depart')
    ticks(bundle,10)
    act(bundle,'outpost_develop')
    for _ in range(3):act(bundle,'outpost_invest')


@pytest.mark.parametrize('source,destination',PAIRS)
def test_every_peer_direction_establishes_fights_subjugates_and_returns(engine,origins,source,destination):
    bundle=bundle_for(engine,origins,source,destination);establish(bundle)
    g=load(bundle);row=base.get(g,bundle[3]);terms=profile(source)
    assert row['source']==source and row['destination']==destination and row['status']=='active'
    assert g.player.world==destination and g.sects[bundle[4]].world==source
    assert {k for k in row['stock']}==set(base.materials(source))
    assert row['visit']['return_fare']==8*terms['annual']
    worker=next(u['person_id'] for u in row['units'] if u['person_id']!=row['governor_id'])
    act(bundle,'outpost_war_start',dict(person_id=worker,rival_id=bundle[5]))
    g,row=ticks(bundle,160,lambda g,r:bool((w:=conquest.current(g,r)) and w.get('winner')=='attacker' and w['war_score']>=55))
    war=conquest.current(g,row)
    assert war and war['winner']=='attacker' and war['battles']>0 and war['war_score']>=55
    assert war['logistics']['sides']['attacker']['mobilized']==terms['war_budget']
    act(bundle,'outpost_war_vassal')
    g,row=ticks(bundle,60,lambda g,r:conquest.current(g,r) is None)
    assert conquest.current(g,row) is None and g.world_npcs[worker].location_id==ENDPOINTS[destination]
    from cultivation_life.world_state import race_pair
    assert g.sect_relations[race_pair(bundle[4],bundle[5])]['overlord']==bundle[4]
    assert g.sects[bundle[5]].world==destination
    validate_outposts(g.heavens_state['runtime']['outposts']);validate_references(g)
    act(bundle,'outpost_return')
    assert load(bundle).player.world==source


def test_routes_cover_exactly_the_seventeen_pairs_and_reviewed_endpoints(engine):
    routes=[r for r in WORLD_SYSTEMS['world_transition_routes'] if r['mode']=='expedition']
    assert len(PAIRS)==len(routes)==34
    assert {(r['source'],r['destination']) for r in routes}==set(PAIRS)
    for r in routes:
        assert r['source_location']==ENDPOINTS[r['source']] and r['destination_location']==ENDPOINTS[r['destination']]
        assert r['capacity']==1
        for w in (r['source'],r['destination']):
            site=engine.maps.location(w,ENDPOINTS[w]);assert site and not site.get('min_realm_index',0)
            assert site['name']==SITE_NAMES[w]


@pytest.mark.parametrize('source,destination',[('human','spirit'),('spirit','celestial'),('celestial','hell'),('spirit','lost')])
def test_cross_tier_and_spatial_targets_never_gain_an_outpost_permit(engine,origins,source,destination):
    original,owner=origins[source];g=copy.deepcopy(original);engine.store.save(g)
    deps=replace(engine._dependencies.heavens,load_game=engine.store.load)
    identity=target_for(owner,source,destination)
    path=engine.store._path(g.id);before=path.read_bytes()
    with pytest.raises(ValueError):command(deps,g.id,g.heavens_state['command_seq']+1,g.heavens_state['revision'],'outpost_authorize',identity,{})
    assert path.read_bytes()==before


def test_separate_destinations_have_separate_permits_and_free_original_people_can_redeploy(engine,origins):
    a=bundle_for(engine,origins,'spirit','true_demon');establish(a)
    g=load(a);row=base.get(g,a[3]);who=next(u['person_id'] for u in row['units'] if u['person_id']!=row['governor_id'])
    act(a,'outpost_recall',dict(person_id=who));ticks(a,8);act(a,'outpost_return');ticks(a,1)
    b=(*a[:3],target_for(a[4],'spirit','hell'),a[4],a[5])
    act(b,'outpost_authorize')
    act(b,'outpost_dispatch',dict(person_id=who))
    g=load(b);rows=g.heavens_state['runtime']['outposts']
    assert rows[a[3]]['destination']=='true_demon' and rows[b[3]]['destination']=='hell'
    assert next(u for u in rows[a[3]]['units'] if u['person_id']==who)['phase']=='home'
    assert next(u for u in rows[b[3]]['units'] if u['person_id']==who)['phase']=='outbound'
    assert base.wallet(rows[a[3]])!=base.wallet(rows[b[3]])
    validate_references(g)


def test_same_person_cannot_be_promised_to_two_destinations(engine,origins):
    a=bundle_for(engine,origins,'spirit','true_demon');act(a,'outpost_authorize')
    g=load(a);who=a[2].outpost_candidates(g,g.sects[a[4]],'true_demon')[0]['id']
    act(a,'outpost_dispatch',dict(person_id=who))
    b=(*a[:3],target_for(a[4],'spirit','hell'),a[4],a[5]);act(b,'outpost_authorize')
    path=engine.store._path(a[1]);before=path.read_bytes()
    with pytest.raises(ValueError):act(b,'outpost_dispatch',dict(person_id=who))
    assert path.read_bytes()==before


def test_independent_peer_lanes_progress_without_double_booking_and_retained_personal_return(engine,origins):
    from cultivation_life.person_assignments import outpost_lane_holder
    a=bundle_for(engine,origins,'spirit','true_demon');act(a,'outpost_authorize')
    b=(*a[:3],target_for(a[4],'spirit','hell'),a[4],a[5]);act(b,'outpost_authorize')
    who=[]
    for bundle,destination in [(a,'true_demon'),(b,'hell')]:
        g=load(bundle);person=a[2].outpost_candidates(g,g.sects[a[4]],destination)[0]['id'];who.append(person)
        act(bundle,'outpost_dispatch',dict(person_id=person))
    g=load(a)
    assert outpost_lane_holder(g,source='spirit',destination='true_demon')==who[0]
    assert outpost_lane_holder(g,source='spirit',destination='hell')==who[1]
    ticks(a,1);g=load(a)
    assert all(row['units'][0]['progress']==1 for row in g.heavens_state['runtime']['outposts'].values())
    ticks(a,7);act(a,'outpost_depart')
    before=copy.deepcopy(load(a).heavens_state['runtime']['outposts'][a[3]]['visit'])
    with pytest.raises(ValueError):act(b,'outpost_depart')
    assert load(a).heavens_state['runtime']['outposts'][a[3]]['visit']==before
    act(a,'outpost_return')
    assert load(a).player.world=='spirit'


def test_disabled_pair_and_insufficient_rank_fail_without_rng_or_cash_changes(engine,origins,monkeypatch):
    a=bundle_for(engine,origins,'celestial','asura')
    route=next(r for r in WORLD_SYSTEMS['world_transition_routes'] if r['id']=='expedition:celestial:asura')
    monkeypatch.setitem(route,'enabled',False)
    path=engine.store._path(a[1]);before=path.read_bytes()
    with pytest.raises(ValueError,match='未开放'):act(a,'outpost_authorize')
    assert path.read_bytes()==before
    monkeypatch.setitem(route,'enabled',True)
    for world in ('celestial','asura'):
        world_profile=WORLD_SYSTEMS['world_profiles'][world]
        monkeypatch.setitem(world_profile,'enabled',False)
        with pytest.raises(ValueError,match='未开放'):act(a,'outpost_authorize')
        assert path.read_bytes()==before
        monkeypatch.setitem(world_profile,'enabled',True)
    g=load(a);g.player.realm_index=8;engine.store.save(g);before=path.read_bytes()
    with pytest.raises(ValueError,match='修为'):act(a,'outpost_authorize')
    assert path.read_bytes()==before


@pytest.mark.parametrize('source,destination',[('spirit','true_demon'),('celestial','asura')])
def test_upper_tier_expansion_builds_consumes_original_materials_and_exports_scaled_cash(engine,origins,source,destination):
    from cultivation_life.system.heavens import outpost_development as development
    bundle=bundle_for(engine,origins,source,destination);establish(bundle)
    g=load(bundle);row=base.get(g,bundle[3]);terms=profile(source)
    original=copy.deepcopy(g.to_dict())
    outposts.project(bundle[2],g)
    assert g.to_dict()==original
    worker=development.workers(bundle[2],g,row)[0]['id']
    place=next(p['id'] for p in development.project(bundle[2],g,row,row['id'])['locations']
               if p['id']!=ENDPOINTS[destination] and any(a['action']=='outpost_expand' and a['enabled'] for a in p['actions']))
    options=dict(person_id=worker,location_id=place)
    plan=development.job_plan(bundle[2],g,row,'outpost_expand',options)
    quoted=development.quote(bundle[2],g,row,'outpost_expand',options)
    assert quoted['costs']['organization_stones']==1000*terms['scale']+(plan['outward']['years']+plan['homeward']['years'])*terms['annual']
    act(bundle,'outpost_expand',options)
    def ended(g,r):return all(u.get('local_job',{}).get('status')!='active' for u in r['units'])
    g,row=ticks(bundle,120,ended)
    unit=next(u for u in row['units'] if u['person_id']==worker)
    assert unit['local_job']['result']=='expanded' and unit['local_job']['fee_spent']==1000*terms['scale']
    original_stock=dict(row['stock'])
    act(bundle,'outpost_build_site',options)
    g=load(bundle);row=base.get(g,bundle[3])
    assert all(row['stock'][k]==original_stock[k]-n for k,n in base.materials(source).items())
    g,row=ticks(bundle,120,ended)
    unit=next(u for u in row['units'] if u['person_id']==worker)
    assert unit['local_job']['result']=='built' and unit['local_job']['fee_spent']==10000*terms['scale']
    assert territory.snapshot(g,engine.maps,destination)[place][bundle[4]]['outpost']
    assert g.world_npcs[worker].location_id==ENDPOINTS[destination]
    before=balance(g,base.wallet(row));home=balance(g,'organization:sect:'+bundle[4]);personal=balance(g,'player')
    act(bundle,'outpost_export',dict(person_id=worker))
    g=load(bundle);row=base.get(g,bundle[3])
    assert balance(g,base.wallet(row))==before-terms['transfer']
    assert balance(g,'organization:sect:'+bundle[4])==home and balance(g,'player')==personal
    ticks(bundle,8);act(bundle,'outpost_return');g,row=ticks(bundle,1)
    assert next(u for u in row['units'] if u['person_id']==worker)['phase']=='home'
    assert balance(g,'organization:sect:'+bundle[4])>=home+terms['transfer']
    validate_references(g)


def test_pair_stock_rejects_third_world_and_lower_grade_and_metadata_matches_content(engine,origins):
    bundle=bundle_for(engine,origins,'celestial','asura');establish(bundle)
    rows=load(bundle).heavens_state['runtime']['outposts']
    for item in ('item:econ_nether_9_ore_structure','item:econ_celestial_2_ore_structure'):
        malformed=copy.deepcopy(rows);malformed[bundle[3]]['stock'][item]=1
        with pytest.raises(ValueError):validate_outposts(malformed)
    from cultivation_life.system.territory.rules import COSTS
    for world in ENDPOINTS:
        terms=profile(world)
        assert WORLD_SYSTEMS['world_profiles'][world]['tier']==terms['tier']
        assert COSTS[terms['tier']]['grade']==terms['grade']
        assert COSTS[terms['tier']]['outpost']==terms['build_cost']


def test_sect_and_family_share_one_whole_year_slot_for_the_same_pair(engine,origins):
    source,destination='spirit','true_demon'
    a=bundle_for(engine,origins,source,destination);act(a,'outpost_authorize')
    g=load(a);person=a[2].outpost_candidates(g,g.sects[a[4]],destination)[0]['id']
    act(a,'outpost_dispatch',dict(person_id=person));ticks(a,7)
    g=load(a)
    assert g.family is None
    # One other original organization becomes this fixture's original family;
    # the actual people are retained, never copied into another roster.
    family=next(e for e in g.sects.values() if e.world==source and e.id!=a[4] and e.npcs)
    g.sects.pop(family.id);g.family=family;family.kind='family'
    family.location_id=ENDPOINTS[source];family.founded_by_player=True;family.founder_player_id=g.id
    for npc in family.npcs:
        npc.location_id=ENDPOINTS[source];npc.realm_index=profile(source)['maximum'];npc.layer=1
    organizations.register(g,'family',family.id,source)
    g.intrigue_state['factions']['family:'+family.id].update(resources=10**9,controller_id='player')
    depot.ensure(g,family)['stock'].update(base.materials(source))
    engine.store.save(g)
    b=(*a[:3],target_for(family.id,source,destination),family.id,a[5]);act(b,'outpost_authorize')
    g=load(b);second=b[2].outpost_candidates(g,g.family,destination)[0]['id']
    act(b,'outpost_dispatch',dict(person_id=second))
    g,row=ticks(a,1)
    assert row['units'][0]['phase']=='stationed'
    assert base.get(g,b[3])['units'][0]['phase']=='outbound'
    assert base.get(g,b[3])['units'][0]['progress']==0
    ticks(a,7);assert base.get(load(a),b[3])['units'][0]['progress']==7
    ticks(a,1);g=load(a)
    assert g.world_npcs[person].world==g.world_npcs[second].world==destination
    assert g.family.id==family.id and g.family.world==source
    validate_references(g)
