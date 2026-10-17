import copy
import json
import random
import subprocess
import sys
from itertools import combinations
from pathlib import Path

import pytest

from cultivation_life.content_registry import (
    TECHNIQUE_CATALOG, MARKET_GOODS, WORLD_SYSTEMS, ROOT_DEFINITIONS, ContentError, ContentRegistry,
    restricted_acquisition, natural_market_acquisition_allowed,
)
from cultivation_life.engine import GameEngine
from cultivation_life.engine.transactions import request_scope
from cultivation_life.models import GameState
from cultivation_life.rules import (
    acquire_technique, add_item, add_technique_copy, assign_technique,
    can_player_practice_technique, can_practice_technique, public_player,
    technique_scale, validate_technique, ensure_technique_set,
)
from tools.generate_common_techniques import FAMILIES, LINES, ROLES, WORLD_PATHS

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ('opportunity_bonus','hp_bonus','mp_bonus','combat_bonus')
OPEN = [t for t in TECHNIQUE_CATALOG.values() if t.id.startswith('TECH_OPEN_')]


def art(grade=1, family='metal_water', role='main', path='dao'):
    return copy.deepcopy(TECHNIQUE_CATALOG[f'TECH_OPEN_{LINES[path][2][grade-1]}_{family.upper()}_{role.upper()}'])


@pytest.fixture
def ready(tmp_path):
    engine=GameEngine(ROOT,tmp_path/'saves')
    made=engine.create_game('通用功法','supreme_metal','dao',71861)
    game=engine._load(made['id']);game.pending_event=None
    game.player.spirit_root='supreme_metal'
    game.player.realm_index=1;game.player.layer=1
    engine.store.save(game)
    return engine,game


