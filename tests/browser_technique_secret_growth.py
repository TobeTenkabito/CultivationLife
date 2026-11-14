"""Actual growth-secret commands and stale reward previews in both pixel themes."""
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
from test_technique_secrets import prepare
from browser_technique_secrets import open_art
from scripts.browser_navigation import click_control


def main():
    output=ROOT/'build/secret-growth-browser';output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='growth-secrets-ui-') as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        original=engine.store.load(engine.create_game('百艺归真','supreme_water','dao',14731,preset_id='core')['id'])
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(args=['--disable-gpu','--renderer-process-limit=1'])
                    try:
                        for theme in ('light','dark'):
                            for width,height in ((1440,960),(393,852),(852,393)):
                                page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce')
                                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                                page.goto(f'http://127.0.0.1:{http.server_port}');page.wait_for_function('!!configData')
                                for identity,label in [('manual_earth_marrow','炼体积累'),('manual_spirit_return','灵气经验'),('manual_read_flame','炼丹经验')]:
                                    g=prepare(engine,original,identity)
                                    page.evaluate('async id=>loadGame(id)',g.id)
                                    if identity=='manual_earth_marrow':
                                        page.evaluate('GameThemes.ready');click_control(page.locator('#theme-open'))
                                        page.locator(f'#theme-dialog [data-pixel-theme-choice={theme}]').click()
                                        page.evaluate('GameThemes.saved');page.locator('[data-close-dialog=theme-dialog]').click()
                                    open_art(page,identity)
                                    preview=page.locator('#secret-root-detail .secret-art-objective')
                                    assert label in preview.inner_text() and '+' in preview.inner_text()
                                    if identity=='manual_spirit_return':
                                        # External legitimate progress makes the displayed before/after stale.
                                        current=engine.store.load(g.id);current.player.qi_experience['spirit']+=1;engine.store.save(current)
                                        with page.expect_response(lambda r:r.url.endswith('/secret-art')) as stale:
                                            click_control(page.get_by_role('button',name='施展秘术',exact=True))
                                        assert stale.value.status==400
                                        page.wait_for_function('!busy')
                                        assert not engine.store.load(g.id).player.secret_art_state.get('manuals')
                                        assert page.get_by_role('button',name='施展秘术',exact=True).is_enabled()
                                    click_control(preview)
                                    page.screenshot(path=str(output/f'{identity}-{theme}-{width}.png'))
                                    before=engine.store.load(g.id).player
                                    with page.expect_response(lambda r:r.url.endswith('/secret-art')) as cast:
                                        click_control(page.get_by_role('button',name='施展秘术',exact=True))
                                    assert cast.value.status==200
                                    page.wait_for_function('id=>!busy && game.secret_arts.library.find(a=>a.id===id).activated',arg=identity)
                                    p=engine.store.load(g.id).player
                                    if identity=='manual_earth_marrow':assert p.body_progress>before.body_progress and p.body_training==before.body_training
                                    elif identity=='manual_spirit_return':assert p.qi_experience['spirit']==before.qi_experience['spirit']+900
                                    else:assert p.art_experience['alchemy']>before.art_experience['alchemy']
                                    assert '成果已获得' in page.locator('#secret-root-detail').inner_text()
                                    assert page.locator('#secret-root-detail .secret-art-command').count()==0
                                    assert page.locator('#secret-art-card').evaluate('e=>e.scrollWidth<=e.clientWidth+2')
                                assert not errors,errors
                                page.close()
                    finally:browser.close()
            finally:http.shutdown();http.server_close()
    (output/'result.json').write_text(json.dumps(dict(passed=True,themes=2,layouts=3,types=3,
        checks=['exact-growth-preview','real-body-qi-art-grants','stale-reward-rejected-refresh',
                'no-repeat-button','no-horizontal-overflow']),indent=2),encoding='utf-8')
    print('Growth secrets browser passed: three growth types, two themes, three layouts')


if __name__=='__main__':main()
