import copy
import json
import random
from pathlib import Path
from unittest.mock import patch

import pytest

from test_merchant_commissions import setup, complete
from cultivation_life.content_registry import ContentRegistry, CONTENT, CONTENT_DOCUMENTS, ITEM_CATALOG
from cultivation_life.models import SectNpc
from cultivation_life.system.formation_system import calculate_formation_profile, formation_alpha

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('maxima', [{'kill':-1}, {'kill':float('nan')}, {'kill':float('inf')}, {'unknown':10}])
def test_invalid_maximum_is_rejected_without_payment(setup, maxima):
    engine, game, alliance = setup
    before = copy.deepcopy(game.to_dict())
    with pytest.raises(ValueError):
        engine._merchant_post(game, alliance, {'kind':'formation', 'metric_maxima':maxima})
    assert game.to_dict() == before


def test_upper_limits_and_real_delivery_preserve_requested_metrics(setup):
    engine, game, alliance = setup
    payload = {'kind':'formation','material_tier':2,'stars':5,'metric_maxima':{'kill':0,'change':20}}
    quote = engine._merchant_quote(game, alliance, payload)
    assert quote['spec']['profile']['metrics']['kill'] == 0
    assert quote['spec']['profile']['metrics']['change'] <= 20
    with pytest.raises(ValueError, match='下限'):
        engine._merchant_quote(game, alliance, payload | {'metrics':{'kill':1}})
    engine._merchant_post(game, alliance, payload)
    order = complete(engine, game)
    loadout = game.player.formation_loadouts[-1]
    definitions = engine._formation_material_defs()
    profile = calculate_formation_profile([definitions.get(key) for key in loadout['slots']], alpha=formation_alpha(game.player))
    assert profile['metrics'] == order['spec']['profile']['metrics']
    assert len(game.player.formation_materials) == profile['occupied_count'] + 4
    assert len({row['id'] for row in game.player.formation_materials}) == len(game.player.formation_materials)


def test_star_quality_and_cost_improve_with_same_materials_and_mold(setup):
    engine, game, alliance = setup
    quotes = [engine._merchant_quote(game, alliance, {'kind':'weapon','material_tier':2,'stars':stars}) for stars in range(1,6)]
    assert [row['spec']['quality'] for row in quotes] == ['normal','excellent','refined','epic','legendary']
    for previous, current in zip(quotes,quotes[1:]):
        assert current['minimum'] > previous['minimum']
        assert current['spec']['stats']['combat_power'] > previous['spec']['stats']['combat_power']
    engine._merchant_post(game, alliance, {'kind':'weapon','material_tier':2,'stars':5})
    complete(engine, game)
    assert game.player.crafted_artifacts[-1]['quality'] == 'legendary'
    assert game.player.crafted_artifacts[-1]['actual_stats'] == quotes[-1]['spec']['stats']


def test_high_star_procurement_adds_other_goods_and_legacy_does_not(setup):
    engine, game, alliance = setup
    item = 'jinque_metal'
    engine._merchant_post(game, alliance, {'kind':'item','definition_id':item,'quantity':2,'stars':5})
    order = complete(engine, game)
    assert len(order['bonus_items']) == 4
    assert next(row.quantity for row in game.player.inventory if row.id==item) == 2
    old = copy.deepcopy(order)
    old.update(commission_version=2,id=999)
    count = len(game.player.crafting_materials)
    engine._merchant_deliver_commission(game, old)
    assert len(game.player.crafting_materials) == count


def test_higher_stars_attract_more_senior_workers(setup):
    engine, game, alliance = setup
    workers = [SectNpc('low','初阶行商','',1,1,30,100,world='human'), SectNpc('high','高阶行商','',5,1,300,1000,world='human')]
    means = []
    with patch.object(engine, '_all_world_npcs', return_value=workers):
        for stars in (1,5):
            total = 0
            for seed in range(60):
                order = {'id':seed,'stars':stars,'kind':'intel','name':'打听','years':10,'source_world':'human'}
                engine._merchant_start_order(game, order, random.Random(seed))
                total += order['worker_realm']
            means.append(total/60)
    assert means[1] > means[0] + 1