def test_catalog_all_grades_roles_elements_and_stable_generator():
    assert len(OPEN)==3888
    assert len({t.id for t in OPEN})==len({t.name for t in OPEN})==3888
    assert {t.grade for t in OPEN}==set(range(1,13))
    assert not any(any(r.name in t.name for r in __import__('cultivation_life.content_registry',fromlist=['REALMS']).REALMS) for t in OPEN)
    for t in OPEN:
        validate_technique(t)
        assert t.effective_worlds==[] and t.doctrine_id is None
        assert not restricted_acquisition('technique',t.id)
    result=subprocess.run([sys.executable,'-X','utf8','tools/generate_common_techniques.py'],cwd=ROOT,capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('world',WORLD_PATHS)
def test_every_local_stage_has_all_roots_and_roles_in_generic_pools(ready,world):
    engine,game=ready
    native=WORLD_PATHS[world]
    cap=WORLD_SYSTEMS['world_profiles'][world]['npc_realm_cap']
    offered={r['content_id'] for r in MARKET_GOODS if r.get('world','human')==world and r['kind']=='technique'}
    for grade in range(1,cap+1):
        for family in FAMILIES:
            for role in ROLES:
                assert art(grade,family,role,native).id in offered
    game.player.world=world;game.player.location_id=engine.maps.default_location(world)
    game.player.realm_index=cap
    auction={r['content_id'] for r in engine._auction_goods_pool(world) if r['kind']=='technique'}
    treasure={r['content_id'] for r in engine._treasure_reward_pool(game,'technique')}
    assert art(cap,'thunder','combat',native).id in auction
    assert any(art(cap,family,role,native).id in treasure for family in FAMILIES for role in ROLES)


@pytest.mark.parametrize('grade',range(1,13))
def test_role_advantages_and_ratios_increase_with_every_level(grade):
    for path in LINES:
        for family in FAMILIES:
            main,support,combat=[art(grade,family,r,path) for r in ROLES]
            previous=None
            for level in range(1,10):
                for t in (main,support,combat):t.level=level
                val=lambda t,k:getattr(t,k)*technique_scale(t,k)
                assert val(combat,'combat_bonus')>val(main,'combat_bonus')
                assert val(main,'opportunity_bonus')>max(val(support,'opportunity_bonus'),val(combat,'opportunity_bonus'))
                assert val(support,'hp_bonus')>max(val(main,'hp_bonus'),val(combat,'hp_bonus'))
                assert val(support,'mp_bonus')>max(val(main,'mp_bonus'),val(combat,'mp_bonus'))
                ratios=(val(combat,'combat_bonus')/val(main,'combat_bonus'),
                        val(main,'opportunity_bonus')/val(combat,'opportunity_bonus'),
                        val(support,'hp_bonus')/val(main,'hp_bonus'),val(support,'mp_bonus')/val(main,'mp_bonus'))
                if previous:assert all(a>b for a,b in zip(ratios,previous))
                previous=ratios


@pytest.mark.parametrize('grade',range(1,13))
def test_mutation_and_multi_root_premiums_follow_requirement_hierarchy(grade):
    for role in ROLES:
        neutral,single,dual,triple,quad,all_five,mutated,mixed,three_mutations,four_mutations=[art(grade,f,role) for f in ['neutral','metal','metal_water','metal_water_wood','metal_wood_water_earth','five_elements','wind','wind_thunder','wind_thunder_yin','wind_thunder_yin_yang']]
        for k in FIELDS:
            v=getattr(neutral,k)
            precision=1e-4 if k=='combat_bonus' else 1e-6
            for t,mult in [(single,1.04),(dual,1.08),(triple,1.12),(quad,1.16),(all_five,1.20),(mutated,1.18),(mixed,1.19),(three_mutations,1.25),(four_mutations,1.30)]:
                assert getattr(t,k)==pytest.approx(v*mult,abs=precision)
            assert getattr(neutral,k)<getattr(single,k)<getattr(dual,k)<getattr(triple,k)<getattr(quad,k)<getattr(all_five,k)
            assert getattr(quad,k)<getattr(mutated,k)<getattr(mixed,k)<getattr(all_five,k)
            assert getattr(all_five,k)<getattr(three_mutations,k)<getattr(four_mutations,k)
            for family in ('wind_thunder_yang','wind_yin_yang','thunder_yin_yang'):
                assert getattr(art(grade,family,role),k)==getattr(three_mutations,k)


def test_three_mutation_families_cover_every_combination():
    actual={frozenset(roots) for roots,_ in FAMILIES.values()
            if len(roots)==3 and set(roots)<={'wind','thunder','yin','yang'}}
    assert actual=={frozenset(roots) for roots in combinations(('wind','thunder','yin','yang'),3)}


@pytest.mark.parametrize('family',FAMILIES)
def test_all_required_roots_must_be_present_in_both_player_and_npc_rules(ready,family):
    _,game=ready;t=art(family=family)
    roots=t.required_affinities
    game.player.spirit_root='none';game.player.additional_roots=list(roots)
    assert can_player_practice_technique(game.player,t)
    for missing in roots:
        game.player.additional_roots=[r for r in roots if r!=missing]
        assert not can_player_practice_technique(game.player,t)
    matching=next((k for k,v in ROOT_DEFINITIONS.items() if set(roots)<=set(v['elements'])),None)
    if matching:assert can_practice_technique(matching,t)
    if len(roots)>1:assert not can_practice_technique('supreme_metal',t)


def test_equipping_failed_check_is_atomic_then_upgrading_preserves_requirements(ready):
    engine,game=ready;t=art()
    acquire_technique(game.player,t);add_technique_copy(game.player,t)
    engine.store.save(game)
    before=game.to_dict()
    with pytest.raises(ValueError,match='灵根'):
        assign_technique(game.player,copy.deepcopy(t),'main')
    assert game.to_dict()==before
    shown=public_player(game.player)
    row=next(r for r in shown['known_techniques'] if r['id']==t.id)
    assert not row['compatible'] and '须全部具备' in row['element_name']
    game.player.additional_roots=['water'];engine.store.save(game)
    engine.equip_known_technique(game.id,t.id,'main')
    engine.upgrade_technique(game.id,t.id)
    saved=engine._load(game.id)
    assert saved.player.technique.level==2
    assert saved.player.technique.required_affinities==['metal','water']
    assert not any(i.technique_id==t.id for i in saved.player.inventory)


def test_saved_metadata_is_personal_and_old_catalogue_requirements_cannot_disappear(ready):
    _,game=ready;t=art();acquire_technique(game.player,t)
    game.player.additional_roots=['water'];assign_technique(game.player,t,'main')
    raw=game.to_dict();loaded=GameState.from_dict(raw)
    loaded.player.world='spirit'
    assert loaded.player.technique.required_affinities==['metal','water']
    assert game.player.technique.required_affinities is not loaded.player.technique.required_affinities
    loaded.player.technique.required_affinities=[]
    ensure_technique_set(loaded.player)
    assert loaded.player.technique.required_affinities==['metal','water']
    del raw['player']['technique']['required_affinities']
    old=GameState.from_dict(raw);ensure_technique_set(old.player)
    assert old.player.technique.required_affinities==['metal','water']


@pytest.mark.parametrize('requirements',[['metal','metal'],['ice'],'metal',None])
def test_invalid_root_requirements_rejected(requirements):
    t=art();t.required_affinities=requirements
    with pytest.raises(ValueError,match='所需灵根'):validate_technique(t)


def test_legacy_root_and_level_rules_remain_valid(ready):
    _,game=ready
    assert can_player_practice_technique(game.player,'metal')
    assert can_practice_technique('none','neutral')
    assert not can_practice_technique('supreme_metal','five_elements')
    old=copy.deepcopy(TECHNIQUE_CATALOG['TECH_BASIC_QI'])
    assert old.required_affinities==[]
    for i,mult in enumerate((1.,1.1,1.2,1.3,1.4,1.5,1.8,2.4,3.),1):
        old.level=i;assert old.level_multiplier==mult


def test_all_open_definitions_are_available_without_any_dlc(tmp_path):
    base=ContentRegistry.load(ROOT/'content',tmp_path/'no-extensions')
    assert {t.id for t in OPEN}<set(base.techniques)


def test_registry_rejects_malformed_fixed_root_metadata():
    documents={p.name:json.loads(p.read_text(encoding='utf-8')) for p in (ROOT/'content').glob('*.json')}
    documents['techniques.json']['techniques'][-1]['required_affinities']=['water','ice']
    with pytest.raises(ContentError,match='所需灵根'):
        ContentRegistry._from_documents(documents)


def test_acquisition_ignores_missing_roots_but_equip_does_not(ready):
    engine,game=ready;t=art()
    add_item(game.player,'spirit_stone',1000)
    engine._ensure_market(game,random.Random(7))
    game.market_offers.append(dict(id='open-manual',kind='technique',content_id=t.id,name=t.name,
                                  description='通用传承',element=t.element,price=100,tier=1,tier_name='练气',
                                  market_name='书坊',world='human',location_id=game.player.location_id,
                                  rare_next_tier=False,sold=False,locked=False))
    engine.store.save(game)
    shown=engine.buy_market_offer(game.id,'open-manual')
    known=next(r for r in shown['player']['known_techniques'] if r['id']==t.id)
    assert not known['compatible']
    with pytest.raises(ValueError,match='灵根'):
        engine.equip_known_technique(game.id,t.id,'main')


RARE_FAMILIES=('five_elements','wind_thunder','yin_yang','wind_thunder_yin',
               'wind_thunder_yang','wind_yin_yang','thunder_yin_yang','wind_thunder_yin_yang')


@pytest.mark.parametrize('world',WORLD_PATHS)
def test_shop_excludes_rare_arts_without_removing_other_acquisition_pools(ready,monkeypatch,world):
    engine,game=ready
    path=WORLD_PATHS[world];cap=WORLD_SYSTEMS['world_profiles'][world]['npc_realm_cap']
    game.player.world=world;game.player.location_id=engine.maps.default_location(world)
    game.player.realm_index=cap
    original=engine.maps.localize_goods
    captured=[]
    def inspect(goods,*args):
        rows=list(goods);captured.extend(rows)
        return original(rows,*args)
    monkeypatch.setattr(engine.maps,'localize_goods',inspect)
    engine._ensure_market(game,random.Random(20))
    assert captured
    supplied={r['content_id'] for r in captured if r['kind']=='technique'}
    auction={r['content_id'] for r in engine._auction_goods_pool(world) if r['kind']=='technique'}
    for family in RARE_FAMILIES:
        for role in ROLES:
            t=art(cap,family,role,path)
            assert t.id not in supplied
            assert t.id in auction
            assert engine._is_world_market_good(world,'technique',t.id)
    for family in ('neutral','metal','wind','metal_water','metal_water_wood','metal_wood_water_earth'):
        assert art(cap,family,'main',path).id in supplied
    assert all(natural_market_acquisition_allowed(r['kind'],r['content_id']) for r in game.market_offers)
    assert not any(t.element=='five_elements' and t.id in supplied for t in TECHNIQUE_CATALOG.values())


def shelf_offer(game,t):
    return dict(id='legacy-rare-art',kind='technique',content_id=t.id,name=t.name,
                description='旧坊市页面',element=t.element,price=100,tier=1,tier_name='练气',
                market_name='书坊',world=game.player.world,location_id=game.player.location_id,
                rare_next_tier=False,sold=False,locked=True)


@pytest.mark.parametrize('family',RARE_FAMILIES)
def test_stale_purchase_and_lock_reject_without_charging_or_granting(ready,family):
    engine,game=ready;t=art(family=family)
    add_item(game.player,'spirit_stone',1000)
    engine.store.save(game)
    # Hydrate once, then exercise both command guards against a stale request cache.
    with request_scope(engine):
        loaded=engine._load(game.id)
        loaded.market_offers.append(shelf_offer(loaded,t));engine.store.save(loaded)
        before=engine.store._path(game.id).read_bytes();state=copy.deepcopy(loaded.to_dict())
        with pytest.raises(ValueError,match='坊市直售'):
            engine.buy_market_offer(game.id,'legacy-rare-art')
        assert loaded.to_dict()==state and engine.store._path(game.id).read_bytes()==before
        with pytest.raises(ValueError):engine.toggle_market_offer_lock(game.id,'legacy-rare-art')
        assert loaded.to_dict()==state and engine.store._path(game.id).read_bytes()==before


def test_refresh_drops_cached_and_reserved_rare_offers_but_keeps_owned_books(ready):
    from cultivation_life.system.economy.state import local_market
    engine,game=ready;t=art(family='wind_yin_yang')
    engine._ensure_market(game,random.Random(1))
    acquire_technique(game.player,t);add_technique_copy(game.player,t)
    books=copy.deepcopy(game.player.known_techniques);inventory=copy.deepcopy(game.player.inventory)
    offer=shelf_offer(game,t)
    game.market_offers.append(offer)
    assert not any(o['content_id']==t.id for o in engine._public_market(game)['offers'])
    # Same-year cache and a later return to locally reserved shelves both obey the rule.
    engine._ensure_market(game,random.Random(2))
    assert not any(o['content_id']==t.id for o in game.market_offers)
    local_market(game)['reserved_offers']=[copy.deepcopy(offer)]
    game.market_age=None
    engine._ensure_market(game,random.Random(3))
    assert not any(o['content_id']==t.id for o in game.market_offers)
    assert not local_market(game).get('reserved_offers')
    assert game.player.known_techniques==books and game.player.inventory==inventory
