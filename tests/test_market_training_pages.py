"""Dedicated training shelf keeps the original local stock and refresh clock."""
import copy
import random
from pathlib import Path
import pytest
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item
from cultivation_life.npc_development_content import definitions, allowed, is_training_supply
from cultivation_life.system.economy_system import _market_offer_group


@pytest.fixture
def ready(tmp_path):
    engine=GameEngine(Path(__file__).resolve().parents[1],tmp_path)
    g=engine._load(engine.create_game('货架验证','supreme_metal','dao',315,custom_start=dict(world='human',realm_index=4))['id'])
    g.pending_event=None
    add_item(g.player,'spirit_stone',10**9)
    engine.store.save(g)
    return engine,g


@pytest.mark.parametrize('world,tier', [('human',4),('spirit',8),('celestial',9),('asura',9),('nether',9),('reincarnation',9)])
def test_shelf_complete_scoped_and_read_only(ready,world,tier):
    e,g=ready
    g.player.world=world;g.player.realm_index=tier
    g.player.location_id=e.maps.normalize_location(world,None)
    e._clear_market(g);e._ensure_market(g,random.Random(17))
    before=copy.deepcopy(g.to_dict())
    shown=e._public_market(g)
    supplies=shown['training_material_offers']
    assert {r['content_id'] for r in supplies if r['kind']=='item'}=={i for i in definitions() if allowed(i,world)}
    assert len(supplies)==len({r['content_id'] for r in supplies})
    assert all(r['market_group']=='training' for r in supplies)
    assert not any(is_training_supply(r['kind'],r['content_id']) for r in shown['offers']+shown['puppet_material_offers'])
    assert len(shown['offers'])==6 and len(shown['material_offers'])==6
    assert all(r['world']==world for r in supplies)
    assert g.to_dict()==before
    e._ensure_market(g,random.Random(99))
    assert g.to_dict()==before


@pytest.mark.parametrize('kind', ['item', 'puppet_material'])
def test_independent_locks_purchase_and_natural_refresh(ready, kind):
    e,g=ready
    e._ensure_market(g,random.Random(7));e.store.save(g)
    def find(group):return next(r for r in e.store.load(g.id).market_offers if _market_offer_group(r)==group and not r.get('sold'))
    general=find('general')
    training=next(r for r in e.store.load(g.id).market_offers if _market_offer_group(r)=='training' and r['kind']==kind)
    e.toggle_market_offer_lock(g.id,general['id'])
    e.toggle_market_offer_lock(g.id,training['id'])
    saved=e.store.load(g.id)
    locked=[copy.deepcopy(r) for r in saved.market_offers if r.get('locked')]
    assert {r['id'] for r in locked}=={general['id'],training['id']}
    other=next(r for r in saved.market_offers if _market_offer_group(r)=='training' and not r.get('locked') and not r.get('economy_unavailable'))
    e.buy_market_offer(g.id,other['id'])
    purchased=e.store.load(g.id)
    assert purchased.player.age==saved.player.age
    assert next(r for r in purchased.market_offers if r['id']==other['id'])['sold']
    with pytest.raises(ValueError):e.buy_market_offer(g.id,other['id'])
    # The same authoritative age is stable, including across read-only reloads.
    e._ensure_market(purchased,random.Random(8))
    assert next(r for r in purchased.market_offers if r['id']==other['id'])['sold']
    purchased.player.age+=1
    e._ensure_market(purchased,random.Random(9))
    for old in locked:
        current=next(r for r in purchased.market_offers if r['id']==old['id'])
        assert current==old
    assert len([r for r in purchased.market_offers if r['content_id']==training['content_id']])==1
    assert any(r['content_id']==other['content_id'] and not r['sold'] and r['id']!=other['id'] for r in purchased.market_offers)


@pytest.mark.parametrize('world',['lost','rift'])
def test_no_market_in_special_space(ready,world):
    e,g=ready
    g.player.world=world
    e._refresh_world_market(g,random.Random(4))
    assert not g.market_offers
