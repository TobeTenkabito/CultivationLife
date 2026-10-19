"""Eleven-world city content and actual finite event / project submissions."""
import copy
import pytest

from test_building_system import local, choose, construct, stable_time
from cultivation_life.content_registry import WORLD_SYSTEMS, CONTENT_DOCUMENTS, ContentError, ContentRegistry
from cultivation_life.models import GameState
from cultivation_life.building_schema import address
from cultivation_life.building_rules import config, initial_rows, describe, qi_multiplier, ensure_state
from cultivation_life.rules import add_item, remove_item, max_hp, max_mp
from cultivation_life.system import buildings
from cultivation_life.system.building_projects import quote
from cultivation_life.system.building_destruction import war_damage
from cultivation_life.system.economy.ledger import balance

WORLDS=list(config()['cities'])


def commit(engine,game_id,prefix):
    shown=engine.get_game(game_id)
    selected=next(c['id'] for c in shown['pending_event']['choices'] if c['id'].startswith(prefix))
    return engine.choose(game_id,selected,event_id=shown['pending_event']['id'])


def fund_city(engine,game):
    add_item(game.player,'spirit_stone',10**14)
    for key in quote(game,'city')['materials']:add_item(game.player,key,100000)
    engine.store.save(game)


def build_city(engine,game,kind='economic',population='mixed'):
    engine.building_action(game.id,'city-plan')
    choose(engine,game.id,'city:'+kind)
    choose(engine,game.id,f'city:{kind}:{population}')
    commit(engine,game.id,'city:build:')
    return engine.store.load(game.id)


@pytest.mark.parametrize('world',WORLDS)
def test_two_unique_initial_cities_and_real_story_claims_in_every_world(tmp_path,world):
    from cultivation_life.engine import GameEngine
    from pathlib import Path
    engine=GameEngine(Path(__file__).resolve().parents[1],tmp_path)
    tier=WORLD_SYSTEMS['world_profiles'][world]['tier']
    created=engine.create_game('城中行客','supreme_metal','dao',2170,
        custom_start=dict(world=world,realm_index={1:3,2:6,3:9}[tier]))
    game=engine._load(created['id']);game.pending_event=None;engine.store.save(game)
    shown=engine.get_game(game.id)
    all_rows=[r for p in shown['map']['locations'] for r in p['buildings']]
    assert len([r for r in all_rows if r['type']=='city'])==4
    assert len([r for r in all_rows if r['type']=='scenery'])>=1
    assert not game.building_state
    for spec in config()['cities'][world]:
        game=engine.store.load(game.id);game.player.location_id=spec['location_id'];engine.store.save(game)
        engine.get_game(game.id);game=engine.store.load(game.id)
        before=stable_time(game)
        city=next(r for r in buildings.local_rows(game) if r['type']=='city')
        engine.building_action(game.id,'enter',building_id=city['id'])
        choose(engine,game.id,'city:audience');choose(engine,game.id,'city:audience:listen')
        choose(engine,game.id,'city:audience');choose(engine,game.id,'back')
        rumors=choose(engine,game.id,'city:rumor')
        assert spec['rumor'] in rumors['pending_event']['body']
        choose(engine,game.id,'back')
        story=choose(engine,game.id,'city:story')
        assert spec['story']['body'] in story['pending_event']['body']
        choose(engine,game.id,'city:resolve:0');choose(engine,game.id,'back')
        old=engine.get_game(game.id);snapshot=engine.store.load(game.id).to_dict()
        choose(engine,game.id,'city:story')
        shown=engine.get_game(game.id)
        assert not next(c for c in shown['pending_event']['choices'] if c['id']=='city:resolve:1')['enabled']
        with pytest.raises(ValueError):choose(engine,game.id,'city:resolve:1')
        assert engine.store.load(game.id).player.opportunity==snapshot['player']['opportunity']
        choose(engine,game.id,'leave')
        assert stable_time(engine.store.load(game.id))==before
    identities=[s['story']['title'] for rows in config()['cities'].values() for s in rows]
    assert len(identities)==len(set(identities))==44


