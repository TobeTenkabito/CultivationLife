import copy
import random

import pytest

from test_immortal_cultivation import prepared
from cultivation_life.content_registry import WORLD_SYSTEMS, TECHNIQUE_CATALOG, MARKET_GOODS
from cultivation_life.engine.combat_capabilities import bind_capabilities
from cultivation_life.models import Player, SectNpc
from cultivation_life.rules import max_hp, max_mp, intrinsic_resource_breakdown, technique_copy_count, upgrade_known_technique
from cultivation_life.system.combat_system import BattleUnit
from cultivation_life.system.cultivation_ranks import describe, rank_for, ensure_npc, npc_voisinage_limit, body_rank
from cultivation_life.system.immortal_aperture import public_aperture, energy_state
from cultivation_life.system.spirit_voisinage import catalog, grant, player_source, offers
from cultivation_life.system.teleport_system import public_teleport, separated


def test_quickstart_and_rank_coordinates(prepared):
    engine, game, _ = prepared
    p = game.player
    assert p.body_training == 100 and p.immortal_body['level'] == 1
    assert p.immortal_aperture['current'] == 300
    assert describe(100)['name'] == '大乘后期'
    assert {describe(i)['realm_index'] for i in range(101)} == set(range(9))
    assert all(body_rank(100, n) <= body_rank(100, n+1) for n in range(100))
    data = p.to_dict(); data.pop('cultivation_ranks_schema'); data['divine_sense_rank'] = 77
    loaded = Player.from_dict(data)
    assert loaded.divine_sense_rank == rank_for(9)
    assert Player.from_dict(loaded.to_dict()).divine_sense_rank == loaded.divine_sense_rank
    from cultivation_life.system.cultivation_ranks import legacy_sense
    assert all(legacy_sense(n) < legacy_sense(n+1) for n in range(300))


def test_npc_independent_ranks_and_rare_late_fields():
    late = 0
    for i in range(200):
        npc = SectNpc(str(i), '修士', '', 9, 1, 1000, None)
        ensure_npc(npc)
        assert npc.divine_sense_rank >= rank_for(9)
        assert npc_voisinage_limit(npc) == 3
        original = npc.body_training
        ensure_npc(npc)
        assert npc.body_training == original
        npc.layer = 7
        late += npc_voisinage_limit(npc) >= 4
        npc.realm_index = 10
        ensure_npc(npc)
        assert npc.immortal_body_level >= 20 and npc.body_training == 100
    assert 8 <= late <= 45


def test_manual_guidance_gives_inventory_copy_not_level(prepared):
    from cultivation_life.system.doctrine.daomen import discover
    from cultivation_life.system.doctrine.provider import config
    engine, game, d = prepared
    for _ in range(2):
        peer = discover(game, d['id'], d, WORLD_SYSTEMS['transcendent_combat'], config()['words'])
    book = next(t for t in game.player.known_techniques if t.doctrine_id == d['id'])
    before = technique_copy_count(game.player, book.id, 1)
    engine.store.save(game)
    engine.doctrine_action(game.id, 'teach_manual', d['id'], book.id, npc_id=peer.id)
    p = engine.store.load(game.id).player
    assert next(t for t in p.known_techniques if t.id == book.id).level == 1
    assert technique_copy_count(p, book.id, 1) == before + 1


def test_aperture_combat_is_independent_and_reload_never_refills(prepared):
    engine, game, d = prepared
    game.doctrine_state['player']['progress'][d['id']]['level'] = 4
    game.doctrine_state['player']['active'] = d['id']
    mp = game.player.mp
    binding = bind_capabilities(game, [BattleUnit('player', '测试', 'player', 100, 9)],
        dict(target_name='石像', target_power=100, target_realm_index=8), WORLD_SYSTEMS['transcendent_combat'])
    caps = binding.battle.units['player'].unit.capabilities
    assert caps.current == 300 and caps.resource_link == 'independent'
    binding.commit([dict(id='player', resource_link='independent', current=7, vitality=1, suppressed=False)])
    assert game.player.mp == mp and energy_state(game.player)['current'] == 7
    engine.store.save(game)
    for _ in range(3):
        shown = engine.get_game(game.id)
        assert shown['aperture']['current'] == 7


