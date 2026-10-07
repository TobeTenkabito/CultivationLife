"""Real HTTP, family cash/production actions and fiscal disclosure in four themes."""
import json
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
from cultivation_life.system.economy import organizations as finance
from test_family_expansion import family_game


def prepare(engine):
    game = family_game(engine)
    game.family.npcs[0].realm_index = 4
    game.player.faction_id = next(s.id for s in game.sects.values() if s.world == 'human' and s.kind == 'sect')
    finance.ensure_organizations(game)
    game.player.age += 1
    finance.advance_organizations(game, engine.maps)
    engine.store.save(game)
    return game.id


def main():
    output = ROOT / 'build/economy-v2-r3-browser'
    output.mkdir(exist_ok=True)
    checks = []
    with tempfile.TemporaryDirectory() as folder:
        engine = GameEngine(ROOT, Path(folder) / 'saves')
        class Handler(server.Handler):
            def log_message(self, *args): pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)), patch.object(engine, '_intrigue_enabled', return_value=False):
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    for theme in 'abdf':
                        for width, height in [(1440, 1000), (393, 852)]:
                            gid = prepare(engine)
                            page = browser.new_page(viewport=dict(width=width, height=height))
                            errors = []
                            page.on('pageerror', lambda error: errors.append(str(error)))
                            page.goto(f'http://127.0.0.1:{httpd.server_port}')
                            page.wait_for_function('configData && window.GameThemes')
                            page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]').click()
                            page.evaluate('async id=>loadGame(id)', gid)
                            page.locator('[data-panel-target=family]').click()
                            saved = engine.store.load(gid)
                            source = finance.key('family', saved.family.id)
                            before = finance.balance(saved, source)
                            page.locator('[data-family-funds]').fill('1000')
                            page.get_by_role('button', name='注资', exact=True).click()
                            page.wait_for_function('!busy && game.family.ledger.resources===' + str(before + 1000))
                            saved = engine.store.load(gid)
                            assert finance.balance(saved, source) == before + 1000
                            page.get_by_role('button', name='组织经营采集（每年一次）', exact=True).click()
                            page.wait_for_function('!busy && game.family.gather_used')
                            assert page.get_by_role('button', name='本年已经营', exact=True).is_disabled()
                            page.locator('#family-card .organization-finance summary').click()
                            assert '驻地产出' in page.locator('#family-card .organization-finance').inner_text()
                            assert page.locator('#family-card').evaluate('(n)=>n.scrollWidth<=n.clientWidth+1')
                            page.locator('#family-card .organization-finance').scroll_into_view_if_needed()
                            page.screenshot(path=str(output / f'{theme}-{width}-family.png'))
                            page.locator('[data-panel-target=faction]').click()
                            page.locator('#faction-card .organization-finance summary').click()
                            assert '福利实付' in page.locator('#faction-card .organization-finance').inner_text()
                            page.screenshot(path=str(output / f'{theme}-{width}-sect.png'))
                            assert page.locator('#faction-card').evaluate('(n)=>n.scrollWidth<=n.clientWidth+1'), page.locator('#faction-card').evaluate('(n)=>[n.clientWidth,n.scrollWidth,...Array.from(n.querySelectorAll("*")).filter(e=>e.getBoundingClientRect().right>n.getBoundingClientRect().right).map(e=>[e.tagName,e.className,e.textContent.slice(0,80)])]')
                            page.screenshot(path=str(output / f'{theme}-{width}-sect.png'))
                            before = engine.store._path(gid).read_bytes()
                            page.reload(); page.wait_for_function('configData')
                            page.evaluate('async id=>loadGame(id)', gid)
                            assert engine.store._path(gid).read_bytes() == before
                            assert not errors, errors
                            checks.append(dict(theme=theme, width=width, status='passed'))
                            page.close()
                    browser.close()
            finally:
                httpd.shutdown(); httpd.server_close()
    (output / 'report.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Organization browser passed: 8 layouts, base family funding, real production, yearly button lock, sect finance and read-only reload')


if __name__ == '__main__': main()
