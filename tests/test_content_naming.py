"""Naming changes preserve saved ownership, progression and transaction references."""
import copy
import tempfile
import unittest
from pathlib import Path

from cultivation_life.content_identifiers import (
    LEGACY_CONTENT_IDS, canonical_content_id, normalize_content_references,
)
from cultivation_life.content_registry import ITEM_CATALOG, TECHNIQUE_CATALOG
from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState, Item
from cultivation_life.rules import add_item, public_catalog_entry, breakthrough_opportunity_required
from test_other_systems_audit_fixes import api

ROOT = Path(__file__).resolve().parents[1]


def legacy_fixture(engine):
    made = engine.create_game('旧名兼容', 'supreme_metal', 'dao', 61983, preset_id='nascent')
    game = engine._load(made['id'])
    game.pending_event = None
    game.player.realm_index, game.player.layer = 4, 3
    technique = copy.deepcopy(TECHNIQUE_CATALOG['TECH_YELLOW_COURT_INNER'])
    technique.id, technique.name, technique.level = 'TECH_COMMON_NASCENT', '婴神太虚录', 5
    game.player.known_techniques = [technique]
    game.player.technique = copy.deepcopy(technique)
    game.player.support_technique = None
    game.player.inventory = [Item(
        id='nascent_flame_crystal', name='婴火玄晶', quantity=7,
    ), Item(
        id='technique_manual::TECH_COMMON_NASCENT::lv5', name='《婴神太虚录》Lv.5 传承玉简',
        quantity=2, technique_id='TECH_COMMON_NASCENT', technique_level=5,
        technique_origin_realm_index=4,
    ), Item(id='custom-sword', name='婴神太虚录', quantity=1, combat_bonus=123)]
    add_item(game.player, 'spirit_stone', 10000)
    # The old page's opaque offer ID must remain usable after its content ID changes.
    game.market_world, game.market_location_id = game.player.world, game.player.location_id
    game.market_age, game.market_realm_index = game.player.age, 4
    game.market_offers = [dict(
        id='legacy-flame-offer', kind='item', content_id='nascent_flame_crystal',
        name='婴火玄晶', description='炼器用婴火玄晶', tier=4, price=123,
        sold=False, locked=False, rare_next_tier=False, market_name='测试坊市',
        world=game.player.world, location_id=game.player.location_id,
    )]
    engine.store.save(game)
    return game


class ContentNamingTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='content-naming-')
        self.addCleanup(self.folder.cleanup)
        self.engine = GameEngine(ROOT, Path(self.folder.name) / 'saves')

    def test_aliases_are_complete_one_way_and_manual_levels_survive(self):
        catalog = ITEM_CATALOG | TECHNIQUE_CATALOG
        self.assertEqual(len(set(LEGACY_CONTENT_IDS.values())), len(LEGACY_CONTENT_IDS))
        for old, new in LEGACY_CONTENT_IDS.items():
            self.assertNotIn(old, catalog)
            self.assertIn(new, catalog)
            self.assertEqual(canonical_content_id(new), new)
            if old.startswith('TECH_'):
                self.assertEqual(canonical_content_id(f'technique_manual::{old}::lv7'), f'technique_manual::{new}::lv7')
        self.assertEqual(canonical_content_id('custom-nascent-item'), 'custom-nascent-item')

    def test_references_normalize_without_touching_text_or_resources(self):
        source = dict(
            name='nascent_incense', description='TECH_COMMON_NASCENT',
            history=[dict(summary='婴神太虚录', text='nascent_incense')],
            inventory=[dict(id='nascent_incense', name='婴神香', quantity=9)],
            ghost_core_state=dict(known_techniques=[dict(id='TECH_COMMON_NASCENT', level=6)]),
            active_breakthrough_aids=['infant_soul_dew'],
            refined_inheritances={'TECH_COMMON_NASCENT': 7},
            commodities={'nascent_incense': dict(stock=9, price=100, volume=5)},
            cargo=dict(item='nascent_incense', quantity=3, paid=450),
            lots=[dict(kind='item', content_id='mahayana_spirit_pill', current_bid=999)],
            inputs={'nascent_flame_crystal': 2},
        )
        original = copy.deepcopy(source)
        result = normalize_content_references(source)
        self.assertEqual(source, original)
        self.assertEqual(result['name'], source['name'])
        self.assertEqual(result['description'], source['description'])
        self.assertIs(result['history'], source['history'])
        self.assertEqual(result['inventory'], [dict(id='purple_mansion_incense', name='婴神香', quantity=9)])
        self.assertEqual(result['commodities']['purple_mansion_incense'], source['commodities']['nascent_incense'])
        self.assertEqual(result['cargo'], dict(item='purple_mansion_incense', quantity=3, paid=450))
        self.assertEqual(result['active_breakthrough_aids'], ['moon_soul_dew'])
        self.assertEqual(result['refined_inheritances'], {'TECH_YELLOW_COURT_INNER': 7})
        self.assertEqual(result['ghost_core_state']['known_techniques'][0], dict(id='TECH_YELLOW_COURT_INNER', level=6))
        self.assertEqual(result['inputs'], {'radiant_flame_crystal': 2})
        self.assertEqual(result['lots'][0]['current_bid'], 999)
        self.assertIs(normalize_content_references(result), result)

    def test_real_load_preserves_quantities_levels_custom_names_and_file(self):
        game = legacy_fixture(self.engine)
        path = self.engine.store._path(game.id)
        original = path.read_bytes()
        decoded = self.engine.store.load(game.id)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(decoded.player.technique.id, 'TECH_YELLOW_COURT_INNER')
        self.assertEqual(decoded.player.technique.level, 5)
        self.assertEqual(decoded.market_offers[0]['id'], 'legacy-flame-offer')
        self.assertEqual(decoded.market_offers[0]['content_id'], 'radiant_flame_crystal')
        shown = self.engine.present(decoded)
        known = shown['player']['known_techniques'][0]
        self.assertEqual((known['id'], known['name'], known['level']), ('TECH_YELLOW_COURT_INNER', '黄庭内景经', 5))
        bag = {r['id']: r for r in shown['player']['inventory']}
        self.assertEqual((bag['radiant_flame_crystal']['name'], bag['radiant_flame_crystal']['quantity']), ('离照玄晶', 7))
        manual = bag['technique_manual::TECH_YELLOW_COURT_INNER::lv5']
        self.assertEqual(manual['quantity'], 2)
        self.assertIn('黄庭内景经', manual['name'])
        self.assertEqual((bag['custom-sword']['name'], bag['custom-sword']['combat_bonus']), ('婴神太虚录', 123))
        offer = next(r for r in shown['market']['offers'] if r['id'] == 'legacy-flame-offer')
        self.assertEqual((offer['name'], offer['base_price'], offer['sold']), ('离照玄晶', 123, False))
        self.assertEqual(decoded.market_offers[0]['name'], '婴火玄晶')
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(GameState.from_dict(decoded.to_dict()).player.technique.level, 5)

    def test_stale_technique_command_uses_original_manuals_once(self):
        game = legacy_fixture(self.engine)
        self.engine.upgrade_technique(game.id, 'TECH_COMMON_NASCENT')
        saved = self.engine.store.load(game.id)
        self.assertEqual(saved.player.technique.level, 6)
        self.assertEqual(saved.player.known_techniques[0].level, 6)
        manual = next(i for i in saved.player.inventory if i.technique_id == 'TECH_YELLOW_COURT_INNER')
        self.assertEqual((manual.quantity, manual.technique_level), (1, 5))

    def test_complete_current_schema_round_trip_keeps_economy_and_escrow(self):
        game = self.engine._load(legacy_fixture(self.engine).id)
        game.auction_state = dict(status='scheduled', world=game.player.world, lots=[
            dict(kind='technique' if identity in TECHNIQUE_CATALOG else 'item',
                 content_id=identity, current_bid=12345, quantity=3)
            for identity in LEGACY_CONTENT_IDS.values()
        ])
        current = game.to_dict()
        reverse = {new: old for old, new in LEGACY_CONTENT_IDS.items()}
        def old_spelling(value):
            if isinstance(value, dict):
                return {reverse.get(k, k): old_spelling(v) for k, v in value.items()}
            if isinstance(value, list):
                return [old_spelling(v) for v in value]
            if isinstance(value, str):
                if value.startswith('technique_manual::'):
                    book, separator, level = value[len('technique_manual::'):].partition('::lv')
                    return 'technique_manual::' + reverse.get(book, book) + separator + level
                return reverse.get(value, value)
            return value
        legacy = old_spelling(current)
        original = copy.deepcopy(legacy)
        self.assertEqual(GameState.from_dict(legacy).to_dict(), GameState.from_dict(current).to_dict())
        self.assertEqual(legacy, original)

    def test_stale_item_command_keeps_breakthrough_qualification(self):
        game = legacy_fixture(self.engine)
        aid = copy.deepcopy(ITEM_CATALOG['jade_pivot_pill'])
        aid.id, aid.name = 'infant_transformation_pill', '婴变丹'
        game.player.inventory.append(aid)
        game.player.awaiting_minor_breakthrough = True
        game.player.opportunity = breakthrough_opportunity_required(game.player)
        self.engine.store.save(game)
        shown = self.engine.use_item(game.id, 'infant_transformation_pill')
        self.assertIn('jade_pivot_pill', shown['player']['active_breakthrough_aids'])
        self.assertFalse(any(i['id'] == 'jade_pivot_pill' for i in shown['player']['inventory']))
        with self.assertRaises(ValueError):
            self.engine.use_item(game.id, 'infant_transformation_pill')

    def test_market_and_auction_projection_preserves_price_and_custom_artifact(self):
        row = dict(kind='technique', content_id='TECH_CICADA_METAMORPHOSIS', name='无相夺舍经',
                   description='无相夺舍经的旧拍卖签', price=19000, sold=True)
        original = copy.deepcopy(row)
        shown = public_catalog_entry(row)
        self.assertEqual(shown['name'], '蝉蜕玄章')
        self.assertTrue(shown['description'].startswith('蝉蜕玄章的旧拍卖签'))
        self.assertIn('成功夺舍次数上限 +1', shown['description'])
        self.assertEqual((shown['price'], shown['sold']), (19000, True))
        self.assertEqual(row, original)
        custom = dict(kind='crafted_artifact', content_id='radiant_flame_crystal', name='我的婴火剑')
        self.assertEqual(public_catalog_entry(custom), custom)

    def test_ambiguous_stock_rejected_without_overwrite(self):
        source = dict(commodities={'nascent_incense': dict(stock=4), 'purple_mansion_incense': dict(stock=7)})
        original = copy.deepcopy(source)
        with self.assertRaisesRegex(ValueError, '不能自动覆盖'):
            normalize_content_references(source)
        self.assertEqual(source, original)

    def test_legacy_procurement_order_completes_once_after_load(self):
        game = self.engine._load(legacy_fixture(self.engine).id)
        alliance = game.merchant_state['worlds']['human'][0]
        game.player.location_id = alliance['hq']
        add_item(game.player, 'spirit_stone', 10**8)
        self.engine._merchant_post(game, alliance, dict(
            kind='item', definition_id='jade_pivot_pill', quantity=2))
        order = game.merchant_state['posted'][-1]
        order.update(definition_id='infant_transformation_pill',
                     status='working', worker='验收承接人', will_finish=True,
                     started_age=game.player.age, finish_age=game.player.age + 1)
        self.engine.store.save(game)
        path = self.engine.store._path(game.id)
        original = path.read_bytes()
        loaded = self.engine._load(game.id)
        self.assertEqual(path.read_bytes(), original)
        loaded.player.age += 1
        self.engine._advance_merchant_year(loaded)
        completed = loaded.merchant_state['posted'][-1]
        self.assertEqual(completed['status'], 'completed')
        self.assertEqual(completed['definition_id'], 'jade_pivot_pill')
        self.assertTrue(completed['delivery_claimed'])
        self.assertEqual(next(i.quantity for i in loaded.player.inventory if i.id == 'jade_pivot_pill'), 2)
        inventory = copy.deepcopy(loaded.player.inventory)
        self.engine._advance_merchant_year(loaded)
        self.assertEqual(loaded.player.inventory, inventory)

    def test_legacy_npc_combat_artifact_survives_loading(self):
        from cultivation_life.system.combat_loadout import public_loadout
        game = self.engine._load(legacy_fixture(self.engine).id)
        npc = next(n for n in self.engine._all_world_npcs(game) if n.world == 'human')
        npc.combat_artifact_id = 'heaven_reaching_treasure'
        npc.treasure_item_id = 'heaven_reaching_treasure'
        self.engine.store.save(game)
        path = self.engine.store._path(game.id)
        original = path.read_bytes()
        loaded = self.engine.store.load(game.id)
        saved = self.engine._find_npc(loaded, npc.id)
        self.assertEqual(public_loadout(loaded, saved)['combat_artifact_name'], '承天如意')
        self.assertEqual(saved.combat_artifact_id, 'heaven_bearing_scepter')
        self.assertEqual(saved.treasure_item_id, 'heaven_bearing_scepter')
        self.assertEqual(path.read_bytes(), original)