def test_lower_domain_costs_intrinsic_and_does_not_consume_sealed_reserve(prepared):
    engine, game, d = prepared
    p = game.player
    p.world='spirit'; p.location_id=engine.maps.default_location('spirit')
    game.doctrine_state['player']['progress'][d['id']]['level']=4
    game.doctrine_state['player']['active']=d['id']
    p.hp=max_hp(p); p.mp=max_mp(p)
    field=player_source(game).voisinages[0]
    original=d['stages'][3]['voisinage']
    assert field.strength == pytest.approx(original['strength'] * .04)
    assert energy_state(p)['current'] == 0
    before=intrinsic_resource_breakdown(p)
    engine.store.save(game)
    result=engine.aperture_action(game.id,'refine')
    p=engine.store.load(game.id).player
    after=intrinsic_resource_breakdown(p)
    assert result['aperture']['current']==20 and p.immortal_aperture['current']==300
    assert after['mp']['maximum']==before['mp']['maximum']
    assert after['mp']['current']==pytest.approx(before['mp']['current']*.65)
    assert after['hp']['current']==pytest.approx(before['hp']['current']*.85)


def test_spirit_manual_only_restricted_sources_and_level4(prepared):
    engine, game, _=prepared
    p=game.player;p.world='spirit';p.realm_index=6;p.location_id=engine.maps.default_location('spirit')
    p.immortal_power_converted=False; p.immortal_conversion_stage=0
    books=catalog(game);assert len(books)==25
    assert not set(books)&set(TECHNIQUE_CATALOG)
    assert not set(books)&{row['content_id'] for row in MARKET_GOODS}
    book=grant(game,next(iter(books)),3)
    assert not player_source(game).voisinages
    book=next(t for t in p.known_techniques if t.id==book.id);book.level=4
    assert player_source(game).voisinages and public_aperture(p,game)['field']
    first=[t.id for t in offers(game,'black_market','one-opening')]
    assert first==[t.id for t in offers(game,'black_market','one-opening')]
    p.world='human';assert offers(game,'black_market','one-opening')==[]


def test_all_maps_expanded_and_no_adjacent_array_nodes(prepared):
    engine,game,_=prepared
    for world, geography in engine.maps.worlds.items():
        assert len(geography['locations']) >= 21
        nodes={r['id'] for r in geography['locations'] if r.get('teleport_array')}
        assert len(nodes)>=4
        for edge in geography['routes']:
            assert not {edge['from'],edge['to']}<=nodes
    plan=engine.maps.travel_plan('celestial','jade_capital','expanse_celestial_1',9)
    assert plan.years != 100 and plan.years>1


def test_array_permission_bribe_zero_time_and_adjacency_enforced(prepared):
    engine,game,_=prepared
    info=public_teleport(game,engine.maps)
    assert info['origin'] and info['destinations']
    dest=info['destinations'][0]['id'];age=game.player.age
    engine.store.save(game)
    with pytest.raises(ValueError,match='许可'):
        engine.teleport_action(game.id,'travel',dest)
    result=engine.teleport_action(game.id,'bribe',dest)
    assert result['player']['age']==age and result['player']['location_id']==dest
    game=engine.store.load(game.id);game.player.fame=10000;engine.store.save(game)
    engine.teleport_action(game.id,'request')
    game=engine.store.load(game.id)
    assert public_teleport(game,engine.maps)['origin']['licensed']
    neighbor=engine.maps._graphs[game.player.world][dest][0][0]
    with pytest.raises(ValueError,match='相邻'):
        engine._instant_arrival(game,neighbor)


def test_merchant_internal_array_needs_membership_but_not_map_fixture(prepared):
    engine,game,_=prepared
    engine._ensure_merchant(game)
    alliance=game.merchant_state['worlds']['celestial'][0]
    game.player.location_id=alliance['hq'];age=game.player.age;engine.store.save(game)
    with pytest.raises(ValueError,match='成员'):
        engine.merchant_action(game.id,'teleport',{'alliance_id':alliance['id'],'destination':alliance['offices'][0]['location_id']})
    engine.merchant_action(game.id,'join',{'alliance_id':alliance['id']})
    dest=next(o['location_id'] for o in alliance['offices'] if separated(engine.maps,'celestial',alliance['hq'],o['location_id']))
    result=engine.merchant_action(game.id,'teleport',{'alliance_id':alliance['id'],'destination':dest})
    assert result['player']['age']==age and result['player']['location_id']==dest