def test_city_construction_consumes_actual_materials_and_starts_at_one(local):
    engine,game=local
    fund_city(engine,game)
    before=engine.store.load(game.id)
    required=quote(before,'city')
    game=build_city(engine,game,'military','mortal')
    row=next(r for r in game.building_state['records'].values() if r['type']=='city')
    assert row['level']==1 and row['population']=='mortal' and row['subtype']=='military'
    assert stable_time(before)==stable_time(game)
    held={i.id:i.quantity for i in game.player.inventory}
    old={i.id:i.quantity for i in before.player.inventory}
    for key,n in required['materials'].items():assert old[key]-held[key]==n
    assert balance(before,'player')-balance(game,'player')==required['coins']
    assert '凡人之城' in describe(row) and '护城大阵' not in describe(row)
    choose(engine,game.id,'leave')
    engine.building_action(game.id,'city-plan');choose(engine,game.id,'city:economic')
    shown=choose(engine,game.id,'city:economic:mixed')
    assert not shown['pending_event']['choices'][0]['enabled']
    with pytest.raises(ValueError):commit(engine,game.id,'city:build:')


def test_city_build_failure_and_stale_plan_never_charge(local):
    engine,game=local
    fund_city(engine,game)
    engine.building_action(game.id,'city-plan');choose(engine,game.id,'city:economic')
    shown=choose(engine,game.id,'city:economic:mixed')
    old=shown['pending_event']
    game=engine.store.load(game.id)
    key=next(iter(quote(game,'city')['materials']))
    remove_item(game.player,key,100000);engine.store.save(game)
    before=engine.store.load(game.id).to_dict()
    with pytest.raises(ValueError):engine.choose(game.id,old['choices'][0]['id'],event_id=old['id'])
    assert not engine.store.load(game.id).building_state['records']
    assert engine.store.load(game.id).player.inventory==GameState.from_dict(before).player.inventory


def test_civic_progress_requires_real_year_and_upgrade_one_level(local):
    engine,game=local;fund_city(engine,game);build_city(engine,game)
    for index in range(6):
        choose(engine,game.id,'city:govern');commit(engine,game.id,'city:commit:')
        if index==0:
            disabled=choose(engine,game.id,'city:govern')
            assert not disabled['pending_event']['choices'][0]['enabled']
            with pytest.raises(ValueError):commit(engine,game.id,'city:commit:')
            choose(engine,game.id,'back')
            choose(engine,game.id,'leave')
            saved=engine.store.load(game.id);saved.settings['silent_events']=True;saved.player.next_tribulation_age=None;engine.store.save(saved)
            engine.advance(game.id,'rest',1)
            saved=engine.store.load(game.id)
            row=next(r for r in saved.building_state['records'].values() if r['type']=='city')
            engine.building_action(game.id,'enter',building_id=row['id'])
        elif index<5:
            saved=engine.store.load(game.id);saved.player.age+=1;engine.store.save(saved)
    choose(engine,game.id,'city:develop');commit(engine,game.id,'city:commit:')
    saved=engine.store.load(game.id);row=next(r for r in saved.building_state['records'].values() if r['type']=='city')
    assert row['level']==2 and row['development']==0
    shown=choose(engine,game.id,'city:develop')
    assert not shown['pending_event']['choices'][0]['enabled']


def test_destroy_rebuild_city_keeps_identity_owner_and_claims(local):
    engine,game=local;fund_city(engine,game);build_city(engine,game)
    choose(engine,game.id,'city:story');choose(engine,game.id,'city:resolve:1');choose(engine,game.id,'back')
    before=engine.store.load(game.id);row=next(r for r in before.building_state['records'].values() if r['type']=='city')
    choose(engine,game.id,'management');choose(engine,game.id,'destroy')
    commit(engine,game.id,'destroy:')
    ruined=engine.get_game(game.id)
    assert any(r['id']==row['id'] and r['name'].endswith('遗址') for r in ruined['buildings']['rows'])
    choose(engine,game.id,'rebuild');commit(engine,game.id,'rebuild:')
    choose(engine,game.id,'back')
    shown=choose(engine,game.id,'city:story')
    assert not shown['pending_event']['choices'][0]['enabled']
    after=engine.store.load(game.id)
    assert after.building_state['records'][row['id']]['owner']==row['owner']
    assert after.building_state['records'][row['id']]['level']==1
    assert after.building_state['city_usage']==before.building_state['city_usage']


def test_cave_destroy_rebuild_and_no_discount_bypass(local):
    engine,game=local;construct(engine,game)
    choose(engine,game.id,'management');choose(engine,game.id,'destroy');commit(engine,game.id,'destroy:')
    assert engine.get_game(game.id)['buildings']['qi_multiplier']==1
    choose(engine,game.id,'leave')
    engine.building_action(game.id,'construct');choose(engine,game.id,'level:2')
    assert not engine.get_game(game.id)['pending_event']['choices'][0]['enabled']
    choose(engine,game.id,'leave')
    game=engine.store.load(game.id);row=next(iter(game.building_state['records'].values()))
    before=balance(game,'player')
    engine.building_action(game.id,'manage',building_id=row['id']);choose(engine,game.id,'rebuild');commit(engine,game.id,'rebuild:')
    game=engine.store.load(game.id)
    assert before-balance(game,'player')==800 and qi_multiplier(game.player)==1.04


