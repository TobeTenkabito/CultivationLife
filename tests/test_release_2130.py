"""Actual reward use, bounded recipes, treasury conservation and independent dungeon state."""
import copy
import json
from pathlib import Path
import pytest
from cultivation_life.engine import GameEngine
from cultivation_life.content_registry import WORLD_SYSTEMS, GUIXU_TIDE_CONTENT, ITEM_CATALOG
from cultivation_life.generated_loot_schema import validate_reward
from cultivation_life.system.generated_loot import generate_rewards, grant
from cultivation_life.system.economy.organizations import welfare
from cultivation_life.system.economy.organization_accounts import register, key
from cultivation_life.system.economy.ledger import balance, transfer_value
from cultivation_life.system import trial_sites

ROOT=Path(__file__).resolve().parents[1]
@pytest.fixture
def local(tmp_path):
    engine=GameEngine(ROOT,tmp_path/'saves')
    made=engine.create_game('山海验收','supreme_metal','dao',300,custom_start=dict(world='human',realm_index=4,sect='new',sect_name='问道宗'))
    return engine,engine.store.load(made['id'])

@pytest.mark.parametrize('path',['dao','demonic','monster','ghost','buddhist','confucian'])
def test_random_loot_is_seeded_complete_and_not_a_catalog_copy(path):
    names=WORLD_SYSTEMS['trial_sites']['reward_names'];seen=set()
    for n in range(1,45):
        rows=generate_rewards(300,'human',n,4,path,names)
        assert rows==generate_rewards(300,'human',n,4,path,names)
        for row in rows:
            validate_reward(row);seen.add(row['roll']['family'])
            assert row['content_id'] not in ITEM_CATALOG
    assert seen=={'item','technique','artifact','treasure'}

@pytest.mark.parametrize('family',['item','technique','artifact','treasure'])
def test_random_loot_survives_save_load_and_original_use_ports(local,family):
    engine,game=local;names=WORLD_SYSTEMS['trial_sites']['reward_names']
    reward=next(r for n in range(1,100) for r in generate_rewards(300,'human',n,4,'dao',names) if r['roll']['family']==family)
    grant(game,reward);engine.store.save(game);engine.get_game(game.id)
    loaded=engine.store.load(game.id);assert loaded.player.age==game.player.age
    if family=='technique':
        engine.equip_known_technique(game.id,reward['content_id'],'combat')
        assert any(t.id==reward['content_id'] for t in engine.store.load(game.id).player.combat_techniques)
    elif family=='item':
        before=engine.store.load(game.id)
        engine.use_item(game.id,reward['content_id'])
        after=engine.store.load(game.id)
        assert not any(i.id==reward['content_id'] for i in after.player.inventory)
        assert after.player.age==before.player.age
    elif family=='artifact':
        assert any(r['id']==reward['content_id'] for r in loaded.player.crafted_artifacts)
    else:
        assert next(i for i in loaded.player.inventory if i.id==reward['content_id']).combat_bonus>0

@pytest.mark.parametrize('bad',[{'family':'script'},{'stats':{'world':2}},{'stats':{'combat_power':float('nan')}},{'stats':{'combat_power':float('inf')}}])
def test_invalid_reward_recipe_refused(bad):
    row=generate_rewards(300,'human',1,4,'dao',WORLD_SYSTEMS['trial_sites']['reward_names'])[0]
    row['roll'].update(bad)
    with pytest.raises(ValueError):validate_reward(row)


def test_sect_dividend_uses_actual_surplus_reserve_and_same_year_cursor(local):
    engine,game=local;entity=game.sects[game.player.faction_id];row=register(game,'sect',entity.id,'human');source=key('sect',entity.id)
    transfer_value(game,'background:human',source,1000000,'测试经营资金')
    row.update(income=100000,expense=10000,expected_upkeep=1000,shortfall=0)
    before=balance(game,'player');funds=balance(game,source);welfare(game,entity)
    assert row['dividend_rate']==.15 and row['dividend_paid']==int((100000-10000-100)*.15)
    assert balance(game,'player')-before==row['dividend_paid']
    assert funds-balance(game,source)==100+row['dividend_paid']
    snapshot=game.to_dict();assert welfare(game,entity)==0;assert game.to_dict()==snapshot
    assert balance(game,source)>=1950
    engine.store.save(game);assert engine.store.load(game.id).economy_v2['organizations'][source]['dividend_paid']==row['dividend_paid']


