"""Actual five-aggregate inventory costs, source-world limits and DLC artwork."""
import copy
import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from cultivation_life import content_registry as registry
from cultivation_life.body_mechanism_content import validate_config,validate_material_sources
from cultivation_life.errors import NotFoundError
from cultivation_life.rules import add_item,has_item,remove_item
from cultivation_life.system.wuyun import definitions
from cultivation_life.system.wuyun_cultivation import quote,train
from cultivation_life.visual_assets import public_catalog,extension_asset
from test_asura_manifestation import ready

ROOT=Path(__file__).resolve().parents[1]
OWNER='official.asura-manifestation'


@pytest.mark.parametrize('index',range(5))
def test_each_aggregate_spends_only_its_actual_material_without_time_or_rng(ready,index):
    e,g=ready;row=definitions()[index];g.player.asura_cultivation['body_level']=50
    g.player.opportunity=10**12;bill=quote(row,0)
    for key,amount in bill['materials'].items():add_item(g.player,key,amount)
    unrelated=next(k for other in definitions() if other['id']!=row['id'] for k in other['recipe'])
    add_item(g.player,unrelated,17);e.store.save(g);e.get_game(g.id);before=e.store.load(g.id)
    e.asura_action(g.id,'train_aggregate',row['id'],expected_level=0);after=e.store.load(g.id)
    assert after.player.asura_cultivation['aggregates']=={row['id']:1}
    assert all(not has_item(after.player,key) for key in bill['materials'])
    assert has_item(after.player,unrelated,17)
    assert after.player.opportunity==before.player.opportunity-bill['opportunity']
    assert after.player.asura_cultivation['souls']==before.player.asura_cultivation['souls']-bill['souls']
    assert after.player.age==before.player.age and after.rng_state==before.rng_state


def test_missing_material_rejects_entire_payment_and_public_quote_is_read_only(ready):
    e,g=ready;row=definitions()[0];key,amount=next(iter(row['recipe'].items()))
    g.player.asura_cultivation['body_level']=50;g.player.opportunity=10**12
    add_item(g.player,key,amount-1);e.store.save(g);e.get_game(g.id)
    path=e.store._path(g.id);before=path.read_bytes()
    shown=e.get_game(g.id)['asura']['aggregates'][0]
    assert not shown['can_train'] and '培养材料不足' in shown['reason']
    assert shown['materials'][0]['owned']==amount-1 and shown['materials'][0]['needed']==amount
    with pytest.raises(ValueError,match='材料不足'):e.asura_action(g.id,'train_aggregate','se',expected_level=0)
    assert path.read_bytes()==before
    instance=e.store.load(g.id);snapshot=copy.deepcopy(instance)
    with pytest.raises(ValueError,match='材料不足'):train(instance,'se',0,has_item=has_item,remove_item=remove_item)
    assert instance==snapshot


def test_later_training_scales_material_fee_and_stale_request_cannot_spend_twice(ready):
    e,g=ready;row=definitions()[0];key=next(iter(row['recipe']))
    g.player.asura_cultivation.update(body_level=50,aggregates={'se':3});g.player.opportunity=10**12
    bill=quote(row,3);add_item(g.player,key,bill['materials'][key]);e.store.save(g)
    e.asura_action(g.id,'train_aggregate','se',expected_level=3)
    assert not has_item(e.store.load(g.id).player,key)
    path=e.store._path(g.id);before=path.read_bytes()
    with pytest.raises(ValueError,match='等级已变化'):e.asura_action(g.id,'train_aggregate','se',expected_level=3)
    assert path.read_bytes()==before


def test_natural_supply_exists_only_in_asura_across_every_world_catalog(ready):
    e,_=ready;ids={key for row in definitions() for key in row['recipe']}
    assert len(ids)==5
    for world in registry.WORLD_SYSTEMS['world_names']:
        permitted={key for key in ids if e._is_world_market_good(world,'item',key)}
        auctions={r['content_id'] for r in e._auction_goods_pool(world)}&ids
        assert permitted==auctions==(ids if world=='asura' else set())
    for key in ids:
        assert {r['tier'] for r in registry.MARKET_GOODS if r['content_id']==key}=={9,10,11,12}
        assert registry.ITEM_CATALOG[key].force_tier==1