def test_black_market_spirit_manual_purchase_and_merge(prepared):
    engine,game,_=prepared
    game.player.world='spirit';game.player.location_id=engine.maps.default_location('spirit')
    opening=next(str(i) for i in range(30) if offers(game,'black_market',str(i)))
    game.auction_state=dict(id=opening,status='black_market',world='spirit',location_id=game.player.location_id)
    engine.store.save(game)
    result=engine.search_black_market(game.id,'灵域残解')
    row=next(r for r in result['auction_system']['black_market_results'] if r['kind']=='spirit_manual')
    engine.buy_black_market_item(game.id,row['id'],8)
    saved=engine.store.load(game.id)
    assert technique_copy_count(saved.player,row['content_id'],1)==7
    from cultivation_life.rules import merge_technique_copies
    for level in (1,2):
        while technique_copy_count(saved.player,row['content_id'],level)>=2:
            merge_technique_copies(saved.player,row['content_id'],level)
    for level in (2,3,4):
        assert upgrade_known_technique(saved.player,row['content_id'])==level
    assert player_source(saved).voisinages


def test_spirit_manual_commission_uses_real_elapsed_delivery(prepared):
    from test_merchant_commissions import complete
    engine,game,_=prepared
    game.player.world='spirit'
    engine._ensure_merchant(game)
    alliance=game.merchant_state['worlds']['spirit'][0]
    game.player.location_id=alliance['hq']
    book=next(iter(catalog(game).values()))
    payload=dict(kind='spirit_manual',source_world='spirit',definition_id=book.id,quantity=2)
    engine._merchant_post(game,alliance,payload)
    assert not any(t.id==book.id for t in game.player.known_techniques)
    order=complete(engine,game)
    assert order['kind']=='spirit_manual'
    assert technique_copy_count(game.player,book.id,1)==1
    payload['source_world']='human'
    with pytest.raises(ValueError):engine._merchant_quote(game,alliance,payload)


def test_aperture_capacity_grows_without_refilling(prepared):
    _,game,_=prepared
    game.player.immortal_aperture['current']=17
    game.player.realm_index=10
    state=energy_state(game.player)
    assert state['capacity']==4000 and state['current']==17


def test_spirit_authority_is_not_double_discounted_against_unprotected_target(prepared):
    from cultivation_life.system.combat.contracts import CombatCapabilities, Combatant
    from cultivation_life.system.combat.voisinages import VoisinageBattle
    _,game,d=prepared
    game.player.world='spirit'
    game.doctrine_state['player']['progress'][d['id']]['level']=4
    game.doctrine_state['player']['active']=d['id']
    source=player_source(game);field=source.voisinages[0]
    assert field.authority_reference==4
    caps=CombatCapabilities(capacity=60,current=20,resource_tier=2,voisinages=(field,),attainments=source.attainments)
    battle=VoisinageBattle([Combatant('caster','灵域修士','player',100,caps),Combatant('victim','凡修','enemy',10000)])
    # Use the same public phase interface as the conventional battle adapter.
    battle.begin_round(1,player_condition=1,enemy_condition=1,player_mp=1,enemy_mp=1)
    target=battle.units['victim']
    assert target.vitality < .9 or target.seal_progress > .1
    assert battle.units['caster'].current < 20
    from cultivation_life.system.combat.contracts import VoisinageDefinition
    complete=VoisinageDefinition(**d['stages'][3]['voisinage'])
    protected=CombatCapabilities(capacity=1000,current=1000,resource_tier=2,voisinages=(complete,),attainments=source.attainments)
    battle=VoisinageBattle([Combatant('caster','灵域修士','player',100,caps),Combatant('victim','完整仙域','enemy',100,protected)])
    frame=battle.begin_round(1,player_condition=1,enemy_condition=1,player_mp=1,enemy_mp=1)
    assert frame.relations['caster']['relation']=='dominated'
    assert battle.units['victim'].vitality==1