def test_two_dungeons_per_world_have_independent_finite_state(local):
    engine,game=local;catalog=GUIXU_TIDE_CONTENT['dungeons'];assert len(catalog)==22
    for world in trial_sites.REALM_ROWS:
        rows=[d for d in catalog if d['world']==world];assert len(rows)==2
        new=next(d for d in rows if d.get('unrestricted_entry'))
        assert not engine.maps.location(world,new['entry_location_id']).get('min_realm_index')
        a,b=(game.guixu_state['cycles'][d['id']] for d in rows)
        assert a is not b
        old=copy.deepcopy(b);a['pool_remaining'].pop();assert b==old
        assert set(r['id'] for r in rows[0]['treasure_pool']).isdisjoint(r['id'] for r in rows[1]['treasure_pool'])


def test_atlas_preserves_all_roads_with_zero_line_crossings():
    text=(ROOT/'web/map-layouts.js').read_text(encoding='utf-8')
    layout=json.loads(text.split('window.MapLayouts = ',1)[1].strip().rstrip(';'))
    maps=json.loads((ROOT/'content/maps.json').read_text(encoding='utf-8'))['worlds']
    def turn(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    for world,data in maps.items():
        row=layout[world];points=row['points'];lines=row['roads']
        assert set(points)=={p['id'] for p in data['locations']}
        assert {tuple(sorted(e)) for e in lines+row['portals']}=={tuple(sorted((r['from'],r['to']))) for r in data['routes']}
        for i,(a,b) in enumerate(lines):
            for c,d in lines[i+1:]:
                if len({a,b,c,d})<4:continue
                a1,b1,c1,d1=[points[p] for p in (a,b,c,d)]
                assert not (turn(a1,b1,c1)*turn(a1,b1,d1)<0 and turn(c1,d1,a1)*turn(c1,d1,b1)<0),world


@pytest.mark.parametrize('dungeon',[d for d in GUIXU_TIDE_CONTENT['dungeons'] if d.get('unrestricted_entry')],ids=lambda d:d['world'])
def test_new_dungeon_real_enter_return_and_independent_entry_receipt(tmp_path,dungeon):
    import random
    engine=GameEngine(ROOT,tmp_path/'saves')
    view=engine.create_game('新洞府入口','supreme_metal','dao',300,custom_start=dict(world=dungeon['world'],realm_index=max(1,dungeon['max_entry_rank'][0]-1)))
    game=engine._load(view['id']);game.player.location_id=dungeon['entry_location_id']
    cycle=game.guixu_state['cycles'][dungeon['id']]
    engine._open_guixu_cycle(game,dungeon,cycle,random.Random(300));game.pending_event=None;engine.store.save(game)
    other=next(d for d in GUIXU_TIDE_CONTENT['dungeons'] if d['world']==dungeon['world'] and d['id']!=dungeon['id'])
    untouched=copy.deepcopy(game.guixu_state['cycles'][other['id']])
    engine.guixu_action(game.id,'enter',{'dungeon_id':dungeon['id']})
    session=engine.store.load(game.id).guixu_state['player_session']
    assert session['dungeon_id']==dungeon['id']
    if session.get('pending_team_offer'):engine.guixu_action(game.id,'team_decline',{})
    engine.guixu_action(game.id,'return',{})
    saved=engine.store.load(game.id)
    assert saved.player.world==dungeon['world'] and saved.player.location_id==dungeon['entry_location_id']
    assert saved.guixu_state['player_session'] is None
    assert saved.guixu_state['cycles'][other['id']]==untouched
    assert list(saved.guixu_state['entered_cycles'])==[f"{dungeon['id']}:{cycle['cycle_index']}"]
    assert dungeon['period_years']==other['period_years']
    assert abs(dungeon['first_open_year']-other['first_open_year'])>=2
