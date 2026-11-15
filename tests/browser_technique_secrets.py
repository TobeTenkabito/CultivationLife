"""Real linked-secret activation, equip, stale-event recovery; both pixel palettes."""
import copy
import json
import random
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
from cultivation_life.content_registry import TECHNIQUE_CATALOG
from cultivation_life.rules import learn_technique
from fixtures.secret_arts_release import pending_secret_art_event
from test_technique_secrets import prepare
from scripts.browser_navigation import navigation_locator, click_control


def open_art(page,identity):
    if not page.locator('#secret-art-card').evaluate("e=>e.classList.contains('panel-open')"):
        navigation_locator(page,'[data-panel-target=secret-art]').click()
    page.wait_for_function("document.querySelector('#secret-art-card').classList.contains('panel-open')")
    if page.locator('#secret-art-back').is_visible():click_control(page.locator('#secret-art-back'))
    click_control(page.locator('#secret-tab-known'))
    page.locator('#secret-art-filter').select_option('linked')
    click_control(page.locator(f'[data-secret-art={identity}]'))


def equip_support(page,name,identity):
    if page.locator('#secret-art-toggle').is_visible():click_control(page.locator('#secret-art-toggle'))
    click_control(page.locator('.hud-identity'))
    if not page.locator('.technique-library').evaluate('e=>e.open'):
        click_control(page.locator('.technique-library > summary'))
    row=page.locator('#known-technique-list .known-technique').filter(has_text=name)
    with page.expect_response(lambda r:r.url.endswith('/equip-technique')) as result:
        click_control(row.get_by_role('button',name='辅',exact=True,include_hidden=True))
    assert result.value.status==200
    page.wait_for_function('id=>!busy && game.player.support_technique.id===id',arg=identity)
    click_control(page.locator('[data-close-dialog=player-details-dialog]'))


