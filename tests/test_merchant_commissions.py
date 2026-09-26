import copy
import json
import random
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item
from cultivation_life.system.formation_system import calculate_formation_profile, formation_alpha, make_formation_material_instance


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def setup(tmp_path):
    engine = GameEngine(ROOT, tmp_path)
    game_id = engine.create_game('委托验收', 'heavenly', 'dao', 1360, preset_id='core')['id']
    game = engine._load(game_id)
    alliance = game.merchant_state['worlds']['human'][0]
    game.player.location_id = alliance['hq']
    add_item(game.player, 'spirit_stone', 10**12)
    engine.store.save(game)
    engine.merchant_action(game_id, 'join', {'alliance_id':alliance['id']})
    return engine, engine._load(game_id), alliance


def complete(engine, game):
    order = game.merchant_state['posted'][-1]
    order.update(status='working',worker='验收工匠',started_age=game.player.age,
                 finish_age=game.player.age+1,will_finish=True)
    game.player.age += 1
    engine._advance_merchant_year(game)
    assert order['status'] == 'completed'
    return order


def test_formation_material_category_delivers_unique_instances(setup):
    engine, game, alliance = setup
    definition = next(row for row in engine._formation_material_defs().values() if row['world']=='human')
    engine._merchant_post(game,alliance,{'kind':'supply','material_category':'formation','definition_id':definition['id'],'quantity':3})
    complete(engine,game)
    received = [row for row in game.player.formation_materials if row['material_id']==definition['id']]
    assert len(received)==3 and len({row['id'] for row in received})==3
    assert not game.player.crafting_materials


def test_supply_board_material_categories_consume_correct_bag(setup):
    engine, game, alliance = setup
    task = next(row for row in engine._merchant_board(game,alliance) if row['kind']=='supply' and row.get('material_category')=='formation')
    definition=engine._formation_material_defs()[task['definition_id']]
    game.player.formation_materials.append(make_formation_material_instance(definition,source='test',origin_world='human'))
    engine.store.save(game)
    engine.merchant_action(game.id,'accept',{'task_id':task['id']})
    with patch.object(engine,'_advance_world_year',return_value=True):
        engine.merchant_action(game.id,'work')
    saved=engine._load(game.id)
    assert not saved.player.formation_materials
    assert saved.player.crafting_materials and saved.merchant_state['active'] is None


def test_jinque_local_delivery_and_no_unlinked_targets(setup):
    engine, game, local = setup
    payload={'kind':'item','source_world':'human','definition_id':'jinque_metal','quantity':2}
    engine._merchant_post(game,local,payload)
    complete(engine,game)
    assert next(row for row in game.player.inventory if row.id=='jinque_metal').quantity==2
    game.player.world='true_demon'
    for key in ('jiukun', 'xuanji'):
        alliance=engine._merchant_alliance(game,'true_demon',key)
        with pytest.raises(ValueError, match='分总部'):
            engine._merchant_quote(game,alliance,payload)
        assert 'human' not in {row['world'] for row in engine._merchant_procurement_catalog(game,alliance)}


@pytest.mark.parametrize('payload',[
    {'kind':'item','definition_id':'spirit_stone'},
    {'kind':'item','source_world':'spirit','definition_id':'jinque_metal'},
    {'kind':'supply','material_category':'bad','definition_id':'human_cold_iron'},
    {'kind':'weapon','material_tier':12},
    {'kind':'weapon','mold_id':'forged-client-mold'},
    {'kind':'formation','material_tier':12},
    {'kind':'formation','metrics':{'kill':float('nan')}},
    {'kind':'formation','metrics':{'kill':float('inf')}},
    {'kind':'formation','metrics':{'balance':101}},
    {'kind':'formation','metrics':{'growth':100,'kill':100}},
])
def test_invalid_contracts_never_charge_or_create_order(setup,payload):
    engine,game,alliance=setup
    before=copy.deepcopy(game.to_dict())
    with pytest.raises(ValueError):
        engine._merchant_post(game,alliance,payload)
    assert game.to_dict()==before