def test_natural_scenery_never_rewards_or_destroys(local):
    engine,game=local
    spec=config()['scenery'][game.player.world][0]
    game.player.location_id=spec['location_id'];engine.store.save(game);engine.get_game(game.id)
    game=engine.store.load(game.id)
    row=next(r for r in buildings.local_rows(game) if r['type']=='scenery')
    assert row['owner']['kind']=='none'
    baseline=(stable_time(game),game.player.to_dict())
    for _ in range(3):
        engine.building_action(game.id,'enter',building_id=row['id'])
        choose(engine,game.id,'details');choose(engine,game.id,'back');choose(engine,game.id,'leave')
    after=engine.store.load(game.id)
    assert (stable_time(after),after.player.to_dict())==baseline
    engine.building_action(game.id,'manage',building_id=row['id'])
    assert not engine.get_game(game.id)['pending_event']['choices'][0]['enabled']
    with pytest.raises(ValueError):choose(engine,game.id,'destroy')


def test_real_arena_uses_original_battle_and_finite_attempts(local):
    engine,game=local
    city=next(r for r in buildings.local_rows(game) if r['type']=='city')
    engine.building_action(game.id,'enter',building_id=city['id'])
    before=engine.store.load(game.id).player.age
    for _ in range(3):
        choose(engine,game.id,'city:arena')
        saved=engine.store.load(game.id);saved.player.hp=max_hp(saved.player);saved.player.mp=max_mp(saved.player);engine.store.save(saved)
        choose(engine,game.id,'city:fight');choose(engine,game.id,'back')
    shown=choose(engine,game.id,'city:arena')
    assert not shown['pending_event']['choices'][0]['enabled']
    with pytest.raises(ValueError):choose(engine,game.id,'city:fight')
    saved=engine.store.load(game.id)
    assert saved.player.age==before and saved.building_state['city_usage'][city['id']]['arena']==3
    assert saved.player.alive


def test_war_damage_only_once_and_never_destroys_city_or_scenery(local,monkeypatch):
    engine,game=local;game=construct(engine,game);choose(engine,game.id,'leave')
    game=engine.store.load(game.id)
    monkeypatch.setitem(config(),'war_destruction_chance',1)
    war=dict(id='actual-battle',world=game.player.world,location_id=game.player.location_id,battles=1)
    rng=game.rng_state
    engine._wear_war_guard_arrays(game,war)
    assert next(iter(game.building_state['records'].values()))['status']=='destroyed'
    assert all(r['status']=='intact' for r in buildings.local_rows(game) if r['type']=='city')
    before=copy.deepcopy(game.to_dict());war_damage(game,war)
    assert game.to_dict()==before and game.rng_state==rng
    assert war['building_damage_round']==1


def test_industry_destruction_pauses_paid_job_and_preserves_original_wealth(local):
    from test_economy_enterprises import buy,estate_act,configure
    from cultivation_life.system.economy.enterprise_operations import advance_estates
    engine,game=local
    game,identity=buy(engine,game,'mine')
    game=estate_act(engine,game,identity,'fund',amount=10000)
    game=configure(engine,game,identity);game=estate_act(engine,game,identity,'start')
    original=copy.deepcopy(game.economy_v2['estates'][identity])
    engine.building_action(game.id,'manage',building_id='estate:'+identity)
    choose(engine,game.id,'destroy');commit(engine,game.id,'destroy:');choose(engine,game.id,'leave')
    saved=engine.store.load(game.id)
    saved.player.age+=3;advance_estates(saved,engine.maps);engine.store.save(saved)
    damaged=saved.economy_v2['estates'][identity]
    assert damaged['stock']==original['stock'] and damaged['reserve']==original['reserve'] and damaged['job']==original['job']
    with pytest.raises(ValueError):estate_act(engine,saved,identity,'start')
    engine.building_action(game.id,'manage',building_id='estate:'+identity)
    choose(engine,game.id,'rebuild');commit(engine,game.id,'rebuild:')
    repaired=engine.store.load(game.id).economy_v2['estates'][identity]
    assert repaired['job']['finish']==original['job']['finish']+3
    assert repaired['stock']==original['stock'] and repaired['reserve']==original['reserve']


