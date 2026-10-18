"""Actual map-node clicks, instance time, reload and destination catch-up."""
import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.engine.world import regions
from cultivation_life.system import spatial
from cultivation_life.system.economy.ledger import transfer_value
from scripts.browser_navigation import navigation_locator, click_control
from scripts.release_evidence import inputs_digest
from test_regional_rifts import prepare, node


def main():
    digest=inputs_digest(ROOT)
    output=ROOT/'build/regional-rifts-browser';output.mkdir(exist_ok=True)
    cases=[]
    with tempfile.TemporaryDirectory(prefix='rift-calendar-ui-') as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)),patch.object(
                spatial,'outcome_weights',return_value={'passage':1}):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for width,height in [(1440,960),(393,852)]:
                        identity=engine.create_game('节点补算验收','none','dao',20261018)['id']
                        game=engine._load(identity)
                        game.settings.update(silent_events=True,guixu_event_popup=False)
                        game.player.lifespan=10000;game.pending_event=None
                        regions.ensure(engine,game)
                        prepare(engine,game)
                        transfer_value(game,'background:human','background:spirit',123,'节点页面托管')
                        target=node(engine,game,'spirit')
                        page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce')
                        page.set_default_timeout(120000)
                        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                        page.goto(f'http://127.0.0.1:{http.server_port}')
                        def load():
                            page.wait_for_function('!!configData')
                            page.evaluate('async id=>loadGame(id)',identity)
                            navigation_locator(page,'[data-panel-target=map]').click()
                        def cross(target,destination):
                            click_control(page.locator(f'.spatial-rift[data-rift-id="{target}"] button'))
                            page.wait_for_function('destination=>!busy && game.player.world===destination',arg=destination)
                            return engine.store.load(identity)
                        load()
                        assert page.evaluate("game.spatial.rifts.every(r=>!('destination' in r))")
                        page.reload();load()
                        arrived=cross(target,'spirit')
                        assert arrived.world_simulation['regions']['spirit']['year']==arrived.player.age
                        assert arrived.economy_v2['accounts']['regional:escrow:spirit']['balance']==0
                        target=node(engine,arrived,'lost')
                        page.reload();load()
                        inside=cross(target,'lost')
                        frozen={w:r['year'] for w,r in inside.world_simulation['regions'].items()}
                        click_control(page.locator('#map-toggle'))
                        click_control(page.locator('[data-action=rest]'))
                        page.wait_for_function('!busy')
                        inside=engine.store.load(identity)
                        assert inside.player.age>arrived.player.age
                        assert {w:r['year'] for w,r in inside.world_simulation['regions'].items()}==frozen
                        target=node(engine,inside,'human')
                        page.reload();load()
                        final=cross(target,'human')
                        assert final.world_simulation['regions']['human']['year']==final.player.age
                        assert final.world_simulation['regions']['spirit']['year']==frozen['spirit']
                        assert final.spatial_state['current'] is None
                        assert not errors,errors
                        page.screenshot(path=str(output/f'node-return-{width}.png'))
                        cases.append(dict(width=width,status='passed',years=final.player.age-arrived.player.age))
                        page.close()
                    browser.close()
            finally:http.shutdown();http.server_close()
    assert inputs_digest(ROOT)==digest
    (output/'result.json').write_text(json.dumps(dict(source_sha256=digest,status='passed',cases=cases),ensure_ascii=False,indent=2),encoding='utf8')
    print('Real map node/instance/reload regional browser acceptance passed')


if __name__=='__main__':main()
