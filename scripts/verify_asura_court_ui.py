"""Real court actions, persisted appointments, all themes and three viewports."""
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.rules import max_hp, max_mp
from cultivation_life.system.upper_institutions import account


class Quiet(server.Handler):
    def log_message(self, *args):
        pass


def main():
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
        server.PERSISTENCE_ROOT = Path(folder)
        engine = server.ENGINE = GameEngine(ROOT, Path(folder)/'saves')
        made = engine.create_game('血海新王', 'supreme_metal', 'demonic', 1530, preset_id='asura_upper')
        g = engine._load(made['id'])
        g.player.realm_index = 12
        g.player.hp, g.player.mp = max_hp(g.player), max_mp(g.player)
        account(g).update(merit=10000, earned=10000, regard=100)
        engine.store.save(g)
        httpd = ThreadingHTTPServer(('127.0.0.1',0), Quiet)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        errors = []
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                page = browser.new_page(viewport=dict(width=1440,height=1080))
                page.emulate_media(reduced_motion='reduce')
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{httpd.server_port}')
                page.wait_for_function('configData!==null')
                page.evaluate('(id)=>loadGame(id)', g.id)
                page.evaluate("UtilityPanels.open('upper-institution')")
                root = page.locator('#upper-institution-content')
                root.get_by_role('button', name='登记效力', exact=True).click()
                page.wait_for_function('!busy&&game.upper_institution.joined')
                for rank in range(1,6):
                    root.get_by_role('button', name='申请晋阶', exact=True).click()
                    page.wait_for_function('(r)=>!busy&&game.upper_institution.rank===r', arg=rank)
                root.get_by_role('button', name='政令', exact=True).click()
                root.get_by_role('heading',name='通商令',exact=True).locator('..').get_by_role('button').click()
                page.wait_for_function("!busy&&game.upper_institution.policy==='trade'")
                root.get_by_role('button', name='内政', exact=True).click()
                root.get_by_label('府库总管人选').select_option('asura_royal_court_1')
                root.get_by_role('heading',name='府库总管',exact=True).locator('..').get_by_role('button',name='任命',exact=True).click()
                page.wait_for_function("!busy&&game.upper_institution.court.offices.treasury==='asura_royal_court_1'")
                root.get_by_role('heading',name='万战互市 · 0/3',exact=True).locator('..').get_by_role('button').click()
                page.wait_for_function("!busy&&game.upper_institution.court.project?.id==='market'")
                root.get_by_role('heading',name='开仓安抚',exact=True).locator('..').get_by_role('button').click()
                page.wait_for_function('!busy&&game.upper_institution.court.public_support===65')
                for theme in 'abcdef':
                    page.evaluate('(t)=>document.querySelector(`[data-theme-picker=dialog] [data-theme-choice=${t}]`).click()',theme)
                    for width,height in [(1440,1080),(412,915),(915,412)]:
                        page.set_viewport_size(dict(width=width,height=height))
                        page.evaluate("UtilityPanels.open('upper-institution')")
                        for label in ['爵位','政令','内政','功勋','纪事']:
                            root.get_by_role('button',name=label,exact=True).click()
                            assert root.evaluate('e=>e.scrollWidth<=e.clientWidth+1'), (theme,width,label)
                            assert root.locator('button').evaluate_all('(rows)=>rows.every(e=>e.scrollWidth<=e.clientWidth+2)'), (theme,width,label)
                            if (label,width) in [('爵位',1440),('内政',412)]:
                                page.screenshot(path=str(ROOT/f'build/court-{theme}-{width}-1530.png'))
                page.reload()
                page.wait_for_function('configData!==null')
                page.evaluate('(id)=>loadGame(id)', g.id)
                page.wait_for_function("game?.upper_institution?.court.offices.treasury==='asura_royal_court_1'")
                saved = engine._load(g.id)
                state = account(saved)
                state['court']['challenge'] = dict(npc_id=state['court']['holders']['4'],rank=5,deadline=4)
                engine.store.save(saved)
                page.evaluate('(id)=>loadGame(id)',g.id)
                page.evaluate("UtilityPanels.open('upper-institution')")
                root.get_by_role('button',name='承认挑战并让位',exact=True).click()
                page.wait_for_function('!busy&&game.upper_institution.rank===4&&!game.upper_institution.court.king')
                assert not errors, errors
                browser.close()
        finally:
            httpd.shutdown()
    print('Asura court UI passed: actual promotion, policy, appointment, construction, decree, surrender and persistence; six themes, desktop, portrait and landscape.')


if __name__ == '__main__':
    main()
