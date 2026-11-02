"""Canonical inventory fees, world-only natural supply and reference-matched art."""
import copy,hashlib,json,random
from pathlib import Path
import pytest
from PIL import Image

from cultivation_life import content_registry as registry
from cultivation_life.ghost_body_content import MATERIAL_IDS,IDS,recipe,validate_material_content
from cultivation_life.rules import add_item,has_item
from cultivation_life.errors import NotFoundError
from cultivation_life.visual_assets import public_catalog,extension_asset
from test_ghost_body import ready_ghost

ROOT=Path(__file__).resolve().parents[1]
OWNER='official.ghost-reincarnation'


def test_natural_supply_is_exclusively_reincarnation_in_all_world_catalogs(ready_ghost):
    e,_=ready_ghost;keys=set(MATERIAL_IDS)
    for world in registry.WORLD_SYSTEMS['world_names']:
        stock={k for k in keys if e._is_world_market_good(world,'item',k)}
        auctions={r['content_id'] for r in e._auction_goods_pool(world)}&keys
        assert stock==auctions==(keys if world=='reincarnation' else set())
    for key in keys:
        assert registry.ITEM_CATALOG[key].force_tier==1
        assert {g['tier'] for g in registry.MARKET_GOODS if g['content_id']==key}=={9,10,11,12}


def test_later_training_quotes_and_spends_only_corresponding_material(ready_ghost):
    e,g=ready_ghost;g.player.immortal_body.update(level=50,ghost_training={'yinguo':3});e.store.save(g)
    before={i.id:i.quantity for i in g.player.inventory};bill=recipe('yinguo',3)
    e.upper_voisinage_action(g.id,'ghost_body_refine','yinguo',expected_level=3)
    saved=e._load(g.id)
    for key in MATERIAL_IDS:
        assert next(i.quantity for i in saved.player.inventory if i.id==key)==before[key]-bill.get(key,0)
    assert saved.player.immortal_body['ghost_training']['yinguo']==4
    assert saved.rng_state==g.rng_state and saved.player.age==g.player.age


def black_market(e,g):
    g.auction_state=dict(id='ghost-material-market',status='black_market',world=g.player.world,
        location_id=g.player.location_id,location_name=e.maps.location(g.player.world,g.player.location_id)['name'],
        round=0,lots=[],consignments=[],attendees=[],black_market_results=[])


def test_actual_black_market_search_and_purchase_deliver_original_inventory_item(ready_ghost):
    e,g=ready_ghost;black_market(e,g);add_item(g.player,'spirit_stone',10**10);e.store.save(g)
    e.search_black_market(g.id,'鬼躯五法');g=e._load(g.id)
    rows=g.auction_state['black_market_results'];assert {r['content_id'] for r in rows}==set(MATERIAL_IDS)
    row=rows[0];before=next(i.quantity for i in g.player.inventory if i.id==row['content_id'])
    e.buy_black_market_item(g.id,row['id'],quantity=4)
    assert next(i.quantity for i in e._load(g.id).player.inventory if i.id==row['content_id'])==before+4


def test_forged_other_world_black_market_cannot_produce_material(ready_ghost):
    e,g=ready_ghost;g.player.world='celestial';g.player.location_id=e.maps.default_location('celestial')
    black_market(e,g);g.auction_state['black_market_results']=[dict(id='foreign-ghost-material',kind='item',content_id=MATERIAL_IDS[0],price=1)]
    add_item(g.player,'spirit_stone',10**10);e.store.save(g);e.get_game(g.id)
    path=e.store._path(g.id);blob=path.read_bytes()
    with pytest.raises(ValueError,match='流通范围'):e.buy_black_market_item(g.id,'foreign-ghost-material',quantity=1)
    assert path.read_bytes()==blob


@pytest.mark.parametrize('bad',['missing','foreign_world','missing_tier'])
def test_invalid_dlc_material_sources_are_rejected(bad):
    items=dict(registry.ITEM_CATALOG);goods=list(registry.MARKET_GOODS)
    if bad=='missing':items.pop(MATERIAL_IDS[0])
    elif bad=='foreign_world':goods.append(dict(world='human',kind='item',content_id=MATERIAL_IDS[0],tier=9,price=1))
    else:goods=[g for g in goods if not(g['content_id']==MATERIAL_IDS[0] and g['tier']==12)]
    with pytest.raises(ValueError):validate_material_content(items,goods)


def test_art_is_dlc_owned_binary_alpha_pixel_portrait_and_denied_when_disabled():
    enabled=public_catalog(ROOT,registry.EXTENSION_REPORT);disabled=public_catalog(ROOT,[])
    provenance=json.loads((ROOT/'dlc/ghost-reincarnation/assets/visual/body-materials/provenance.json').read_text(encoding='utf-8'))
    assert {r['id'] for r in provenance['assets']}==set(MATERIAL_IDS)
    for key in MATERIAL_IDS:
        asset='material.'+key;assert enabled['items'][key]==asset and key not in disabled['items']
        loaded=[]
        for suffix,size in [('',32),('.portrait',128)]:
            record=enabled['assets'][asset+suffix];path=extension_asset(ROOT,ROOT,registry.EXTENSION_REPORT,record['file'])
            assert hashlib.sha256(path.read_bytes()).hexdigest()==record['sha256']
            with Image.open(path) as image:
                assert image.mode=='RGBA' and image.size==(size,size)
                assert set(image.getchannel('A').getdata())<={0,255};loaded.append(image.copy())
            with pytest.raises(NotFoundError):extension_asset(ROOT,ROOT,[],record['file'])
        assert loaded[1].tobytes()==loaded[0].resize((128,128),Image.Resampling.NEAREST).tobytes()


def test_disabled_package_does_not_register_its_material_items(tmp_path):
    directory=tmp_path/'empty';directory.mkdir()
    core=registry.ContentRegistry.load(ROOT/'content',directory)
    assert not set(MATERIAL_IDS)&set(core.items)
