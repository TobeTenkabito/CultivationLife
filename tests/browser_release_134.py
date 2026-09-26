"""Release UI integration checks using an isolated save directory."""
import random
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright
from cultivation_life import server as server_module
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item
from cultivation_life.system.crafting_system import make_crafting_material_instance


def main():
    with tempfile.TemporaryDirectory() as directory:
        engine = GameEngine(ROOT, Path(directory))
        game_id = engine.create_game("交换会验收", "heavenly", "dao", 1341, preset_id="core")["id"]
        game = engine.store.load(game_id)
        engine._schedule_exchange(game, random.Random(1))
        game.player.location_id = game.exchange_state["location_id"]
        engine.store.save(game)
        server_module.ENGINE = engine
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server_module.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        errors = []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 1050})
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{httpd.server_port}")
                page.evaluate("async id => { await loadGame(id); render(game); }", game_id)
                page.locator('[data-panel-target="exchange"]').click()
                assert "2 个时间单位" in page.locator("#exchange-description").text_content(), (page.locator("#exchange-description").text_content(), errors, page.evaluate("game.exchange_system"))
                page.locator("#exchange-toggle").click()
                engine._open_exchange(game, random.Random(3))
                offer = game.exchange_state["offers"][0]
                demand = offer["demands"][0]
                for _ in range(demand["quantity"]):
                    material = make_crafting_material_instance(engine._crafting_material_defs()[demand["definition_id"]], random.Random(1), source="测试", origin_world="human")
                    game.player.crafting_materials.append(material)
                add_item(game.player, "spirit_stone", 1000000)
                engine.store.save(game)
                page.evaluate("async id => { await loadGame(id); render(game); }", game_id)
                page.locator('[data-panel-target="exchange"]').click()
                page.locator("#exchange-content").get_by_role("button", name="青笠客", exact=True).click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                first = page.locator("#exchange-content section").first
                first.locator("summary").click()
                for field in first.locator('input[type="number"]').all():
                    field.fill("1")
                first.get_by_role("button", name="提交交换").click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                assert "已成交" in page.locator("#exchange-content section").first.text_content()
                page.screenshot(path=str(ROOT / "build/exchange-134.png"))
                game = engine.store.load(game_id)
                game.auction_state = {"id": "smoke", "status": "black_market", "world": "human", "location_id": game.player.location_id, "location_name": "无棣原"}
                engine.store.save(game)
                engine.search_black_market(game_id, "阵法材料")
                page.evaluate("async id => { await loadGame(id); render(game); }", game_id)
                page.locator('[data-panel-target="auction"]').click()
                first = page.locator("#black-market-results .auction-lot").first
                first.locator('input[type="number"]').fill("3")
                first.get_by_role("button").click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                assert len(engine.store.load(game_id).player.formation_materials) == 3
                engine.natal_artifact_action(game_id, "bind", "starfall_blade")
                page.evaluate("async id => { await loadGame(id); render(game); }", game_id)
                page.locator('[data-panel-target="natal-artifact"]').click()
                page.get_by_role("button", name="移除本命 · 下次突破 −10%").click()
                page.locator("#game-confirm-accept").click()
                page.wait_for_function("!document.body.classList.contains('busy')")
                assert engine.store.load(game_id).player.natal_origin_penalty == .1
                assert not errors, errors
                browser.close()
        finally:
            httpd.shutdown()
    print("Release 1.34 browser checks passed")


if __name__ == "__main__":
    main()