def test_stale_procurement_request_keeps_qualification_and_delivers_once(api):
    engine, act = api
    game = engine._load(legacy_fixture(engine).id)
    alliance = game.merchant_state['worlds']['human'][0]
    game.player.location_id = alliance['hq']
    game.player.next_tribulation_age = None
    game.settings['silent_events'] = True
    add_item(game.player, 'spirit_stone', 10**8)
    engine.store.save(game)
    act(game.id, 'merchant-action', action='join', alliance_id=alliance['id'])
    payload = dict(kind='item', definition_id='infant_transformation_pill',
                   quantity=2, alliance_id=alliance['id'])
    quote = act(game.id, 'merchant-preview', **payload)
    assert quote['definition_id'] == 'jade_pivot_pill'
    act(game.id, 'merchant-action', action='post', preview_token=quote['preview_token'], **payload)
    saved = engine._load(game.id)
    order = saved.merchant_state['posted'][-1]
    assert order['definition_id'] == 'jade_pivot_pill'
    order.update(status='working', worker='验收承接人', will_finish=True,
                 started_age=saved.player.age, finish_age=saved.player.age + 1)
    engine.store.save(saved)
    original = engine.store._path(game.id).read_bytes()
    act(game.id, 'merchant-preview', kind='item', definition_id='heroic_progeny_elixir',
        alliance_id=alliance['id'], status=400)
    assert engine.store._path(game.id).read_bytes() == original
    act(game.id, 'advance', action='rest', years=1)
    finished = engine.store.load(game.id)
    assert finished.merchant_state['posted'][-1]['status'] == 'completed'
    assert next(i.quantity for i in finished.player.inventory if i.id == 'jade_pivot_pill') == 2
    act(game.id, 'advance', action='rest', years=1)
    assert next(i.quantity for i in engine.store.load(game.id).player.inventory if i.id == 'jade_pivot_pill') == 2


if __name__ == '__main__':
    unittest.main()
