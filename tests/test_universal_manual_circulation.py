import copy
import random
import pytest
from cultivation_life import universal_manuals as jade
from cultivation_life.content_registry import MARKET_GOODS, WORLD_SYSTEMS, ITEM_CATALOG
from cultivation_life.models import Technique
from cultivation_life.rules import add_item
from cultivation_life.system.economy.state import commodity_catalog
from test_seeded_dungeons import local


def test_every_world_band_and_natural_manual_level():
    for world,cap in WORLD_SYSTEMS['seeded_dungeons']['ceilings'].items():
        rows=[r for r in MARKET_GOODS if r['world']==world and jade.parse(r['content_id'])]
        expected=set(range({5:1,8:6,12:9}[cap],cap+1))
        assert {jade.parse(r['content_id'])[1] for r in rows}==expected
        assert len(rows)==len(expected)*6
        assert all(jade.parse(r['content_id'])[2]==1 for r in rows)
        assert {jade.parse(k)[1] for k in commodity_catalog(world) if jade.parse(k)}==expected
    assert len([i for i in ITEM_CATALOG if jade.parse(i)])==6*12*9


def test_merge_conserves_materials_through_maximum_level(local):
    from cultivation_life.rules import merge_technique_copies
    from cultivation_life.system.economy.basket_production import recipe
    from cultivation_life.system.economy_system import _catalog_price
    _,g=local
    for level in range(1,9):
        key=jade.identity('dao',3,level)
        add_item(g.player,key,2)
        before=sum(i.quantity for i in g.player.inventory if i.id==key)
        assert merge_technique_copies(g.player,key,level)==level+1
        assert sum(i.quantity for i in g.player.inventory if i.id==key)==before-2
        assert _catalog_price('item',jade.identity('dao',3,level+1))==2**level*_catalog_price('item',jade.identity('dao',3))
        assert recipe({'world':'human'},jade.identity('dao',3,level+1)) is None
    before=copy.deepcopy(g.player.inventory)
    with pytest.raises(ValueError):merge_technique_copies(g.player,jade.identity('dao',3,9),9)
    assert g.player.inventory==before
    assert recipe({'world':'human'},jade.identity('dao',9)) is None


def test_merge_upgrade_and_replay_through_original_commands(local):
    e,g=local
    book=Technique(id='random:unrepeatable',name='孤本',path='dao',grade=3,level=2)
    g.player.known_techniques.append(book)
    key=jade.identity('dao',3)
    add_item(g.player,key,2);e.store.save(g);e.get_game(g.id)
    before=e.store._path(g.id).read_bytes()
    with pytest.raises(ValueError,match='万能玉简'):e.upgrade_technique(g.id,book.id)
    assert e.store._path(g.id).read_bytes()==before
    with pytest.raises(ValueError,match='等级'):e.merge_technique_manuals(g.id,key,2)
    e.merge_technique_manuals(g.id,key,1)
    merged=e.store.load(g.id)
    assert not any(i.id==key for i in merged.player.inventory)
    assert next(i.quantity for i in merged.player.inventory if i.id==jade.identity('dao',3,2))==1
    with pytest.raises(ValueError,match='两份'):e.merge_technique_manuals(g.id,key,1)
    e.upgrade_technique(g.id,book.id)
    saved=e.store.load(g.id)
    assert next(t.level for t in saved.player.known_techniques if t.id==book.id)==3
    assert not any(jade.parse(i.id) for i in saved.player.inventory)


def test_black_market_actual_purchase_and_foreign_offer_rejection(local):
    e,g=local;add_item(g.player,'spirit_stone',10**7)
    g.auction_state.update(status='black_market',world=g.player.world,location_id=g.player.location_id,location_name='验收交易会')
    e.store.save(g)
    shown=e.search_black_market(g.id,r'^\d+阶.*途万能玉简')
    rows=shown['auction_system']['black_market_results']
    assert rows and all(jade.parse(r['content_id'])[1]<=5 for r in rows)
    selected=next(r for r in rows if r['content_id']==jade.identity('dao',1))
    e.buy_black_market_item(g.id,selected['id'],2)
    saved=e.store.load(g.id)
    assert next(i.quantity for i in saved.player.inventory if i.id==selected['content_id'])==2
    bad=copy.deepcopy(selected);bad['id']='foreign';bad['content_id']=jade.identity('dao',9)
    saved.auction_state['black_market_results'].append(bad);e.store.save(saved)
    before=e.store._path(g.id).read_bytes()
    with pytest.raises(ValueError,match='流通范围'):e.buy_black_market_item(g.id,'foreign')
    assert e.store._path(g.id).read_bytes()==before


class JadeDraw(random.Random):
    """Pick a legitimate jade from the actual pool, for deterministic acceptance."""
    def choices(self,population,weights=None,*,cum_weights=None,k=1):
        jades=[r for r in population if isinstance(r,dict) and jade.parse(r.get('content_id',''))]
        return super().choices(jades,k=k) if jades else super().choices(population,weights,cum_weights=cum_weights,k=k)

    def sample(self,population,k,*,counts=None):
        jades=[r for r in population if isinstance(r,dict) and jade.parse(r.get('content_id',''))]
        return super().sample(jades,k) if len(jades)>=k else super().sample(population,k,counts=counts)


def test_real_fair_generation_and_private_purchase(local):
    e,g=local;add_item(g.player,'spirit_stone',10**8)
    e._schedule_auction(g,random.Random(7))
    g.auction_state.update(location_id=g.player.location_id,location_name='验收交易会',auction_class=2,rank_band=[3,4],entry_fee=0)
    e._open_auction(g,JadeDraw(4));e.store.save(g)
    assert g.auction_state['lots'] and all(jade.parse(r['content_id']) for r in g.auction_state['lots'])
    attendee=g.auction_state['attendees'][0];offer=attendee['trade_offers'][0]
    assert jade.parse(offer['content_id'])
    e.negotiate_at_auction(g.id,attendee['id'])
    e.buy_private_trade_item(g.id,attendee['id'],offer['id'])
    saved=e.store.load(g.id)
    assert next(i.quantity for i in saved.player.inventory if i.id==offer['content_id'])==1
    with pytest.raises(ValueError):e.buy_private_trade_item(g.id,attendee['id'],offer['id'])
