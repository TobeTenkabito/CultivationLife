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
                page.on("pageerror", lambda error: errors.append(str(error)))
                response = page.goto(f"http://127.0.0.1:{server.server_port}/")
                assert response is not None and response.ok

                assert page.locator("#start-extension-manager").count() == 1
                assert page.locator("#start-extension-list [data-extension-id]").count() > 0
                page.locator("#achievement-open").click()
                assert page.locator(".achievement-row").count() == 44
                page.locator("#achievement-close").click()

                page.locator("#create input[name=name]").fill("界面烟测")
                page.locator("#create button[type=submit]").click()
                page.locator("#game").wait_for(state="visible")
                assert page.locator("#left-dock button").count() == 11
                assert page.locator("#right-dock button").count() == 14
                assert page.locator("#settings-dock button").count() == 1

                mapped: set[str] = set()
                dock_buttons = page.locator("[data-panel-target]")
                for index in range(dock_buttons.count()):
                    dock_buttons.nth(index).click()
                    mapped.update(page.locator(".operation-card").evaluate_all(
                        "rows => rows.map(row => row.dataset.operationCard)"
                    ))
                assert mapped == set(page.evaluate(
                    "OPERATIONS.map(row => row.operation)"
                ))
                assert page.evaluate("OPERATIONS.map(row => row.operation)") == list(
                    dict.fromkeys(page.evaluate("OPERATIONS.map(row => row.operation)"))
                )

                def open_card(panel: str, query: str):
                    page.locator(f'[data-panel-target="{panel}"]').first.click()
                    page.locator("#operation-search").fill(query)
                    card = page.locator(".operation-card")
                    assert card.count() == 1
                    card.locator("summary").click()
                    return card

                assert open_card("world-route", "选择飞升世界").locator("datalist option").count() > 5
                assert open_card("spirit-field", "播种灵田").locator("datalist option").count() > 0
                assert open_card("spirit-field", "开炉炼丹").locator("datalist").first.locator(
                    "option"
                ).count() > 0
                assert open_card("formation", "预览阵法").locator(
                    "[data-formation-slot]"
                ).count() == 9
                assert open_card("crafting", "预览炼器").locator(
                    "[data-allocation]"
                ).count() == 8

                debug = open_card("settings", "调试世界消息")
                debug.locator("input[type=checkbox]").check()
                with page.expect_response(
                    lambda item: item.url.endswith("/debug-world-news")
                ) as pending:
                    debug.locator("button[type=submit]").click()
                assert pending.value.status == 200
                page.wait_for_function("!document.body.classList.contains('busy')")
                assert page.locator("#save-state").text_content() == "已保存"
                assert not errors, errors
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    main()
