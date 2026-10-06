"""Exercise the ordinary UI at desktop and phone widths using disposable saves."""

import random
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.engine.actions.exploration import enter_scene
from cultivation_life.rules import add_item, max_mp
from cultivation_life.runtime import encode_rng
from cultivation_life.system import spatial, asura_court
from cultivation_life.system.upper_institutions import account


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        engine = GameEngine(ROOT, root / "data/saves")
        gid = engine.create_game(
            "裂缝验收", "supreme_metal", "dao", 1556, preset_id="core"
        )["id"]
        g = engine._load(gid)
        g.pending_event = None
        g.player.realm_index = 4
        add_item(g.player, "spirit_stone", 10000)
        add_item(g.player, "talisman_human_1_paper", 10)
        add_item(g.player, "talisman_human_1_ink", 10)
        g.player.mp = max_mp(g.player)
        spatial.new_rift(g, random.Random(1), engine.maps, controlled=True)["kind"] = "rift"
        g.rng_state = encode_rng(random.Random(1))
        engine.store.save(g)
        king_id = engine.create_game(
            "王庭验收", "supreme_metal", "demonic", 1557, preset_id="asura_upper"
        )["id"]
        engine.upper_institution_action(king_id, "join")
        king = engine._load(king_id)
        asura_court.change_rank(king, account(king), 5)
        account(king)["treasury"] = 10000000
        engine.store.save(king)
        (root / "game_config.txt").write_text("Debug=False")

        class Quiet(server.Handler):
            def log_message(self, *_args):
                pass

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        with (
            patch.object(server, "ENGINE", engine),
            patch.object(server, "APP_ROOT", root),
            patch.object(server, "PERSISTENCE_ROOT", root),
        ):
            thread.start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    page = browser.new_page(viewport={"width": 1440, "height": 1000})
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.goto(f"http://127.0.0.1:{httpd.server_port}")
                    page.wait_for_function("!!configData")
                    page.evaluate("id => loadGame(id)", gid)
                    page.locator("[data-panel-target=talisman]").first.click()
                    panel = page.locator("#talisman-content")
                    panel.get_by_label("符箓阶数", exact=True).select_option("1")
                    panel.get_by_role("button", name="学习 一阶灵破军符", exact=False).click()
                    page.wait_for_function("!busy && game.talismans.methods[0].learned")
                    panel.get_by_role("button", name="炼制符箓", exact=True).click()
                    page.wait_for_function("!busy && game.talismans.rows.length===1")
                    panel.get_by_role("button", name="启用", exact=True).click()
                    page.wait_for_function("!busy && game.talismans.rows[0].enabled")
                    page.locator('[data-panel-target=market]').click()
                    page.locator('#talisman-market-offers .market-buy:not([disabled])').first.click()
                    page.wait_for_function('!busy && game.market.talisman_material_offers.some(r=>r.sold)')
                    page.locator('#market-talisman-sellables button').click()
                    page.wait_for_function('!busy && game.talismans.rows.length===0')
                    page.evaluate("UtilityPanels.open('map')")
                    with patch.dict(
                        spatial.cfg()["outcome_weights"],
                        {"secluded": 1, "passage": 0, "local": 0},
                        clear=True,
                    ):
                        page.locator("#map-locations .map-location .spatial-rift").get_by_role(
                            "button", name="进入空间裂缝", exact=True
                        ).click()
                        page.wait_for_function("!busy && game.spatial.inside")
                    page.evaluate("render(game)")
                    assert "探索" in page.locator("#spatial-panel").inner_text(), (
                        page.locator("body").inner_text()[-2500:]
                    )
                    page.locator("#spatial-panel").get_by_role(
                        "button", name="探索 · 一年", exact=True
                    ).click()
                    page.wait_for_function("!busy && game.spatial.scene.explored===1")
                    assert page.locator("#map-locations").is_visible()
                    assert page.locator("#map-locations .map-location").count() == 4
                    for width, height in [(1440, 1000), (412, 915), (915, 412)]:
                        page.set_viewport_size({"width": width, "height": height})
                        for theme in "abdf":
                            page.evaluate(
                                't=>document.querySelector(`[data-theme-choice="${t}"]`).click()',
                                theme,
                            )
                            page.wait_for_timeout(350)
                            assert page.locator("#spatial-panel").is_visible()
                            assert page.evaluate(
                                "document.documentElement.scrollWidth <= innerWidth + 2"
                            ), (
                                width,
                                theme,
                                page.evaluate(
                                    "Array.from(document.querySelectorAll('body *')).filter(e=>e.getBoundingClientRect().right>innerWidth+2 && e.getBoundingClientRect().width>0).slice(-12).map(e=>[e.tagName,e.id,e.className,e.getBoundingClientRect().right])"
                                ),
                            )
                    page.locator("#spatial-panel").scroll_into_view_if_needed()
                    page.screenshot(path=str(ROOT / "build/spatial-secluded.png"))
                    scene_game = engine.store.load(gid)
                    rng = random.Random(5)
                    enter_scene(
                        engine._exploration_dependencies(),
                        scene_game,
                        spatial.create_instance(scene_game, rng, "lost"),
                        rng,
                    )
                    engine.store.save(scene_game)
                    page.evaluate("id => loadGame(id)", gid)
                    assert page.locator("#spatial-panel button").count() >= 10
                    page.set_viewport_size({"width": 1440, "height": 1000})
                    page.locator('[data-panel-target=relationship]').click()
                    page.locator('#npc-contacts .contact-directory button').first.click()
                    page.locator('[data-contact-action=improve]').click()
                    page.wait_for_function('!busy && game.world_npcs.some(n=>n.affinity>0)')
                    assert page.locator('#npc-contacts').is_visible()
                    market_game = engine.store.load(gid)
                    market_game.player.world = 'human'
                    market_game.spatial_state['current'] = None
                    market_game.player.location_id = engine.maps.default_location('human')
                    market_game.auction_state = dict(status='black_market', world='human',
                        location_id=market_game.player.location_id, lots=[], attendees=[])
                    engine.store.save(market_game)
                    page.evaluate('id=>loadGame(id)', gid)
                    page.evaluate("UtilityPanels.open('auction')")
                    page.locator('#black-market-pattern').fill('符')
                    page.locator('#black-market-search-form button').click()
                    page.wait_for_function("!busy && game.auction_system.black_market_results.some(r=>r.kind==='talisman')")
                    page.locator('#black-market-results > *').filter(has_text='成品符箓').first.get_by_role('button').click()
                    page.wait_for_function('!busy && game.talismans.rows.length===1')
                    page.evaluate("id => loadGame(id)", king_id)
                    page.evaluate("UtilityPanels.open('upper-institution')")
                    court = page.locator("#upper-institution-content")
                    court.get_by_role("button", name="政令", exact=True).click()
                    assert all(
                        court.get_by_role("heading", name=label, exact=True).count()
                        for label in ["政治", "外交", "军事"]
                    )
                    court.get_by_role(
                        "button", name="削权（军事）", exact=True
                    ).first.click()
                    page.wait_for_function(
                        "!busy && game.upper_institution.court.factions.target_at >= 0"
                    )
                    court.get_by_role("button", name="内政", exact=True).click()
                    court.get_by_label("索取资材", exact=True).select_option(
                        "spirit_stone"
                    )
                    court.get_by_role("button", name="索取资材", exact=True).click()
                    page.wait_for_function(
                        "!busy && game.upper_institution.court.factions.tribute_at['material:spirit_stone'] >= 0"
                    )
                    page.set_viewport_size({"width": 1440, "height": 1000})
                    page.screenshot(path=str(ROOT / "build/spatial-royal.png"))
                    phone = browser.new_page(viewport={"width": 412, "height": 915})
                    phone.add_init_script(
                        "window.AndroidGame={requestDebugMode:()=>{}}"
                    )
                    phone.goto(f"http://127.0.0.1:{httpd.server_port}")
                    phone.wait_for_function("!!configData")
                    phone.evaluate("id=>loadGame(id)", king_id)
                    phone.evaluate("UtilityPanels.open('settings')")
                    phone.locator("#debug-native-mode").click()
                    phone.wait_for_function("!busy")
                    assert phone.locator("#debug-console-input").is_visible()
                    assert phone.evaluate("configData.debug") is False
                    phone.screenshot(path=str(ROOT / "build/spatial-phone-console.png"))
                    phone.close()
                    assert not errors, errors
                    browser.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=5)
    print("Spatial/talisman/royal UI passed in four themes at three viewport sizes.")


if __name__ == "__main__":
    main()
