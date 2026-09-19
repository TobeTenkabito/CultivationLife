"""Manual browser smoke test; uses a temporary database only."""

from __future__ import annotations

import tempfile
import threading
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cultivation_life.application import GameEngine  # noqa: E402
from cultivation_life.server import build_handler  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        engine = GameEngine(
            Path(temporary) / "games.db",
            content_directory=ROOT / "content",
            extension_root=ROOT,
        )
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0), build_handler(engine, ROOT / "web")
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                errors: list[str] = []
                console_errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on(
                    "console",
                    lambda message: (
                        console_errors.append(message.text)
                        if message.type == "error"
                        else None
                    ),
                )
                response = page.goto(f"http://127.0.0.1:{server.server_port}/")
                assert response is not None and response.ok

                assert page.locator("#start-extension-manager").count() == 1
                assert page.locator("#start-extension-list input[type=checkbox]").count() > 0
                assert page.locator("#quick-start-list button").count() == 9
                page.locator("#achievement-open").click()
                page.locator(".achievement-row").first.wait_for(state="visible")
                assert page.locator(".achievement-row").count() == 44
                page.locator("#achievement-close").click()

                page.locator("#new-game-form input[name=name]").fill("界面烟测")
                page.locator("#path-select").select_option("demonic")
                page.locator("#new-game-form button[type=submit]").click()
                page.locator("#game-screen").wait_for(state="visible")
                assert page.locator("nav.left-dock button").count() == 12
                assert page.locator("#strategy-dock button").count() == 14
                assert page.locator("nav.settings-dock button").count() == 1
                assert page.locator("#map-locations .map-location").count() >= 2
                assert "NaN" not in page.locator("body").inner_text()
                assert "undefined" not in page.locator("body").inner_text()
                technique_text = page.locator("#known-technique-list").text_content()
                assert "魔煞引气诀" in technique_text
                assert "魔源" in technique_text
                assert "机缘 +10%" in technique_text
                assert page.locator("#player-race").text_content() == "人族"

                game_id = str(engine.list_games()[0]["game_id"])
                state = engine.store.load(game_id)
                actor_id = str(state.controlled_entity_id)
                cultivation = state.entities.require(actor_id, "cultivation.state")
                cultivation.update(
                    realm_id="core", layer=1, opportunity=300.0, bottleneck="minor"
                )
                state.entities.put(actor_id, "cultivation.state", cultivation)
                engine.store.save(
                    state, [], player_name="界面烟测", expected_revision=state.revision
                )
                page.evaluate("id => loadGame(id)", game_id)
                page.wait_for_function("!document.body.classList.contains('busy')")
                assert "初期·1层" in page.locator("#realm-name").text_content()
                assert "53%" in page.locator("#breakthrough-reason").text_content()
                assert "基础 48%" in page.locator("#breakthrough-reason").text_content()

                visible_targets = page.locator("[data-panel-target]:visible")
                for index in range(visible_targets.count()):
                    button = visible_targets.nth(index)
                    target = button.get_attribute("data-panel-target")
                    button.click(force=True)
                    panel = page.locator(f"#{target}-card")
                    assert panel.count() == 1
                    assert panel.evaluate("node => node.classList.contains('panel-open')")

                page.locator('[data-panel-target="settings"]').click(force=True)
                with page.expect_response(
                    lambda item: item.url.endswith("/debug-world-news")
                ) as pending:
                    page.locator("#world-news-debug").click()
                assert pending.value.status == 200
                page.wait_for_function("!document.body.classList.contains('busy')")
                assert "开" in page.locator("#world-news-debug").text_content()

                before = page.locator("#age-line").text_content()
                with page.expect_response(
                    lambda item: item.url.endswith("/advance")
                ) as pending:
                    page.locator('[data-action="cultivate"]').click()
                assert pending.value.status == 200
                page.wait_for_function("!document.body.classList.contains('busy')")
                assert page.locator("#age-line").text_content() != before

                page.set_viewport_size({"width": 390, "height": 844})
                page.locator('[data-panel-target="map"]').evaluate("node => node.click()")
                assert page.evaluate("document.documentElement.scrollWidth === innerWidth")
                assert not errors, errors
                assert not console_errors, console_errors
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    main()