def black_market(e,g):
    location=g.player.location_id
    g.auction_state=dict(id='wuyun-real-market',status='black_market',world=g.player.world,
        location_id=location,location_name=e.maps.location(g.player.world,location)['name'],
        round=0,lots=[],consignments=[],attendees=[],black_market_results=[])


def test_actual_black_market_search_and_purchase_deliver_real_materials(ready):
    e,g=ready;black_market(e,g);add_item(g.player,'spirit_stone',10**10);e.store.save(g)
    e.search_black_market(g.id,'五蕴');g=e.store.load(g.id)
    ids={key for row in definitions() for key in row['recipe']}
    results=g.auction_state['black_market_results']
    assert {r['content_id'] for r in results}==ids
    target=results[0];before=sum(i.quantity for i in g.player.inventory if i.id=='spirit_stone')
    e.buy_black_market_item(g.id,target['id'],quantity=4);after=e.store.load(g.id)
    assert has_item(after.player,target['content_id'],4)
    assert sum(i.quantity for i in after.player.inventory if i.id=='spirit_stone')<before


def test_forged_other_world_black_market_offer_cannot_produce_material(ready):
    e,g=ready;g.player.world='celestial';g.player.location_id=e.maps.default_location('celestial')
    black_market(e,g);key=next(iter(definitions()[0]['recipe']))
    g.auction_state['black_market_results']=[dict(id='foreign-material',kind='item',content_id=key,price=1)]
    add_item(g.player,'spirit_stone',10**10);e.store.save(g);e.get_game(g.id)
    path=e.store._path(g.id);before=path.read_bytes()
    with pytest.raises(ValueError,match='流通范围'):e.buy_black_market_item(g.id,'foreign-material',quantity=1)
    assert path.read_bytes()==before
    e.search_black_market(g.id,'五蕴')
    assert not e.store.load(g.id).auction_state['black_market_results']


def test_optional_content_without_asura_does_not_define_the_five_materials(tmp_path):
    empty=tmp_path/'empty';empty.mkdir()
    core=registry.ContentRegistry.load(ROOT/'content',empty)
    assert not {key for row in definitions() for key in row['recipe']} & set(core.items)


@pytest.mark.parametrize('bad',['missing_item','foreign_world','zero_quantity','missing_recipe'])
def test_bad_material_content_is_rejected_before_dlc_loading(bad):
    cfg=copy.deepcopy(registry.WORLD_SYSTEMS['asura_manifestation']);items=dict(registry.ITEM_CATALOG)
    goods=copy.deepcopy(registry.MARKET_GOODS);key=next(iter(cfg['five_aggregates'][0]['recipe']))
    if bad=='missing_item':items.pop(key)
    elif bad=='foreign_world':goods=(*goods,dict(world='human',kind='item',content_id=key,tier=9,price=1))
    elif bad=='zero_quantity':cfg['five_aggregates'][0]['recipe'][key]=0
    else:cfg['five_aggregates'][0].pop('recipe')
    with pytest.raises(ValueError):
        validate_config(cfg);validate_material_sources(cfg,items,goods)


def test_dlc_art_has_real_alpha_pixel_portraits_and_disabled_access_is_denied():
    enabled=public_catalog(ROOT,registry.EXTENSION_REPORT);disabled=public_catalog(ROOT,[])
    provenance=json.loads((ROOT/'dlc/asura-manifestation/assets/visual/wuyun-materials/provenance.json').read_text(encoding='utf-8'))
    assert len(provenance['assets'])==5
    for row in provenance['assets']:
        key=row['id'];asset='material.'+key
        assert enabled['items'][key]==asset and key not in disabled['items'] and asset not in disabled['assets']
        loaded=[]
        for suffix,size in [('',32),('.portrait',128)]:
            record=enabled['assets'][asset+suffix]
            path=extension_asset(ROOT,ROOT,registry.EXTENSION_REPORT,record['file'])
            assert hashlib.sha256(path.read_bytes()).hexdigest()==record['sha256']
            with Image.open(path) as image:
                assert image.mode=='RGBA' and image.size==(size,size)
                assert set(image.getchannel('A').getdata())<={0,255}
                loaded.append(image.copy())
            with pytest.raises(NotFoundError):extension_asset(ROOT,ROOT,[],record['file'])
        assert loaded[1].tobytes()==loaded[0].resize((128,128),Image.Resampling.NEAREST).tobytes()
