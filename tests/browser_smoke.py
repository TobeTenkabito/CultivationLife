"""手动运行的前端烟雾测试；使用临时存档，不接触玩家数据。"""

import copy
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
from cultivation_life.system.ghost_system import grant_intrinsic_progression_if_new_highwater
from cultivation_life.system.formation_system import formation_material_definitions, make_formation_material_instance
from cultivation_life.rules import TECHNIQUE_CATALOG, add_item, add_technique_copy, assign_technique, learn_technique, max_hp, max_mp, opportunity_required


def main() -> None:
    with tempfile.TemporaryDirectory() as save_directory:
        engine = GameEngine(ROOT, Path(save_directory))
        created = engine.create_game("前端烟测", "supreme_metal", "dao", 99001)
        game = engine.store.load(created["id"])
        game.player.realm_index = 1
        add_item(game.player, "spirit_stone", 10_000)
        add_item(game.player, "guixu_canghai_consumable_01")
        learn_technique(game.player, TECHNIQUE_CATALOG["TECH_BASIC_QI"])
        add_technique_copy(game.player, TECHNIQUE_CATALOG["TECH_BASIC_QI"], 3, level=1)
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
        add_item(game.player, "true_dragon_blood_trace", 5)
        game.player.divine_sense_rank = 1
        game.player.divine_sense_experience = 20
        formation_defs = formation_material_definitions()
        game.player.formation_materials.extend([
            make_formation_material_instance(formation_defs[material_id], source="前端烟测", origin_world="human")
            for material_id in ("human_greenwood_stake", "human_red_sun_sand", "human_xuanyin_stone")
        ])
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
                achievement_count = len(engine.list_achievements()["achievements"])
                assert page.locator(".achievement-row").count() == achievement_count
                assert page.get_by_role("heading", name="本体成就").is_visible()
                assert page.locator(".achievement-row.locked").count() == achievement_count
                assert "解锁条件：取得沧海玄鼎" in page.locator(".achievement-row").first.text_content()
                page.locator("#achievement-close").click()
                page.locator("#new-game-form").wait_for(state="visible")
                assert page.locator(".quick-start-button").count() >= 16
                assert page.locator(".quick-start-button:not([disabled])").count() >= 16
                assert page.locator(".quick-start-button[disabled]").count() == 0
                assert page.locator(".quick-start-group").count() >= 4
                assert "妖修 DLC" in page.locator(".quick-start-button[data-preset-id='monster_core']").text_content()
                assert "妖修 DLC" in page.locator(".quick-start-button[data-preset-id='monster_void']").text_content()
                assert page.locator(".quick-start-button[data-preset-id='buddhist_void']").count() == 1
                page.locator(".quick-start-button[data-preset-id='confucian_core']").click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                inner_outer_dock = page.locator("[data-panel-target='sage-inner-outer']")
                assert inner_outer_dock.is_visible()
                assert "sage-dock-button" in (inner_outer_dock.get_attribute("class") or "")
                assert inner_outer_dock.evaluate("node => node.closest('.left-dock') !== null")
                inner_outer_dock.click()
                page.locator("#sage-inner-outer-card").wait_for(state="visible")
                assert "浩然" in page.locator("#sage-haoran-summary").text_content()
                assert page.locator("#sage-haoran-passives > *").count() >= 1
                assert page.locator("#sage-outer-list .sage-outer-card").count() == 4
                page.locator("#sage-inner-outer-toggle").click()
                sage_dock = page.locator("[data-panel-target='sage']")
                assert sage_dock.is_visible()
                assert "sage-dock-button" in (sage_dock.get_attribute("class") or "")
                sage_dock.click()
                page.locator("#sage-card").wait_for(state="visible")
                assert page.locator("#sage-founding .sage-combo-grid label").count() == 4
                assert page.locator("#sage-founding-preview .sage-effect-chips span").count() == 4
                assert page.locator("#sage-worship-list .sage-worship-card").count() == 8
                assert "战斗力" in page.locator("#sage-classic-detail").text_content()
                assert page.locator("#sage-worship-list .sage-worship-card").first.evaluate(
                    "node => getComputedStyle(node).backgroundColor !== 'rgb(255, 255, 255)'"
                )
                assert page.locator("#sage-doctrine-list .sage-member-row").count() >= 7
                page.locator("#sage-doctrine-list .sage-doctrine").first.locator(":scope > button").click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                assert page.locator("#sage-doctrine-list .sage-member-row.player").count() == 1
                weak_debate = page.locator("#sage-doctrine-list .sage-member-row", has_text="许问经").locator(".sage-debate-button")
                assert weak_debate.is_enabled()
                weak_debate.click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                assert page.locator("#sage-doctrine-list .sage-member-row", has_text="许问经").locator(".sage-debate-button").is_disabled()
                page.locator("#sage-toggle").click()
                page.locator("#new-game-button").click()
                page.locator("#path-select").select_option("monster")
                assert page.locator("#monster-species-field").is_visible()
                assert page.locator("#monster-species-select option").count() == 8
                page.locator("#monster-species-select").select_option("avian")
                page.locator("#gender-select").select_option("female")
                page.locator("#new-game-form input[name='name']").fill("羽族烟测")
                page.locator("#new-game-form button[type='submit']").click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                assert page.locator("[data-panel-target='bloodline']").is_visible()
                assert page.locator("[data-panel-target='bloodline']").evaluate("node => node.classList.contains('dlc-active')")
                page.locator("[data-panel-target='bloodline']").click()
                page.locator("#bloodline-card").wait_for(state="visible")
                page.locator("#bloodline-current").get_by_text("山雀妖", exact=True).wait_for()
                assert "羽属" in page.locator("#bloodline-summary").text_content()
                assert page.locator("#bloodline-profile").count() == 0
                assert page.locator(".bloodline-profile > span").count() == 6
                monster_game_id = page.evaluate("game.id")
                assert engine.store.load(monster_game_id).player.gender == "female"
                page.evaluate("""renderMonsterBloodline({
                    visible:true, available:false,
                    reason:'血脉冻结测试', general_trait_pool_size:16,
                    general_traits:[{id:'monster_common_stout_hide',name:'坚韧皮膜',description:'防护提高 3%。'}]
                })""")
                assert not page.locator("[data-panel-target='bloodline']").evaluate("node => node.classList.contains('dlc-active')")
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
                assert page.locator("#natal-artifact-card .natal-refine-all").is_enabled()
                page.locator("#natal-artifact-card .natal-refine-all").click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                assert page.evaluate("game.natal_artifact.level") > 1
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

                page.locator("[data-panel-target='inventory']").click()
                guixu_consumable = page.locator("#inventory-list .item", has_text="海眼定神丹")
                assert guixu_consumable.locator(".item-use").is_enabled()
                guixu_consumable.locator(".item-use").click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                assert page.locator("#inventory-list .item", has_text="海眼定神丹").count() == 0
                manual_row = page.locator("#inventory-list .item", has_text="Lv.1 传承玉简").filter(has=page.locator(".technique-merge")).first
                assert manual_row.locator(".technique-upgrade").is_enabled()
                assert manual_row.locator(".technique-merge").is_enabled()
                manual_row.locator(".technique-upgrade").click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                manual_row = page.locator("#inventory-list .item", has_text="Lv.1 传承玉简").filter(has=page.locator(".technique-merge")).first
                assert manual_row.locator(".technique-merge").is_enabled()
                manual_row.locator(".technique-merge").click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                page.locator("#inventory-toggle").click()
                page.locator("details.technique-library > summary").click()
                known_basic = page.locator("#known-technique-list .known-technique", has_text=TECHNIQUE_CATALOG["TECH_BASIC_QI"].name)
                assert "Lv.2" in known_basic.text_content()
                assert known_basic.locator(".technique-upgrade").is_enabled()
                known_basic.locator(".technique-upgrade").click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                assert "Lv.3" in page.locator("#known-technique-list .known-technique", has_text=TECHNIQUE_CATALOG["TECH_BASIC_QI"].name).text_content()

                page.locator("[data-panel-target='formation']").click()
                page.locator("#formation-card").wait_for(state="visible")
                assert page.locator("#formation-grid .formation-slot").count() == 9
                assert page.locator("#formation-material-library .formation-material-row").count() == 3
                material_ids = [row["id"] for row in page.evaluate("game.formation_system.materials")]
                for index, material_id in enumerate(material_ids):
                    page.locator("#formation-grid select").nth(index).select_option(material_id)
                page.locator("#formation-name").fill("前端九宫阵")
                page.locator("#formation-preview").click()
                page.wait_for_function("document.querySelectorAll('#formation-flow-lines path').length > 0")
                assert page.locator("#formation-metrics .formation-metric").count() == 6
                page.locator("#formation-save-activate").click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                assert "当前启用" in page.locator("#formation-loadout-list").text_content()
                assert all(row.get("occupied") for row in page.evaluate("game.formation_system.materials"))
                page.locator("#formation-ground-personal").click()
                page.locator("#game-confirm-dialog").wait_for(state="visible")
                assert "镇下此地私阵" == page.locator("#game-confirm-title").text_content()
                with page.expect_response(lambda response: response.url.endswith("/formation-ground-deploy")):
                    page.locator("#game-confirm-accept").click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                assert page.locator("#formation-ground-list .formation-ground-row").count() == 1
                assert "永久完整度 100.0%" in page.locator("#formation-ground-list").text_content()
                assert "镇地占用" in page.locator("#formation-material-library").text_content()
                assert "前端九宫阵" in page.locator("#map-locations .formation-map-marker").text_content()
                page.locator("#formation-ground-list").get_by_role("button", name="撤阵归库").click()
                page.locator("#game-confirm-dialog").wait_for(state="visible")
                with page.expect_response(lambda response: response.url.endswith("/formation-ground-withdraw")):
                    page.locator("#game-confirm-accept").click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                assert page.locator("#formation-ground-list .formation-ground-row").count() == 0
                assert all(not row.get("occupied") for row in page.evaluate("game.formation_system.materials"))
                page.locator("#formation-toggle").click()

                page.locator("[data-panel-target='transformation']").click()
                page.locator("#transformation-card").wait_for(state="visible")
                assert "2/2" in page.locator("#transformation-summary").text_content()
                assert page.locator("#transformation-stored .transformation-form").count() == 2
                assert page.locator("#transformation-stored .transformation-form.active").count() == 2
                assert page.locator("#transformation-stored .transformation-progress").count() == 2
                assert page.locator("#transformation-stored .transformation-stat-bars").count() == 2
                assert page.locator("#transformation-stored .transformation-stat-bar").count() == 12
                stat_colors = page.locator("#transformation-stored .transformation-stat-bar").evaluate_all(
                    "nodes => nodes.slice(0, 6).map(node => getComputedStyle(node.querySelector('.transformation-stat-track i')).backgroundImage)"
                )
                assert len(set(stat_colors)) == 6
                assert page.locator("#transformation-materials .transformation-material").count() == 1
                assert page.locator("#transformation-materials select").count() == 1
                assert "直接培养" in page.locator("#transformation-materials").text_content()
                assert "额外 30%" in page.locator("#transformation-materials").text_content()
                assert page.get_by_role("button", name="一键炼化").is_enabled()
                assert page.get_by_role("button", name="一键合炼").is_enabled()
                assert "67%" in page.locator("#transformation-note").text_content()
                with page.expect_response(lambda response: response.url.endswith("/transformation-batch")):
                    page.get_by_role("button", name="一键合炼").click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                assert page.locator("#transformation-materials .transformation-material").count() == 0
                page.locator("#transformation-toggle").click()

                page.locator("[data-panel-target='settings']").click()
                page.locator("#settings-card").wait_for(state="visible")
                assert not page.locator("#setting-combat-popup").is_checked()
                assert not page.locator("#setting-auto-war").is_checked()
                assert page.locator("#setting-guixu-popup-row").is_visible()
                assert not page.locator("#setting-guixu-popup").is_checked()
                with page.expect_response(lambda response: response.url.endswith("/settings")):
                    page.locator("#setting-combat-popup").check()
                with page.expect_response(lambda response: response.url.endswith("/settings")):
                    page.locator("#setting-guixu-popup").check()
                with page.expect_response(lambda response: response.url.endswith("/settings")):
                    page.locator("#setting-auto-war").check()
                assert engine.store.load(created["id"]).settings == {
                    "combat_popup": False, "achievement_popup": True,
                    "auto_advance_player_wars": True,
                    "guixu_event_popup": False,
                }
                page.locator("#settings-toggle").click()

                page.locator("[data-panel-target='extension']").click()
                page.locator("#extension-card").wait_for(state="visible")
                assert "已识别 6" in page.locator("#extension-summary").text_content()
                extension_text = page.locator("#extension-list").text_content()
                assert "万妖归宗：血脉进化" in extension_text
                assert "百鬼夜行：往生轮回" in extension_text
                assert "明争暗斗：合纵连横" in extension_text
                assert "神机百变：巧夺天工" in extension_text
                page.locator("#extension-toggle").click()

                page.locator("[data-panel-target='tianji']").click()
                assert page.locator("[data-panel-target='tianji']").evaluate("node => node.parentElement.id") == "strategy-dock"
                page.locator("#tianji-card").wait_for(state="visible")
                assert not page.locator("#tianji-card").evaluate("node => node.classList.contains('left-panel')")
                assert page.locator("#tianji-ranking .tianji-rank-row").count() == 100
                assert "已识 0 / 100" in page.locator("#tianji-heading").text_content()
                assert page.locator("#tianji-debug-lv5").is_visible() == bool(
                    server_module.load_runtime_config(server_module.APP_ROOT)["debug"]
                )
                page.locator("#tianji-toggle").click()

                page.locator("[data-panel-target='intrigue']").click()
                page.locator("#intrigue-card").wait_for(state="visible")
                assert "职位、控制权与决策权彼此独立" in page.locator("#intrigue-card").text_content()
                page.locator("#intrigue-toggle").click()

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
                assert page.locator("#map-locations .map-location").count() == 10
                lethal_button = page.locator(".map-travel[data-destination='border_void_watch']")
                assert lethal_button.is_enabled()
                assert lethal_button.text_content() == "强行前往（必死）"
                lethal_button.click()
                page.locator("#game-confirm-dialog").wait_for(state="visible")
                assert page.locator("#game-confirm-title").text_content() == "强行前往凶地"
                assert "必定死亡" in page.locator("#game-confirm-body").text_content()
                page.locator("#game-confirm-cancel").click()
                grassland = page.locator(".map-travel[data-destination='lanjiang_steppe']").locator("xpath=..")
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
                assert page.locator("#market-offers .market-offer").count() == 6
                assert page.locator("#material-market-offers .market-offer").count() == 6
                assert page.locator("#market-offers .market-lock").count() == 6
                assert page.locator("#material-market-offers .market-lock").count() == 6
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
                page.wait_for_function("!document.body.classList.contains('busy')")
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

                ghost_created = engine.create_game(
                    "鬼修烟测", "mutated_yin", "ghost", 99002, start_world="hell",
                )
                ghost_game = engine.store.load(ghost_created["id"])
                ghost_game.player.realm_index = 3
                ghost_game.player.layer = REALMS[3].layers
                grant_intrinsic_progression_if_new_highwater(ghost_game.player)
                ghost_game.player.opportunity = opportunity_required(ghost_game.player)
                ghost_game.player.ghost_soul_erosion_rate_pp = 0.08
                ghost_game.player.ghost_soul_erosion_time_progress = 0.3
                ghost_game.player.ghost_wangsheng_energy = 5
                ghost_game.ghost_parade.update({
                    "status":"active", "announced":True,
                    "world":ghost_game.player.world,
                    "location_id":ghost_game.player.location_id,
                    "start_age":ghost_game.player.age,
                    "end_age":ghost_game.player.age + 5,
                    "participated":False,
                })
                ghost_game.ghost_parade["souls"] = engine._generate_parade_souls(
                    ghost_game, random.Random(99002),
                )
                parade_trait_description = ghost_game.ghost_parade["souls"][0]["soul_trait"]["description"]
                bound_soul = copy.deepcopy(ghost_game.ghost_parade["souls"].pop())
                bound_soul.update(defeated=True, is_bound_soul=True)
                ghost_game.player.ghost_bound_souls.append(bound_soul)
                add_item(ghost_game.player, "ghost_core_pill")
                add_item(ghost_game.player, "ghost_nurturing_casket")
                engine.store.save(ghost_game)
                page.reload()
                page.get_by_text("续接 · 鬼修烟测").click()
                page.wait_for_function("!document.querySelector('#ghost-system-panel').classList.contains('hidden')")
                page.wait_for_function("!document.body.classList.contains('busy')")
                assert page.locator("#ghost-system-panel").is_visible()
                assert page.locator("#ghost-erosion").text_content() == "0.0800%"
                assert page.locator("#ghost-wangsheng").text_content() == "5"
                page.locator(".ghost-ledger summary").click()
                assert "最终有效突破率封顶 98%" in page.locator("#ghost-system-summary").text_content()
                assert "本次轮回预览" in page.locator("#ghost-reincarnation-preview").text_content()
                assert "100.00%" in page.locator("#ghost-integrity-detail").text_content()
                assert "所有行动共享此进度" in page.locator("#ghost-integrity-detail").text_content()
                assert "练气13层 ×0" in page.locator("#ghost-imprint-list").text_content()
                assert page.locator("#ghost-phase-two").count() == 0
                assert page.locator("[data-panel-target='ghost-soul']").is_visible()
                assert page.locator("[data-panel-target='ghost-attachment']").is_visible()
                assert page.locator("[data-panel-target='ghost-parade']").is_visible()
                page.locator("[data-panel-target='ghost-soul']").click()
                page.locator("#ghost-soul-card").wait_for(state="visible")
                assert page.locator("#ghost-soul-slots .captive-row").count() == 10
                assert page.locator("#ghost-bound-souls .captive-row").count() == 1
                page.locator("#ghost-bound-souls").get_by_role("button", name="放归").click()
                page.locator("#game-confirm-dialog").wait_for(state="visible")
                assert page.locator("#game-confirm-title").text_content() == "放归拘魂"
                assert bound_soul["name"] in page.locator("#game-confirm-body").text_content()
                page.locator("#game-confirm-cancel").click()
                page.locator("#game-confirm-dialog").wait_for(state="hidden")
                assert page.locator("#ghost-bound-souls .captive-row").count() == 1
                page.locator("#ghost-bound-souls").get_by_role("button", name="放归").click()
                with page.expect_response(lambda response: response.url.endswith("/ghost-soul")):
                    page.locator("#game-confirm-accept").click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                assert page.locator("#ghost-bound-souls .captive-row").count() == 0
                page.locator("#ghost-soul-toggle").click()
                page.locator("[data-panel-target='ghost-attachment']").click()
                page.locator("#ghost-attachment-card").wait_for(state="visible")
                assert "载体与器灵状态" in page.locator("#ghost-attachment-card").text_content()
                attach_button = page.locator("#ghost-attachment-list").get_by_role("button", name="附入 养魂木匣")
                assert attach_button.is_enabled()
                with page.expect_response(lambda response: response.url.endswith("/ghost-attachment")):
                    attach_button.click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                assert page.locator("#ghost-attachment-summary").text_content() == "当前已附灵"
                assert "养魂木匣器灵" in page.locator("#ghost-attachment-list").text_content()
                with page.expect_response(lambda response: response.url.endswith("/ghost-attachment")):
                    page.locator("#ghost-attachment-list").get_by_role("button", name="离器").click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                assert page.locator("#ghost-attachment-summary").text_content() == "自由魂体"
                page.locator("#ghost-attachment-toggle").click()
                page.locator("[data-panel-target='ghost-parade']").click()
                page.locator("#ghost-parade-card").wait_for(state="visible")
                assert "正在夜行" in page.locator("#ghost-parade-card").text_content()
                assert page.locator("#ghost-parade-list .captive-row").count() >= 3
                assert parade_trait_description in page.locator("#ghost-parade-card").text_content()
                page.locator("#ghost-parade-toggle").click()
                page.locator("[data-panel-target='inventory']").click()
                page.locator("#inventory-card").wait_for(state="visible")
                assert page.get_by_role("button", name="鬼修不可用").count() >= 1
                assert page.get_by_role("button", name="鬼修不可用").first.is_disabled()
                page.locator("#inventory-toggle").click()
                with page.expect_response(lambda response: response.url.endswith("/ghost-wangsheng")):
                    page.locator("#ghost-wangsheng-all-action").click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                assert page.locator("#ghost-erosion").text_content() == "0.0400%"
                assert page.locator("#ghost-wangsheng").text_content() == "1"
                with page.expect_response(lambda response: response.url.endswith("/ghost-reincarnation-prompt")):
                    page.locator("#ghost-reincarnate-action").click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                page.locator("#event-card").wait_for(state="visible")
                assert page.locator("#event-title").text_content() == "轮回门前"
                assert "最终有效概率仍封顶 98%" in page.locator("#event-body").text_content()
                with page.expect_response(lambda response: response.url.endswith("/choice")):
                    page.get_by_role("button", name="取消，暂留此世").click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                cancelled_reincarnation = engine.store.load(ghost_created["id"])
                assert (cancelled_reincarnation.player.realm_index, cancelled_reincarnation.player.layer) == (3, REALMS[3].layers)
                with page.expect_response(lambda response: response.url.endswith("/ghost-reincarnation-prompt")):
                    page.locator("#ghost-reincarnate-action").click()
                page.locator("#event-card").wait_for(state="visible")
                with page.expect_response(lambda response: response.url.endswith("/choice")):
                    page.get_by_role("button", name="继续轮回", exact=True).click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                assert "练气1层" in page.locator("#realm-name").text_content()
                assert page.locator("#ghost-reincarnate-action").is_hidden()

                fallen = engine.store.load(ghost_created["id"])
                fallen.player.prisoners = [{
                    "id":"afterlife-host", "name":"还魂烟测", "race":"human", "path":"dao",
                    "spirit_root":"supreme_water", "realm_index":1, "layer":1,
                    "age":37, "lifespan":118, "combat_power":180,
                }]
                engine._die(
                    fallen, "烟测非剧情战陨落", "SYS_COMBAT", offer_captive_possession=True,
                )
                pre_possession_world_age = fallen.player.age
                engine.store.save(fallen)
                page.reload()
                page.get_by_text("续接 · 鬼修烟测").click()
                page.locator("#ending-card").wait_for(state="visible")
                assert page.locator("#post-battle-possession").is_visible()
                assert page.get_by_role("button", name="夺舍 还魂烟测 · 练气1层 · 37岁").is_visible()
                with page.expect_response(lambda response: response.url.endswith("/post-battle-possession")):
                    page.get_by_role("button", name="夺舍 还魂烟测 · 练气1层 · 37岁").click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                assert page.locator("#ending-card").is_hidden()
                age_line = page.locator("#age-line").text_content()
                assert "37 岁 · 寿元 118" in age_line
                assert f"世界纪年 {pre_possession_world_age}" in age_line
                possessed = engine.store.load(ghost_created["id"])
                assert possessed.player.age == pre_possession_world_age
                assert possessed.player.ghost_host_body["age"] == 37
                browser.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    main()
