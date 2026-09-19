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

                page.locator("#create input[name=name]").fill("界面烟测")
                page.locator("#create button[type=submit]").click()
                page.locator("#game").wait_for(state="visible")
                assert page.locator("#system-nav button").count() == 8

                counts = []
                for index in range(8):
                    page.locator("#system-nav button").nth(index).click()
                    counts.append(page.locator(".operation-card").count())
                assert sum(counts) == 102  # Plus the direct advance/choice entries.
                assert page.evaluate("OPERATIONS.map(row => row.operation)") == list(
                    dict.fromkeys(page.evaluate("OPERATIONS.map(row => row.operation)"))
                )

                def open_card(query: str):
                    page.locator("#operation-search").fill(query)
                    card = page.locator(".operation-card")
                    assert card.count() == 1
                    card.locator("summary").click()
                    return card

                assert open_card("选择飞升世界").locator("datalist option").count() > 5
                assert open_card("播种灵田").locator("datalist option").count() > 0
                assert open_card("开炉炼丹").locator("datalist").first.locator(
                    "option"
                ).count() > 0
                assert open_card("预览阵法").locator(
                    "[data-formation-slot]"
                ).count() == 9
                assert open_card("预览炼器").locator(
                    "[data-allocation]"
                ).count() == 8

                debug = open_card("调试世界消息")
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
