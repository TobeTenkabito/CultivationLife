"""Acquisition and public upgrade regression for one-off random manuals."""
import copy
import random
import pytest
from cultivation_life import universal_manuals as jade
from cultivation_life.content_registry import ITEM_CATALOG, TECHNIQUE_CATALOG, WORLD_SYSTEMS
from cultivation_life.models import Player, Technique
from cultivation_life.rules import (add_item, add_technique_copy, upgrade_known_technique,
    assign_technique, combat_power, technique_special_effect)
from cultivation_life.system.duel_techniques import player_books, npc_eligible
from cultivation_life.system.economy import state as economy
from cultivation_life.system.economy.basket_production import recipe
from cultivation_life.system.dungeons.prose import scene
from test_seeded_dungeons import local


@pytest.mark.parametrize('path',jade.PATHS)
def test_all_twelve_grades_upgrade_unique_books_with_matching_material(path):
    for grade in range(1,13):
        p=Player(name='合参',spirit_root='heavenly',path=path)
        book=Technique(id=f'one-off:{path}:{grade}',name='孤本',path=path,grade=grade,level=4)
        p.known_techniques=[book];p.combat_techniques=[copy.deepcopy(book)]
        add_item(p,jade.material(book),1)
        assert upgrade_known_technique(p,book.id)==5
        assert jade.count(p,book)==0
        assert p.combat_techniques[0].level==5


def test_wrong_grade_path_and_shortfall_are_atomic():
    p=Player(name='合参',spirit_root='heavenly');book=Technique(id='random:unique',name='孤本',grade=3,level=4)
    p.known_techniques=[book]
    add_item(p,jade.identity('dao',3),3)
    add_item(p,jade.identity('dao',4),100)
    add_item(p,jade.identity('demonic',3),100)
    before=copy.deepcopy(p.inventory)
    with pytest.raises(ValueError,match='万能玉简'):upgrade_known_technique(p,book.id)
    assert p.inventory==before and book.level==4


def test_named_copy_has_priority_and_max_level_consumes_nothing():
    p=Player(name='合参',spirit_root='heavenly');book=Technique(id='random:unique',name='孤本',grade=3,level=8)
    p.known_techniques=[book];add_item(p,jade.material(book),8);add_technique_copy(p,book)
    assert upgrade_known_technique(p,book.id)==9
    assert next(i.quantity for i in p.inventory if i.id==jade.identity('dao',3,8))==8
    with pytest.raises(ValueError,match='Lv.9'):upgrade_known_technique(p,book.id)
    assert next(i.quantity for i in p.inventory if i.id==jade.identity('dao',3,8))==8


def test_body_books_never_supply_battle_power_or_duel_effects():
    p=Player(name='炼体',spirit_root='heavenly',realm_index=4,layer=9,body_training=100)
    book=copy.deepcopy(next(t for t in TECHNIQUE_CATALOG.values() if t.category=='body' and t.grade==1 and t.element=='neutral'))
    with pytest.raises(ValueError,match='炼体栏'):assign_technique(p,book,'combat')
    base=combat_power(p)
    # Simulate a pre-change configuration, without changing or deleting its books.
    p.combat_techniques=[book];p.duel_technique_ids=[book.id]
    assert combat_power(p)==base
    assert player_books(p)==[]
    assert not npc_eligible(dict(world='human',realm_index=8,body_training=100,spirit_root='heavenly'),book)
    assign_technique(p,book,'body')
    assert p.body_technique.id==book.id


def test_public_command_upgrades_fused_dungeon_book_and_keeps_study_level(local, monkeypatch):
    engine,game=local
    from cultivation_life.system.dungeons.rewards import grant, learn
    from test_seeded_dungeons import discover
    cfg=WORLD_SYSTEMS['seeded_dungeons'];scope=game.player.world+':'+game.player.location_id
    monkeypatch.setitem(cfg['profiles'][scope],'weights',[0,0,0,1])
    monkeypatch.setitem(cfg,'legendary_fusion_chance',1.)
    discover(engine,game)
    game=engine.store.load(game.id)
    site=next(iter(game.dungeon_state['instances'].values()))
    book_reward=site['nodes'][-1]['reward']
    assert book_reward['fused']
    # An acquired core inheritance fixture retains its actual frozen blueprint/receipt.
    site['claims'].append(book_reward['id']);game.player.realm_index=5
    grant(game,book_reward);learn(game,book_reward['book']['id'])
    book=next(t for t in game.player.known_techniques if t.id==book_reward['book']['id'])
    add_item(game.player,jade.material(book),3)
    engine.store.save(game)
    view=engine.upgrade_technique(game.id,book.id)
    saved=engine.store.load(game.id)
    assert saved.dungeon_state['manuals'][book.id]['level']==2
    assert '万能玉简' in next(h.summary for h in saved.history if h.event_id=='SYS_TECHNIQUE_UPGRADE')
    public=next(t for t in view['player']['known_techniques'] if t['id']==book.id)
    assert not public['can_upgrade'] and not public['doctrine_fusion']
    add_item(saved.player,jade.identity(book.path,book.grade,2))
    saved.player.opportunity=2000
    engine.store.save(saved)
    engine.dungeon_action(game.id,'study',dict(manual_id=book.id))
    with pytest.raises(ValueError,match='参悟'):engine.upgrade_technique(game.id,book.id)
    assert engine.store.load(game.id).dungeon_state['manuals'][book.id]['level']==2


