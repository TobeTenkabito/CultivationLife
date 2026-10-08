"""Real HTTP/page actions; annual ambient incidents isolated from this UI case."""
import json
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from scripts.release_evidence import inputs_digest


def main():
    output=ROOT/'build/release-260-browser';output.mkdir(exist_ok=True)
    fingerprint=inputs_digest(ROOT)
    with tempfile.TemporaryDirectory() as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)),patch.object(engine,'_advance_world_year',return_value=True):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for theme in 'abdf':
                        for width,height in [(1440,1000),(393,852)]:
                            page=browser.new_page(viewport=dict(width=width,height=height));errors=[]
                            page.on('pageerror',lambda e:errors.append(str(e)))
                            page.goto(f'http://127.0.0.1:{http.server_port}')
                            page.wait_for_selector('#custom-start')
                            page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]').click()
                            identity=page.evaluate("""async()=>{const g=await api('/api/games',{method:'POST',body:JSON.stringify({name:'照魂验收',preset_id:'reincarnation_upper',seed:260})});await loadGame(g.id);return g.id;}""")
                            page.locator('[data-panel-target=upper-voisinage]').click()
                            box=page.locator('[data-soul-form]')
                            box.get_by_label('魂因',exact=True).select_option('battle_scars')
                            box.get_by_label('归真道路预览').select_option('sever')
                            box.get_by_text('断戈寂灭域',exact=True).wait_for()
                            box.get_by_role('button',name='照前尘 · 参悟一单位').click()
                            page.wait_for_function("!busy && game.pending_event?.id==='EVT_SOUL_CONTEMPLATION'")
                            # The normal event panel remains reachable from the utility overlay.
                            page.evaluate("UtilityPanels.close('upper-voisinage')")
                            page.get_by_role('button',name='断执 · 割断束缚',exact=True).click()
                            page.wait_for_function('!busy && !!game.upper_voisinages.soul_form.blueprint')
                            page.locator('[data-panel-target=upper-voisinage]').click()
                            g=engine._load(identity);key=g.player.world_voisinages['reincarnation']['ghost_soul_form']['blueprint_id']
                            panel=page.locator(f'[data-voisinage-id="{key}"]');panel.locator('summary').click()
                            panel.get_by_role('button',name='领悟并开域',exact=True).click()
                            page.wait_for_function('!busy && game.upper_voisinages.soul_form.level===1')
                            for level in (2,3,4):
                                panel.get_by_role('button',name='培养下一层',exact=True).click()
                                page.wait_for_function('(n)=>!busy && game.upper_voisinages.soul_form.level===n',arg=level)
                            assert panel.get_by_role('button',name='培养下一层').is_disabled()
                            box.get_by_role('button',name='铭定魂相辅权能',exact=True).click()
                            page.wait_for_function('!busy && game.upper_voisinages.soul_form.blueprint.secondary_locked')
                            assert panel.get_by_role('button',name='培养下一层').is_disabled()
                            panel.get_by_role('button',name='选为斗法邻域',exact=True).click()
                            page.wait_for_function('!busy && game.upper_voisinages.rows.at(-1).active')
                            assert page.locator('#upper-voisinage-card').evaluate('e=>e.scrollWidth<=e.clientWidth+1')
                            page.locator('#upper-voisinage-card').screenshot(path=str(output/f'{theme}-{width}-soul.png'))
                            before=engine._load(identity).player.world_voisinages
                            page.reload();page.wait_for_selector('#custom-start');page.evaluate('async id=>loadGame(id)',identity)
                            assert engine._load(identity).player.world_voisinages==before
                            assert not errors,errors
                            page.close()
                    browser.close()
            finally:http.shutdown();http.server_close()
    assert inputs_digest(ROOT)==fingerprint
    (ROOT/'build/soul-ui-260.json').write_text(json.dumps(dict(status='passed',inputs_sha256=fingerprint,themes=list('abdf'),viewports=2)),encoding='utf-8')
    print('Soul form UI passed: four themes, desktop/mobile, real choices, paid training, realm gate, selection and reload')


if __name__=='__main__':main()