def test_intel_without_tianji_only_reports_actual_npc_ties(setup):
    engine, game, _ = setup
    npcs = [SectNpc('a','张甲','',2,1,50,200,world='human',faction_id='same'),
            SectNpc('b','李乙','',3,1,60,400,world='human',faction_id='same')]
    old = copy.deepcopy(game.tianji_state)
    with patch('cultivation_life.system.tianji_system.tianji_content_available',return_value=False), patch.object(engine,'_all_world_npcs',return_value=npcs):
        report = engine._merchant_intelligence(game,'human',5,random.Random(1))
    assert '张甲' in report and '李乙' in report and '同门' in report
    assert '材料情报' not in report and '神机榜' not in report
    assert game.tianji_state == old


def test_tianji_intel_is_local_persistent_and_can_reveal_multiple_clues(setup):
    engine, game, _ = setup
    engine._ensure_tianji_state(game)
    game.tianji_state['knowledge'] = {}
    rng = random.Random(4)
    with patch.object(rng,'random',return_value=0):
        report = engine._merchant_intelligence(game,'true_demon',5,rng)
    known = game.tianji_state['knowledge']
    assert 1 < len(known) <= 5 and '神机榜线索' in report
    assert all(row['origin_world']=='true_demon' for row in game.tianji_state['artifacts'] if row['id'] in known)
    engine.store.save(game)
    assert engine._load(game.id).tianji_state['knowledge'] == known


def test_primary_secondary_worlds_have_complete_material_roles_and_natures(setup):
    engine, _, _ = setup
    for world in ('human','demon','spirit','true_demon','monster_realm','phantom_underworld','hell'):
        expected = set(range(1,6 if world in {'human','demon'} else 9))
        craft = [row for row in engine._crafting_material_defs().values() if row['world']==world]
        formation = [row for row in engine._formation_material_defs().values() if row['world']==world]
        assert {row['tier'] for row in craft} == {row['tier'] for row in formation} == expected
        for tier in expected:
            assert {role for row in craft if row['tier']==tier for role in row['roles']} == {'primary','secondary','quench'}
            assert len({row['nature'] for row in formation if row['tier']==tier}) == 14
            assert engine._merchant_weapon_spec(world,{'material_tier':tier})['material_tier']==tier


def test_generic_dlc_content_is_available_without_any_dlc(tmp_path):
    docs, report = ContentRegistry.loaded_documents, ContentRegistry.extension_report
    try:
        base = ContentRegistry.load(ROOT/'content',tmp_path)
        base_ids = {row['id'] for row in json.loads((ROOT/'content/items.json').read_text(encoding='utf-8'))['items']}
        assert base_ids <= base.items.keys()
        for key in ('monster_tempering_blood','confucian_jade_ruler','moque_wind','yaoque_thunder'):
            assert key in base.items
            assert any(row['content_id']==key for row in base.market_goods)
        assert 'guixu_canghai_equipment_01' in base.items  # Owned items remain readable without DLC.
        assert not any(row['content_id']=='guixu_canghai_equipment_01' for row in base.market_goods)
        assert 'TECH_GUIXU_CANGHAI_01' in base.techniques and 'TECH_MONSTER_BREATHING' in base.techniques
        assert 'people_annals_bamboo' not in base.items and 'ghost_nurturing_casket' not in base.items
        assert 'TECH_GHOST_BODY_THIEF' not in base.techniques
        assert len(base.items) < len(CONTENT.items)
    finally:
        ContentRegistry.loaded_documents, ContentRegistry.extension_report = docs, report


def test_mutated_root_manuals_and_old_inventory_names(setup):
    engine, game, _ = setup
    from cultivation_life.rules import add_item
    for prefix in ('zique','moque','yaoque','mingque'):
        for affinity in ('wind','thunder','yin','yang'):
            assert ITEM_CATALOG[f'{prefix}_{affinity}'].root_grant == affinity
    add_item(game.player,'moque_wind',1)
    item = next(row for row in game.player.inventory if row.id=='moque_wind')
    item.name='魔阙·风'
    game.player.world='true_demon';game.player.realm_index=5;game.player.layer=1
    engine.store.save(game)
    saved=engine._load(game.id)
    assert next(row for row in saved.player.inventory if row.id=='moque_wind').name=='魔阙天书·风'
    assert ITEM_CATALOG['yaoque_water'].name=='妖阙天书·水'
    engine.use_item(game.id, 'moque_wind')
    assert 'wind' in engine._load(game.id).player.additional_roots