def test_market_material_supply_uses_existing_stock_inputs_and_world_caps(local):
    engine,game=local
    economy.ensure_market(game,engine.maps)
    market=economy.local_market(game)
    key=jade.identity('dao',3)
    assert market['commodities'][key]['stock']>0
    assert recipe(market,key) # Jade is made from paid raw materials, not extracted free.
    assert jade.identity('dao',6) not in economy.commodity_catalog('human')
    assert jade.identity('dao',9) not in economy.commodity_catalog('spirit')
    assert jade.identity('dao',12) in economy.commodity_catalog('celestial')
    stock=market['commodities'][key]['stock']
    economy.ensure_market(game,engine.maps)
    assert market['commodities'][key]['stock']==stock
    del market['commodities'][key];market['goods_policy']=2
    economy.ensure_market(game,engine.maps)
    assert market['commodities'][key]['stock']==0 # Existing shelves gain a listing, never free restocks.


def test_all_fixed_descriptions_and_seeded_prose():
    forbidden=('不可证明','不确定','不可认定','不能证明','不代表','并非','不等于','不能保证','不是','无法确认')
    for book in TECHNIQUE_CATALOG.values():
        assert book.description
        assert not any(word in technique_special_effect(book) for word in forbidden),book.id
    for theme in ('water','mountain','fire','frost','fort','shadow','grove','ruins'):
        texts={scene(random.Random(i),'古塞',theme,'conflict','东') for i in range(500)}
        assert len(texts)>490
        assert scene(random.Random(9),'古塞',theme,'conflict','东')==scene(random.Random(9),'古塞',theme,'conflict','东')
    assert all(p['slots']==12 for p in WORLD_SYSTEMS['seeded_dungeons']['profiles'].values())


def test_actual_purchase_pays_stock_and_material_upgrades_a_one_off_book(local):
    engine,game=local
    from cultivation_life.system.economy.basket_trade import quote
    from cultivation_life.system.economy.ledger import balance
    book=Technique(id='random:market-only-copy',name='归澜孤本',path='dao',grade=3,level=2)
    game.player.known_techniques.append(book)
    add_item(game.player,'spirit_stone',1000000)
    engine.store.save(game)
    engine.get_game(game.id)
    game=engine._load(game.id)
    market=economy.local_market(game);key=jade.identity(book.path,book.grade)
    stock=market['commodities'][key]['stock'];cash=balance(game,'player')
    payload=dict(market_id=market['id'],revision=market['revision'],item_id=key,side='buy',quantity=2,
                 total=quote(market['commodities'][key],'buy',2)['total'])
    engine.store.save(game)
    engine.trade_local_market(game.id,payload)
    after=engine.store.load(game.id)
    assert economy.local_market(after)['commodities'][key]['stock']==stock-2
    assert balance(after,'player')==cash-payload['total']
    engine.merge_technique_manuals(game.id,key,1)
    engine.upgrade_technique(game.id,book.id)
    after=engine.store.load(game.id)
    learned=next(t for t in after.player.known_techniques if t.id==book.id)
    assert learned.level==3 and jade.count(after.player,learned)==0


def test_old_log_projection_removes_commentary_without_mutating_record():
    from cultivation_life.system.dungeons.presentation import public_logs
    rows=[dict(text='沈砚加入队伍。其所述来意尚不能证实。',kind='实证',actors=['shen'])]
    original=copy.deepcopy(rows)
    assert public_logs(rows)[0]['text']=='沈砚加入队伍。'
    assert rows==original


def test_old_body_selection_frees_a_slot_when_player_selects_a_valid_book():
    from cultivation_life.system.duel_techniques import select, public
    p=Player(name='重整',spirit_root='heavenly',realm_index=4,body_training=100)
    old=[Technique(id=f'old-body-{i}',name='旧炼体',category='body') for i in range(7)]
    p.combat_techniques=old+[Technique(id='new-combat',name='斗法',category='spiritual')]
    p.duel_technique_ids=[b.id for b in old]
    assert public(p)['selected']==[]
    assert all(t['id']=='new-combat' for t in public(p)['candidates'])
    select(p,'new-combat')
    assert p.duel_technique_ids==['new-combat']
