"""Real player trait controls, persistence and an obsolete wash submission."""
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.traits import mastery
from cultivation_life.models import SectNpc
from cultivation_life.rules import add_item
from scripts.browser_navigation import navigation_locator


def main():
    with tempfile.TemporaryDirectory() as directory:
        engine = GameEngine(ROOT, Path(directory)/"saves")
        view = engine.create_game("试法", "supreme_water","dao",19)
        game = engine._load(view["id"])
        game.pending_event = None
        game.player.trait_state = {}
        mastery(game.player,"light:kan")
        add_item(game.player, "green_bamboo_sword")
        disciple = SectNpc("student", "林清", "", 2, 1, 30, 200, world=game.player.world,
                           location_id=game.player.location_id, combat_artifact_id="soul_lamp")
        game.world_npcs[disciple.id] = disciple
        game.player.disciples = [game.link_relationship({"id": disciple.id})]
        engine.store.save(game)
        class Handler(server.Handler):
            def log_message(self,*args):
                pass
        with patch.object(server,"ENGINE",engine), ThreadingHTTPServer(("127.0.0.1",0),Handler) as http:
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(args=["--disable-gpu"])
                    page=browser.new_page()
                    errors=[]
                    page.on("pageerror",lambda exc: errors.append(str(exc)))
                    page.on("dialog",lambda dialog: dialog.accept())
                    page.goto(f"http://127.0.0.1:{http.server_port}")
                    page.wait_for_function("!!configData")
                    page.evaluate("id=>loadGame(id)",game.id)
                    page.locator(".hud-identity").click()
                    panel=page.locator("#personal-traits")
                    assert "鱼鳞之体" in panel.inner_text()
                    panel.get_by_role("button",name="洗去").click()
                    page.wait_for_function("!busy && !game.player.trait_state.owned.fish_scales")
                    code=page.evaluate("""async id=>(await fetch('/api/games/'+id+'/trait-config',
                        {method:'POST',headers:{'Content-Type':'application/json'},
                        body:JSON.stringify({action:'wash',key:'fish_scales'})})).status""",game.id)
                    assert code == 400
                    panel.get_by_role("button",name="重炼",exact=False).click()
                    page.wait_for_function("!busy && game.player.trait_state.owned.fish_scales")
                    assert engine.store.load(game.id).player.trait_state["owned"]["fish_scales"] == ["light:kan"]
                    stale = page.request.post(f"http://127.0.0.1:{http.server_port}/api/games/{game.id}/trait-config",
                        data=dict(action="study", key="artifact:green_bamboo_sword", expected_revision="obsolete"))
                    assert stale.status == 400 and "已过期" in stale.text()
                    assert "bamboo_edge" not in engine.store.load(game.id).player.trait_state["owned"]
                    panel.get_by_label("参悟来源").select_option("artifact:green_bamboo_sword")
                    panel.get_by_role("button",name="参悟特质").click()
                    page.wait_for_function("!busy && game.player.trait_state.owned.bamboo_edge")
                    assert "青篁剑骨" in panel.inner_text()
                    assert "青竹飞剑" in panel.locator("div").filter(has=page.get_by_text("紫 · 青篁剑骨",exact=False)).first.get_attribute("title")
                    page.keyboard.press("Escape")
                    navigation_locator(page, "[data-panel-target=npc-development]").click()
                    dialog = page.locator("#npc-development-dialog")
                    dialog.get_by_label("培养方向").select_option("traits")
                    dialog.get_by_label("参悟来源").select_option("artifact:soul_lamp")
                    dialog.get_by_role("button",name="参悟特质").click()
                    page.wait_for_function("!busy && document.querySelector('#npc-development-dialog')?.innerText.includes('洗去守魄灯心')")
                    saved = engine.store.load(game.id)
                    assert saved.world_npcs["student"].trait_state["owned"]["moon_lamp"] == ["artifact:soul_lamp"]
                    assert "moon_lamp" not in saved.player.trait_state["owned"]
                    assert not errors, errors
                    browser.close()
            finally:
                http.shutdown()


if __name__ == "__main__":
    main()