def test_corrupt_new_city_content_rejected_before_gameplay():
    documents=copy.deepcopy(CONTENT_DOCUMENTS)
    documents['world.json']['systems']['building_system']['cities']['human'][0]['location_id']='nonexistent'
    with pytest.raises(ContentError):ContentRegistry._from_documents(documents)


def test_updated_catalog_cannot_duplicate_or_remotely_project_existing_city(local,monkeypatch):
    engine,game=local
    place=address(game)
    row=next(r for r in initial_rows(place) if r['type']=='city')
    ensure_state(game)['records'][row['id']]=copy.deepcopy(row)
    remote=next(p['id'] for p in engine.maps.worlds[game.player.world]['locations'] if p['id']!=place['location_id'])
    monkeypatch.setitem(config()['cities'][game.player.world][0],'location_id',remote)
    assert any(r['id']==row['id'] for r in buildings.rows_at(game,place))
    assert not any(r['id']==row['id'] for r in buildings.rows_at(game,dict(place,location_id=remote)))


def test_temple_destroy_rebuild_uses_original_site_and_preserves_followers(local,monkeypatch):
    from cultivation_life.system.buddhist.rules import buddhist_config
    engine,game=local
    monkeypatch.setitem(buddhist_config(),'enabled',True)
    game.player.path='buddhist';engine.store.save(game)
    engine.building_action(game.id,'temple-plan');choose(engine,game.id,'confirm')
    choose(engine,game.id,'temple');choose(engine,game.id,'temple:upgrade');choose(engine,game.id,'back')
    game=engine.store.load(game.id)
    original=copy.deepcopy(game.buddhist_state['worlds'][game.player.world]['sites'][game.player.location_id])
    choose(engine,game.id,'management');choose(engine,game.id,'destroy');commit(engine,game.id,'destroy:')
    damaged=engine.store.load(game.id)
    site=damaged.buddhist_state['worlds'][game.player.world]['sites'][game.player.location_id]
    assert site['temple']==0 and site['temple_ruin_level']==2 and site['followers']==original['followers']
    choose(engine,game.id,'rebuild');commit(engine,game.id,'rebuild:')
    saved=engine.store.load(game.id)
    site=saved.buddhist_state['worlds'][game.player.world]['sites'][game.player.location_id]
    assert site['temple']==1 and 'temple_ruin_level' not in site and site['followers']==original['followers']
    assert not saved.building_state['records']


def test_real_http_existing_spatial_and_trial_actions_survive_building_read_guard(local,monkeypatch):
    import json
    import threading
    import urllib.request
    import urllib.error
    from http.server import ThreadingHTTPServer
    from cultivation_life import server
    from cultivation_life.system import trial_sites
    engine,game=local
    class Handler(server.Handler):
        def log_message(self,*args):pass
    monkeypatch.setattr(server,'ENGINE',engine)
    httpd=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=httpd.serve_forever,daemon=True).start()
    def post(identity,operation,payload):
        request=urllib.request.Request(f'http://127.0.0.1:{httpd.server_port}/api/games/{identity}/{operation}',
            data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=30) as response:return json.load(response)
    try:
        lost=engine.create_game('空间准入','supreme_metal','dao',250,preset_id='lost_world')
        with pytest.raises(urllib.error.HTTPError):post(lost['id'],'building-action',dict(action='city-plan'))
        sect=lost['spatial']['scene']['society']['sects'][0]
        joined=post(lost['id'],'spatial-action',dict(action='join_sect',target_id=sect['id']))
        assert joined['spatial']['scene']['joined_sect']==sect['id']
        saved=engine.store.load(game.id)
        site=trial_sites.bound_site(saved,engine.maps,saved.player.world)
        saved.player.location_id=site['location_id'];saved.pending_event=None;engine.store.save(saved)
        entered=post(game.id,'trial-site-action',dict(action='enter',world=saved.player.world,floor=1))
        expected=entered['pending_event']['id']
        with pytest.raises(urllib.error.HTTPError):post(game.id,'building-action',dict(action='city-plan'))
        assert engine.get_game(game.id)['pending_event']['id']==expected
        saved=engine.store.load(game.id);_,floor=trial_sites.current(saved)
        paused=post(game.id,'trial-site-action',dict(action='pause',floor_id=floor['id'],revision=floor['revision']))
        assert not paused['trial_site']['active']
    finally:httpd.shutdown();httpd.server_close()
