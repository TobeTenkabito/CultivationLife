"""手动运行的前端烟雾测试；使用临时存档，不接触玩家数据。"""

import tempfile
import threading
import sys
import random
from http.server import ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cultivation_life import server as server_module
from cultivation_life.engine import GameEngine
from cultivation_life.content_registry import REALMS
from cultivation_life.rules import TECHNIQUE_CATALOG, add_item, assign_technique, learn_technique, max_hp, max_mp, opportunity_required


def main() -> None:
    with tempfile.TemporaryDirectory() as save_directory:
        engine = GameEngine(ROOT, Path(save_directory))
        created = engine.create_game("前端烟测", "supreme_metal", "dao", 99001)
        game = engine.store.load(created["id"])
        game.player.realm_index = 1
        add_item(game.player, "spirit_stone", 100)
        learn_technique(game.player, TECHNIQUE_CATALOG["TECH_BASIC_QI"])
        learn_technique(game.player, TECHNIQUE_CATALOG["TECH_SPIRIT_SENSE"])
        learn_technique(game.player, TECHNIQUE_CATALOG["TECH_BEAST_TRANSFORMATION"])
        assign_technique(game.player, TECHNIQUE_CATALOG["TECH_SPIRIT_SENSE"], "divine_sense")
        assign_technique(game.player, TECHNIQUE_CATALOG["TECH_BEAST_TRANSFORMATION"], "transformation")
        game.player.known_transformations = ["FORM_PHOENIX", "FORM_AZURE_LUAN"]
        game.player.transformation_mastery = {
            "FORM_PHOENIX":{"purity":0.72, "material_id":"phoenix_soul_flame", "source_type":"元神"},
            "FORM_AZURE_LUAN":{"purity":0.68, "material_id":"azure_luan_essence", "source_type":"精魄"},
        }
        game.player.transformation_loadouts["TECH_BEAST_TRANSFORMATION"]["stored"] = [
            "FORM_PHOENIX", "FORM_AZURE_LUAN",
        ]
        game.player.transformation_loadouts["TECH_BEAST_TRANSFORMATION"]["active"] = [
            "FORM_PHOENIX", "FORM_AZURE_LUAN",
        ]
        add_item(game.player, "true_dragon_blood_trace", 2)
        game.player.divine_sense_rank = 1
        game.player.divine_sense_experience = 20
        engine._combat(game, {
            "target_name":"烟测木偶", "target_power":1, "target_realm_index":0,
            "target_layer":1, "combat_type":"cultivator", "action":"spar",
        }, False, random.Random(7))
        game.player.prisoners = [{
            "id":"smoke-captive", "name":"烟测俘虏", "realm_index":1, "layer":1,
            "realm_name":"练气1层", "path":"dao", "path_name":"道修", "affinity":-12,
            "combat_power":42, "captured_age":game.player.age,
        }]
        game.player.puppets = [{
            "id":"smoke-puppet", "name":"烟测机关", "type":"mechanical", "realm_index":1,
            "layer":1, "combat_power":35, "original_power":35, "main_technique_id":None,
            "control":100, "cultivation_progress":0, "breakthrough_bonus":0, "alive":True,
        }]
        game.player.foreign_souls = [
            {"id":"active-soul", "name":"未净烟魂", "strength":2, "progress":8, "required":64, "remaining_bonus":0.02, "refined":False},
            {"id":"refined-soul-1", "name":"旧魂甲", "strength":1, "progress":32, "required":32, "remaining_bonus":0, "refined":True},
            {"id":"refined-soul-2", "name":"旧魂乙", "strength":1, "progress":32, "required":32, "remaining_bonus":0, "refined":True},
        ]
        game.player.master = engine._relationship_snapshot("master-smoke", "烟霞真人", 2, 2, "event", 120, 230)
        game.player.disciples = [engine._relationship_snapshot("disciple-smoke", "青童", 0, 1, "event", 17, 90)]
        game.player.disciple_requests = [engine._relationship_snapshot("request-smoke", "求道童子", 0, 1, "event", 16, 88)]
        game.pending_event = engine._instantiate_event(
            engine.events_by_id["EVT_CULTIVATE_INSIGHT_001"], game, random.Random(1)
        )
        engine.store.save(game)
        server_module.ENGINE = engine
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server_module.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                response = page.goto(f"http://127.0.0.1:{httpd.server_port}")
                assert "no-store" in response.headers.get("cache-control", "")
                page.locator("#achievement-open").click()
                page.locator("#achievement-screen").wait_for(state="visible")
                assert page.locator(".achievement-row").count() == 21
                assert page.get_by_role("heading", name="本体成就").is_visible()
                assert page.locator(".achievement-row.locked").count() == 21
                assert "解锁条件：取得沧海玄鼎" in page.locator(".achievement-row").first.text_content()
                page.locator("#achievement-close").click()
                page.locator("#new-game-form").wait_for(state="visible")
                assert page.locator(".quick-start-button").count() == 8
                assert page.locator(".quick-start-button:not([disabled])").count() == 8
                assert page.locator(".quick-start-button[disabled]").count() == 0
                page.locator("#path-select").select_option("monster")
                assert page.locator("#monster-species-field").is_visible()
                assert page.locator("#monster-species-select option").count() == 8
                page.locator("#monster-species-select").select_option("avian")
                page.locator("#new-game-form input[name='name']").fill("羽族烟测")
                page.locator("#new-game-form button[type='submit']").click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                assert page.locator("[data-panel-target='bloodline']").is_visible()
                page.locator("[data-panel-target='bloodline']").click()
                page.locator("#bloodline-card").wait_for(state="visible")
                page.locator("#bloodline-current").get_by_text("山雀妖", exact=True).wait_for()
                assert "羽属" in page.locator("#bloodline-summary").text_content()
                assert page.locator("#bloodline-profile").count() == 0
                assert page.locator(".bloodline-profile > span").count() == 6
                monster_game_id = page.evaluate("game.id")
                page.evaluate("""renderMonsterBloodline({
                    visible:true, available:false,
                    reason:'血脉冻结测试', general_trait_pool_size:16,
                    general_traits:[{id:'monster_common_stout_hide',name:'坚韧皮膜',description:'防护提高 3%。'}]
                })""")
                assert "1 / 16" in page.locator("#bloodline-summary").text_content()
                assert "坚韧皮膜" in page.locator("#bloodline-current").text_content()
                assert "血脉冻结测试" in page.locator("#bloodline-note").text_content()
                monster_game = engine.store.load(monster_game_id)
                monster_game.player.world = "monster_realm"
                monster_game.player.location_id = "myriad_beast_city"
                monster_game.player.realm_index = 8
                monster_game.player.layer = REALMS[8].layers
                monster_game.player.monster_evolution_id = "AVIAN_MAHAYANA_KUNPENG"
                monster_game.player.monster_evolution_history = ["AVIAN_MAHAYANA_KUNPENG"]
                monster_game.player.opportunity = opportunity_required(monster_game.player)
                monster_game.player.awaiting_major_breakthrough = True
                engine.store.save(monster_game)
                page.reload()
                page.get_by_text("续接 · 羽族烟测").click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                page.locator("[data-panel-target='bloodline']").click()
                assert "罡羽破界" in page.locator("#bloodline-current").text_content()
                self_route = page.locator(".bloodline-candidate", has_text="万翼新祖")
                self_route.get_by_role("button").click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                page.locator(".custom-lineage-editor input").fill("万翼自在脉")
                page.get_by_role("button", name="追加规则").click()
                assert page.locator(".custom-lineage-rule").count() == 1
                lineage_rule = page.locator(".custom-lineage-rule").first
                lineage_rule.locator('select[data-field="schedule"]').select_option("even")
                lineage_rule.locator('select[data-field="condition"]').select_option("player_state_50")
                lineage_rule.locator('select[data-field="value"]').select_option("0.1")
                assert lineage_rule.locator(".rule-preview").text_content() == "偶数轮开始时，若己方态势不高于50%，自身威能提高10%。"
                assert "当前费用 8 点" in page.locator(".custom-lineage-total").text_content()
                assert "剩余血脉点数 16 / 24" in page.locator(".custom-lineage-total").text_content()
                assert "当前配置合法" in page.locator(".custom-lineage-invalid").text_content()
                page.get_by_role("button", name="确认立祖并进化").click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                assert "万翼自在脉" in page.locator(".custom-lineage-summary").text_content()
                assert page.evaluate("game.player.realm_index") == 9
                assert page.locator("#cross-world-action").is_visible()
                assert page.locator("#cross-world-secondary-action").is_visible()
                assert page.locator("#cross-world-action").get_attribute("data-destination") == "monster_realm"
                assert page.locator("#cross-world-secondary-action").get_attribute("data-destination") == "phantom_underworld"
                assert "族血 1/16" in page.locator("#bloodline-summary").text_content()
                page.locator("#new-game-button").click()
                page.locator("#new-game-form input[name='name']").fill("快速烟测")
                page.locator(".quick-start-button[data-preset-id='core']").click()
                page.get_by_text("结丹初期·1层", exact=True).wait_for()
                assert page.locator("#technique").text_content() != "尚未获得"
                assert len(page.locator(".left-dock").evaluate("node => getComputedStyle(node).gridTemplateColumns").split()) == 2
                page.locator("[data-panel-target='natal-artifact']").click()
                page.locator("#natal-artifact-card").wait_for(state="visible")
                assert page.get_by_role("button", name="炼为本命").count() >= 1
                page.get_by_role("button", name="炼为本命").first.click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                assert page.locator("#natal-artifact-card .natal-sword").count() == 1
                assert page.locator("#natal-artifact-card .natal-slot").count() == 7
                assert page.locator("#natal-artifact-card .natal-slot:not(.locked)").count() == 2
                page.locator("[data-panel-target='inventory']").click()
                assert page.locator("#inventory-list .natal-artifact-item").count() == 1
                page.locator("#new-game-button").click()
                page.get_by_text("续接 · 前端烟测").click()
                page.locator("#battle-report-open").click()
                page.locator("#battle-report-card").wait_for(state="visible")
                assert page.locator("#battle-stat-grid > div").count() == 6
                assert page.locator("#battle-round-progress > span").count() == 1
                assert "第 1 轮" in page.locator("#battle-round-progress > span").first.get_attribute("title")
                assert "开战后完全由预案自动执行" in page.locator("#battle-report-summary").text_content()
                assert page.locator("#battle-rosters section").count() == 2
                assert page.locator("#battle-rosters section span").count() >= 2
                assert page.locator("#battle-report-card").evaluate("node => getComputedStyle(node).position") == "fixed"
                page.locator("#battle-report-toggle").click()
                page.locator("#battle-report-card").wait_for(state="hidden")
                assert page.locator("#market-card").is_hidden()
                assert page.locator("#qi-mastery .qi-mastery-item").count() == 4
                assert page.locator("#art-mastery .art-mastery-item").count() == 5
                assert "Lv.0" in page.locator("#qi-mastery").text_content()
                assert page.get_by_text("战斗门槛", exact=False).count() >= 1
                assert not page.locator("details.techniques").evaluate("node => node.open")
                assert not page.locator("details.technique-library").evaluate("node => node.open")
                page.locator("[data-panel-target='world-npc']").click()
                page.locator("#world-npc-card").wait_for(state="visible")
                assert page.locator("#world-npc-list .world-npc-row").count() >= 1
                assert page.get_by_text("顾长庚", exact=False).count() == 1
                page.locator("#world-npc-toggle").click()

                page.locator("#event-choices button:not([disabled])").first.click()
                page.locator("#event-card").wait_for(state="hidden")
                assert page.locator("[data-action='cultivate']").is_enabled()
                assert page.locator("[data-action='sense_train']").is_enabled()
                assert page.locator("[data-action='hunt_beast']").is_enabled()
                assert page.locator("[data-action='spar']").is_enabled()
                assert page.locator("[data-action='slay']").is_enabled()
                assert page.locator(".primary-actions button").nth(0).get_attribute("data-action") == "cultivate"
                assert page.locator(".primary-actions button").nth(1).get_attribute("data-action") == "body_train"
                assert page.locator(".action-folds [data-action='travel']").count() == 1
                assert "当前境界期望战斗力" in page.locator("#combat-power").get_attribute("title")
                assert page.locator("#relationship-list").count() == 1
                assert page.locator("#dao-companion-list").count() == 1
                page.locator("[data-panel-target='relationship']").click()
                page.locator("#relationship-card").wait_for(state="visible")
                assert page.get_by_text("烟霞真人").count() == 1
                assert page.get_by_text("120 岁 / 寿元 230", exact=False).count() == 1
                assert page.get_by_role("button", name="索要物品").is_enabled()
                assert page.get_by_role("button", name="收入门下").is_enabled()
                assert page.get_by_role("button", name="赠物").is_enabled()
                assert page.get_by_role("button", name="传功").is_enabled()
                page.locator("#relationship-toggle").click()

                page.locator("[data-panel-target='transformation']").click()
                page.locator("#transformation-card").wait_for(state="visible")
                assert "2/2" in page.locator("#transformation-summary").text_content()
                assert page.locator("#transformation-stored .transformation-form").count() == 2
                assert page.locator("#transformation-stored .transformation-form.active").count() == 2
                assert page.locator("#transformation-stored .transformation-progress").count() == 2
                assert page.locator("#transformation-materials .transformation-material").count() == 1
                assert page.locator("#transformation-materials select").count() == 1
                assert "直接培养" in page.locator("#transformation-materials").text_content()
                assert "67%" in page.locator("#transformation-note").text_content()
                page.locator("#transformation-toggle").click()

                page.locator("[data-panel-target='settings']").click()
                page.locator("#settings-card").wait_for(state="visible")
                assert not page.locator("#setting-combat-popup").is_checked()
                assert not page.locator("#setting-auto-war").is_checked()
                with page.expect_response(lambda response: response.url.endswith("/settings")):
                    page.locator("#setting-combat-popup").check()
                with page.expect_response(lambda response: response.url.endswith("/settings")):
                    page.locator("#setting-auto-war").check()
                assert engine.store.load(created["id"]).settings == {
                    "combat_popup": False, "achievement_popup": True,
                    "auto_advance_player_wars": True,
                }
                page.locator("#settings-toggle").click()

                page.locator("[data-panel-target='extension']").click()
                page.locator("#extension-card").wait_for(state="visible")
                assert "已识别 1" in page.locator("#extension-summary").text_content()
                assert "妖修道途：血脉与进化" in page.locator("#extension-list").text_content()
                page.locator("#extension-toggle").click()

                page.locator("[data-panel-target='captive']").click()
                page.locator("#captive-card").wait_for(state="visible")
                assert "神识容量 1/1" in page.locator("#puppet-capacity").text_content()
                assert page.locator("#captive-list .captive-row").count() == 1
                assert page.locator("#puppet-list .puppet-row").count() == 1
                assert "本体战力 14（40%）" in page.locator("#puppet-list .puppet-row").text_content()
                assert "逐年结算" in page.locator("#puppet-time-note").text_content()
                assert page.locator("#foreign-soul-list > .soul-row").count() == 1
                assert page.locator("#foreign-soul-list details.soul-archive").count() == 1
                assert not page.locator("#foreign-soul-list details.soul-archive").evaluate("node => node.open")
                assert "已炼化元神 2 道" in page.locator("#foreign-soul-list details.soul-archive summary").text_content()
                assert page.locator("#secluded-refine-souls").is_hidden()
                page.locator("#captive-toggle").click()

                page.locator("[data-panel-target='spirit-field']").click()
                page.locator("#spirit-field-card").wait_for(state="visible")
                assert page.locator("#spirit-field-plots .spirit-crop-tile").count() == 8
                assert "荒地" in page.locator("#spirit-field-plots").text_content()
                page.locator("#spirit-field-toggle").click()

                auction_game = engine.store.load(created["id"])
                auction_location = engine.maps.normalize_location(auction_game.player.world, auction_game.player.location_id)
                auction_game.auction_sequence += 1
                auction_game.auction_state = {
                    "id":f"auction-{auction_game.auction_sequence}", "status":"open",
                    "world":auction_game.player.world, "location_id":auction_location,
                    "location_name":engine.maps.location(auction_game.player.world, auction_location)["name"],
                    "announced_age":auction_game.player.age, "actions_until_open":0, "round":0,
                    "lots":[], "consignments":[], "attendees":[], "black_market_results":[],
                }
                engine._open_auction(auction_game, random.Random(19))
                add_item(auction_game.player, "spirit_stone", 100000)
                auction_age = auction_game.player.age
                engine.store.save(auction_game)
                page.reload()
                page.get_by_text("续接 · 前端烟测").click()
                page.locator("[data-panel-target='auction']").click()
                page.locator("#auction-card").wait_for(state="visible")
                page.locator("#auction-lots .auction-lot").first.wait_for()
                assert page.locator("#auction-lots .auction-lot").count() == 5
                assert "所有会内操作均不消耗时间" in page.locator("#auction-description").text_content()
                page.get_by_text("朱雀公主", exact=True).click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                page.locator("#auction-attendees .auction-attendee button:not([disabled])").first.click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                assert page.locator("#auction-attendees details.private-trade-card").count() == 1
                page.locator("#auction-lots .auction-bid:not([disabled])").first.click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                assert "朱雀公主" in page.locator("#auction-bid-logs").text_content()
                assert engine.store.load(created["id"]).player.age == auction_age
                for _ in range(3):
                    page.locator("#auction-advance-round").click()
                    page.wait_for_function("!document.body.classList.contains('busy')")
                page.locator("#black-market-section").wait_for(state="visible")
                page.locator("#black-market-pattern").fill("丹|剑")
                page.locator("#black-market-search-form button").click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                assert page.locator("#black-market-results .auction-lot").count() >= 1
                assert engine.store.load(created["id"]).player.age == auction_age
                page.locator("#black-market-leave").click()
                page.wait_for_function("!document.body.classList.contains('busy')")

                page.locator("[data-panel-target='map']").click()
                page.locator("#map-card").wait_for(state="visible")
                assert page.locator("#map-locations .map-location").count() == 5
                grassland = page.locator("#map-locations .map-location", has_text="岚疆草原")
                assert "气经验：" in grassland.text_content()
                grassland.locator(".map-travel").click()
                page.get_by_text("当前：岚疆草原", exact=True).wait_for()
                assert "岚疆草原" in page.locator("#player-subtitle").text_content()
                page.locator("#map-toggle").click()

                page.locator("[data-panel-target='inventory']").click()
                page.locator("#inventory-card").wait_for(state="visible")
                assert page.locator("#inventory-list .inventory-category").count() >= 1
                page.locator("#inventory-toggle").click()

                page.locator("[data-panel-target='market']").click()
                assert "panel-open" in page.locator("#market-card").get_attribute("class")
                page.locator("#market-toggle").click()
                assert "panel-open" not in page.locator("#market-card").get_attribute("class")
                page.locator("[data-panel-target='market']").click()

                page.locator("[data-panel-target='faction']").click()
                assert "panel-open" in page.locator("#faction-card").get_attribute("class")
                page.locator("#faction-toggle").click()
                assert "panel-open" not in page.locator("#faction-card").get_attribute("class")
                page.locator("[data-panel-target='market']").click()

                first = page.locator(".market-buy:not([disabled])").first
                first.click()
                page.wait_for_timeout(150)
                assert page.locator(".market-buy:not([disabled])").count() >= 1
                assert page.locator("#market-toggle").is_enabled()
                assert page.locator("#faction-toggle").is_enabled()

                page.locator("#market-toggle").click()
                page.locator(".action-folds details").first.locator("summary").click()
                page.locator("[data-action='treasure']").click()
                page.get_by_role("heading", name="遗藏择宝").wait_for()
                assert page.locator("#event-choices button").count() == 3
                labels = page.locator("#event-choices button").all_text_contents()
                assert any("法器" in label for label in labels)
                assert any("功法" in label for label in labels)
                assert any("丹药" in label for label in labels)
                page.locator("#event-choices button:not([disabled])").first.click()
                page.locator("#event-card").wait_for(state="hidden")

                social_game = engine.store.load(created["id"])
                social_game.player.dao_companion = engine._generated_relationship(
                    social_game.player, "companion", random.Random(14)
                )
                social_game.player.dao_companion["main_technique_id"] = social_game.player.known_techniques[0].id
                social_game.player.faction_id = "tianjian"
                engine.store.save(social_game)
                page.reload()
                page.get_by_text("续接 · 前端烟测").click()
                page.locator("[data-panel-target='relationship']").click()
                page.locator("#dao-companion-list .companion-row").wait_for()
                assert page.locator("#dao-companion-list .companion-row").count() == 1
                assert page.get_by_role("button", name="亲密交谈").is_enabled()
                assert page.get_by_role("button", name="脱离师门").is_enabled()
                assert page.get_by_role("button", name="解除道侣").is_enabled()
                assert page.get_by_role("button", name="引荐入宗").count() >= 2
                page.get_by_role("button", name="邀请同行").click()
                page.locator("#party-list .party-row").wait_for()
                party_buttons = page.locator("#party-list .party-row .party-action")
                assert party_buttons.count() >= 2
                boxes = [party_buttons.nth(index).bounding_box() for index in range(party_buttons.count())]
                for index, first_box in enumerate(boxes):
                    for second_box in boxes[index + 1:]:
                        assert not (
                            first_box["x"] < second_box["x"] + second_box["width"]
                            and first_box["x"] + first_box["width"] > second_box["x"]
                            and first_box["y"] < second_box["y"] + second_box["height"]
                            and first_box["y"] + first_box["height"] > second_box["y"]
                        )
                page.get_by_role("button", name="亲密交谈").click()
                assert page.get_by_role("button", name="亲密交谈").is_disabled()
                page.wait_for_function("!document.body.classList.contains('busy')")

                crossing_game = engine.store.load(created["id"])
                crossing_game.player.realm_index = 5
                crossing_game.player.layer = 1
                crossing_game.player.faction_combat_bonus = 500000
                crossing_game.player.faction_id = "tianjian"
                crossing_game.pending_event = None
                add_item(crossing_game.player, "spirit_node_info")
                add_item(crossing_game.player, "broken_god", 5)
                crossing_game.player.hp = max_hp(crossing_game.player)
                crossing_game.player.mp = max_mp(crossing_game.player)
                engine.store.save(crossing_game)
                page.reload()
                page.get_by_text("续接 · 前端烟测").click()
                page.locator("#spirit-crossing-action").wait_for(state="visible")
                assert page.locator("#spirit-crossing-action").is_enabled()
                assert page.get_by_text("极品金灵根", exact=False).count() >= 1
                page.locator("#spirit-crossing-action").click()
                for title in ("节点启封", "界壁炼身", "破界天光"):
                    page.get_by_role("heading", name=title).wait_for()
                    page.locator("#event-choices button:not([disabled])").click()
                page.locator("[data-panel-target='faction']").click()
                page.get_by_role("heading", name="灵界宗门").wait_for()
                assert page.locator("#faction-title").text_content() == "灵界宗门"
                faction_summary = page.locator("#faction-summary")
                assert faction_summary.get_by_text("太玄门", exact=True).count() == 1
                assert faction_summary.get_by_text("万灵山", exact=True).count() == 1
                assert faction_summary.get_by_text("星河书院", exact=True).count() == 1
                assert page.locator("#spirit-crossing-action").is_hidden()
                assert page.locator("[data-panel-target='race']").is_visible()
                page.locator("[data-panel-target='race']").click()
                page.locator("#race-card").wait_for(state="visible")
                assert page.locator("#race-list .race-chip").count() == 20
                assert page.get_by_text("人妖两族盟约", exact=True).count() == 1
                page.locator("#race-list .race-chip").nth(2).click()
                assert page.locator("#race-detail .race-relation").count() == 19
                assert page.locator("#race-detail .race-factions p").count() >= 1
                assert page.locator("#race-detail .race-events h3").text_content() == "族群大事"
                page.locator("[data-panel-target='world-route']").click()
                page.locator("#world-route-card").wait_for(state="visible")
                assert page.locator("#world-route-stages .world-route-stage").count() == 4
                assert page.locator("#world-route-stages .world-route-stage.system").count() == 1
                page.locator("[data-panel-target='ranking']").click()
                page.locator("#ranking-card").wait_for(state="visible")
                assert page.locator("#ranking-list .ranking-row").count() == 20
                assert "排名" in page.locator("#ranking-player-status").text_content()
                page.locator("#ranking-toggle").click()
                browser.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    main()