def test_formation_preview_constraints_and_frozen_delivery(setup):
    engine,game,alliance=setup
    payload={'kind':'formation','material_tier':2,'alliance_id':alliance['id']}
    quote=engine.preview_merchant_commission(game.id,payload)
    spec=quote['spec']
    assert all(0<=value<=100 for value in spec['limits'].values())
    payload['metrics']=dict(spec['profile']['metrics'])
    quote=engine._merchant_quote(game,alliance,payload)
    engine._merchant_post(game,alliance,payload | {'preview_token':quote['preview_token']})
    order=complete(engine,game)
    loadout=game.player.formation_loadouts[-1]
    assert loadout['slots']==quote['spec']['slots']
    definitions=engine._formation_material_defs()
    profile=calculate_formation_profile([definitions.get(key) for key in loadout['slots']],alpha=formation_alpha(game.player))
    assert profile['metrics']==quote['spec']['profile']['metrics']
    assert all(profile['metrics'][key]>=value for key,value in payload['metrics'].items())
    assert len({row['id'] for row in game.player.formation_materials})==profile['occupied_count']
    engine._activate_loadout(game.player,loadout)
    assert game.player.active_formation_id==loadout['id']
    assert order['spec']==quote['spec']


@pytest.mark.parametrize('mold',['sword','umbrella','armor','other'])
def test_weapon_uses_real_mold_stats_and_cannot_buy_inflation(setup,mold):
    engine,game,alliance=setup
    payload={'kind':'weapon','material_tier':1,'mold_id':mold}
    quote=engine._merchant_quote(game,alliance,payload)
    higher_bid=engine._merchant_quote(game,alliance,payload | {'principal':quote['principal']*2})
    assert quote['spec']==higher_bid['spec']
    engine._merchant_post(game,alliance,payload)
    complete(engine,game)
    artifact=game.player.crafted_artifacts[-1]
    assert artifact['actual_stats']==quote['spec']['stats']
    assert artifact['combat_effects']==quote['spec']['combat_effects']
    assert artifact['mold_id']==mold


def test_preview_is_readonly_stable_and_stale_token_is_rejected(setup):
    engine,game,alliance=setup
    payload={'kind':'weapon','material_tier':1,'alliance_id':alliance['id']}
    before=engine.store.load(game.id)
    quote=engine.preview_merchant_commission(game.id,payload)
    assert quote==engine.preview_merchant_commission(game.id,payload)
    after=engine.store.load(game.id)
    assert before.rng_state==after.rng_state and before.player.age==after.player.age
    assert before.player.inventory==after.player.inventory and before.merchant_state==after.merchant_state
    with pytest.raises(ValueError,match='预览'):
        engine._merchant_post(game,alliance,payload | {'mold_id':'umbrella','preview_token':quote['preview_token']})


def test_debug_endpoint_requires_runtime_switch(setup):
    from cultivation_life import server as server_module
    engine,game,alliance=setup
    httpd=ThreadingHTTPServer(('127.0.0.1',0),server_module.Handler)
    threading.Thread(target=httpd.serve_forever,daemon=True).start()
    request=urllib.request.Request(f'http://127.0.0.1:{httpd.server_port}/api/games/{game.id}/merchant-debug-hq',
        data=json.dumps({'alliance_id':alliance['id'],'debug':True}).encode(),headers={'Content-Type':'application/json'})
    try:
        with patch.object(server_module,'ENGINE',engine),patch.object(server_module,'load_runtime_config',return_value={'debug':False}):
            with pytest.raises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request)
            assert error.value.code==404
            assert engine._load(game.id).merchant_state['membership']['rank']==0
        with patch.object(server_module,'ENGINE',engine),patch.object(server_module,'load_runtime_config',return_value={'debug':True}):
            with urllib.request.urlopen(request) as response:
                shown=json.load(response)
            assert shown['merchant_system']['membership']['rank']==2
            assert shown['merchant_system']['membership']['site']=='hq'
            assert shown['player']['faction_id']==engine.present(game)['player']['faction_id']
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_removed_item_content_cancels_and_refunds_without_crashing_year(setup):
    from cultivation_life.content_registry import ITEM_CATALOG
    engine,game,alliance=setup
    engine._merchant_post(game,alliance,{'kind':'item','definition_id':'jinque_metal'})
    order=game.merchant_state['posted'][-1]
    balance=next(row.quantity for row in game.player.inventory if row.id=='spirit_stone')
    with patch.dict(ITEM_CATALOG):
        del ITEM_CATALOG['jinque_metal']
        game.player.age+=1
        engine._advance_merchant_year(game)
    assert order['status']=='cancelled'
    assert next(row.quantity for row in game.player.inventory if row.id=='spirit_stone')==balance+order['principal']