def main():
    output=ROOT/'build/technique-secrets-browser';output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='manual-secrets-ui-') as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        original=engine.store.load(engine.create_game('秘术贯通','supreme_water','dao',14731,preset_id='core')['id'])
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(args=['--disable-gpu','--renderer-process-limit=1','--js-flags=--max-old-space-size=192'])
                    try:
                        for theme in ('light','dark'):
                            for width,height in ((1440,960),(393,852),(852,393)):
                                g=prepare(engine,original,'manual_five_color_ice')
                                learn_technique(g.player,copy.deepcopy(TECHNIQUE_CATALOG['TECH_TIANYUAN_ART']))
                                engine.store.save(g)
                                page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce')
                                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                                page.goto(f'http://127.0.0.1:{http.server_port}')
                                page.wait_for_function('!!configData')
                                page.evaluate('async id=>loadGame(id)',g.id)
                                page.evaluate('GameThemes.ready')
                                click_control(page.locator('#theme-open'))
                                page.locator(f'#theme-dialog [data-pixel-theme-choice={theme}]').click()
                                page.evaluate('GameThemes.saved')
                                page.locator('[data-close-dialog=theme-dialog]').click()
                                open_art(page,'manual_five_color_ice')
                                assert page.locator('#secret-root-detail li').count()==5
                                page.screenshot(path=str(output/f'five-color-{theme}-{width}.png'))
                                with page.expect_response(lambda r:r.url.endswith('/secret-art')) as activated:
                                    click_control(page.get_by_role('button',name='激活秘术',exact=True))
                                assert activated.value.status==200
                                page.wait_for_function("!busy && game.secret_arts.library.find(a=>a.id==='manual_five_color_ice').activated")
                                assert not engine.store.load(g.id).player.formation_materials
                                before=engine.store.load(g.id).player.to_dict()
                                duplicate=page.request.post(activated.value.url,data=activated.value.request.post_data_json)
                                assert duplicate.status==400
                                assert engine.store.load(g.id).player.to_dict()==before
                                equip_support(page,'天元术','TECH_TIANYUAN_ART')
                                assert not page.evaluate("game.secret_arts.library.some(a=>a.id==='manual_five_color_ice')")
                                open_art(page,'manual_know_heaven')
                                rank=engine.store.load(g.id).player.divine_sense_rank
                                with page.expect_response(lambda r:r.url.endswith('/secret-art')) as cast:
                                    click_control(page.get_by_role('button',name='领悟并施展',exact=True))
                                assert cast.value.status==200
                                page.wait_for_function('!busy')
                                assert engine.store.load(g.id).player.divine_sense_rank==rank+1
                                assert page.get_by_role('button',name='本境施展',exact=True).is_disabled()
                                equip_support(page,'高天寒芒','TECH_HIGH_SKY_COLD_RAY')
                                open_art(page,'manual_five_color_ice')
                                assert '生效中' in page.locator('#secret-root-detail').inner_text()
                                assert page.locator('#secret-root-detail .secret-art-command').count()==0
                                assert engine.store.load(g.id).player.divine_sense_rank==rank+1
                                # Real stale enabled button: pending event appears after the page was drawn.
                                g=prepare(engine,original,'manual_know_heaven')
                                page.evaluate('async id=>loadGame(id)',g.id)
                                open_art(page,'manual_know_heaven')
                                pending_secret_art_event(engine,g.id)
                                with page.expect_response(lambda r:r.url.endswith('/secret-art')) as stale:
                                    click_control(page.get_by_role('button',name='领悟并施展',exact=True))
                                assert stale.value.status==400
                                page.wait_for_function('!busy && !!game.pending_event')
                                assert page.get_by_role('button',name='领悟并施展',exact=True).is_disabled()
                                assert not engine.store.load(g.id).player.secret_art_state.get('manuals')
                                click_control(page.locator('#secret-art-toggle'))
                                click_control(page.locator('#event-choices button').first)
                                page.wait_for_function('!busy && !game.pending_event')
                                open_art(page,'manual_know_heaven')
                                assert page.get_by_role('button',name='领悟并施展',exact=True).is_enabled()
                                click_control(page.get_by_role('button',name='领悟并施展',exact=True))
                                page.wait_for_function("!busy && game.secret_arts.library.find(a=>a.id==='manual_know_heaven').activated")
                                assert page.locator('#secret-art-card').evaluate('e=>e.scrollWidth<=e.clientWidth+2')
                                page.screenshot(path=str(output/f'know-heaven-{theme}-{width}.png'))
                                # A trial starts after the equipment page was drawn: the old button must be rejected.
                                g=prepare(engine,original,'manual_five_color_ice')
                                page.evaluate('async id=>loadGame(id)',g.id)
                                if page.locator('#secret-art-toggle').is_visible():
                                    click_control(page.locator('#secret-art-toggle'))
                                click_control(page.locator('.hud-identity'))
                                if not page.locator('.technique-library').evaluate('e=>e.open'):
                                    click_control(page.locator('.technique-library > summary'))
                                row=page.locator('#known-technique-list .known-technique').filter(has_text='高天寒芒')
                                button=row.get_by_role('button',name='辅',exact=True,include_hidden=True)
                                assert button.is_enabled()
                                g=engine.store.load(g.id)
                                engine._start_breakthrough_trial(g,'traditional',4,5,'元婴',major=True,rng=random.Random(71))
                                assert g.active_trial
                                engine.store.save(g)
                                before=g.player.to_dict()
                                with page.expect_response(lambda r:r.url.endswith('/equip-technique')) as stale_equip:
                                    click_control(button)
                                assert stale_equip.value.status==400
                                page.wait_for_function('!busy && !!game.trial?.active')
                                assert button.is_disabled()
                                assert engine.store.load(g.id).player.to_dict()==before
                                # Newly added upper support book and ascension secret use this same UI.
                                for identity in ('manual_gate_buddhist_9','manual_gate_confucian_8'):
                                    g=prepare(engine,original,identity)
                                    page.evaluate('async id=>loadGame(id)',g.id)
                                    open_art(page,identity)
                                    with page.expect_response(lambda r:r.url.endswith('/secret-art')) as added:
                                        click_control(page.get_by_role('button',name='激活秘术',exact=True))
                                    assert added.value.status==200
                                    page.wait_for_function('(id)=>!busy && game.secret_arts.library.find(a=>a.id===id).activated',arg=identity)
                                    assert page.locator('#secret-art-card').evaluate('e=>e.scrollWidth<=e.clientWidth+2')
                                    page.screenshot(path=str(output/f'{identity}-{theme}-{width}.png'))
                                assert not errors,errors
                                page.close()
                    finally:browser.close()
            finally:http.shutdown();http.server_close()
    (output/'result.json').write_text(json.dumps(dict(passed=True,themes=2,layouts=3,
        checks=['real-activation','exact-five-materials','real-equip','hide-when-unequipped','resume-no-repayment',
                'permanent-rank','duplicate-rejected','stale-page-recovered','event-click','busy-cleared',
                'disabled-while-event','no-horizontal-overflow','stale-trial-equip-rejected','trial-equip-disabled',
                'new-upper-book-activation','new-ascension-secret-activation']),indent=2),encoding='utf-8')
    print('Technique secrets browser passed: six layouts, real activation/equip and stale-event recovery')


if __name__=='__main__':main()
