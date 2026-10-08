"""Real HTTP creation and blueprint/training clicks, desktop/mobile and four themes."""
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine


def main():
    output = ROOT/'build/release-251-browser'; output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        engine = GameEngine(ROOT, Path(directory)/'saves')
        class Handler(server.Handler):
            def log_message(self, *_args): pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(directory)):
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    for theme in 'abdf':
                        for width, height in [(1440,1000),(393,852)]:
                            page = browser.new_page(viewport=dict(width=width,height=height))
                            errors = []; page.on('pageerror',lambda e:errors.append(str(e)))
                            page.goto(f'http://127.0.0.1:{httpd.server_port}')
                            page.wait_for_selector('#custom-start')
                            page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]').click()
                            identity = page.evaluate("""async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'本相验收',preset_id:'nether_upper',monster_species_id:'serpent',seed:251})});await loadGame(g.id);return g.id;}""")
                            page.locator('[data-panel-target=upper-voisinage]').click()
                            box = page.locator('[data-true-form]')
                            box.get_by_text('蟠天锁相',exact=True).wait_for(state='visible')
                            before = engine._load(identity)
                            box.get_by_role('button',name='确认本相蓝图',exact=True).click()
                            page.wait_for_function('!busy && !!game.upper_voisinages.true_form.blueprint')
                            after = engine._load(identity)
                            assert before.rng_state == after.rng_state
                            assert before.player.immortal_aperture == after.player.immortal_aperture
                            key = after.player.world_voisinages['nether']['true_form']['blueprint_id']
                            panel = page.locator(f'[data-voisinage-id="{key}"]')
                            panel.locator('summary').click()
                            panel.get_by_role('button',name='领悟并开域',exact=True).click()
                            page.wait_for_function('!busy && game.upper_voisinages.true_form.level===1')
                            panel.get_by_role('button',name='选为斗法邻域',exact=True).click()
                            page.wait_for_function('!busy && game.upper_voisinages.rows.at(-1).active')
                            for level in (2,3):
                                panel.get_by_role('button',name='培养下一层',exact=True).click()
                                page.wait_for_function('(n)=>!busy && game.upper_voisinages.true_form.level===n',arg=level)
                            assert panel.get_by_role('button',name='培养下一层').is_disabled()
                            box.get_by_role('button',name='铭定辅权能',exact=True).click()
                            page.wait_for_function('!busy && game.upper_voisinages.true_form.blueprint.secondary_locked')
                            assert panel.get_by_role('button',name='培养下一层').is_disabled() # realm gate still applies
                            assert page.locator('#upper-voisinage-card').evaluate('e=>e.scrollWidth<=e.clientWidth+1')
                            page.locator('#upper-voisinage-card').screenshot(path=str(output/f'{theme}-{width}-true-form.png'))
                            snapshot = engine._load(identity).player.world_voisinages
                            page.reload(); page.wait_for_selector('#custom-start')
                            page.evaluate('async id=>loadGame(id)', identity)
                            assert engine._load(identity).player.world_voisinages == snapshot
                            assert not errors, errors
                            page.close()
                    browser.close()
            finally:
                httpd.shutdown(); httpd.server_close()
    print('Release 251 UI passed: real creation, immutable blueprint, paid training, selection, auxiliary lock, realm gates, reload, four themes and two widths')


if __name__ == '__main__': main()
