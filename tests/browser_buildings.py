"""Real map clicks and event submissions in all themes, with original map art."""
import copy
import json
import io
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from PIL import Image
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item, remove_item
from cultivation_life.system.economy.ledger import balance
from cultivation_life.system.buddhist.rules import buddhist_config
from scripts.browser_navigation import navigation_locator, click_control


def choice(page, identity):
    old = page.evaluate('game.pending_event.id')
    index = page.evaluate('id=>game.pending_event.choices.findIndex(c=>c.id===id)', identity)
    assert index >= 0, identity
    page.locator('#event-choices button').nth(index).click()
    page.wait_for_function('id=>!busy&&game.pending_event?.id!==id', arg=old)


def open_map(page):
    navigation_locator(page, '[data-panel-target=map]').click()
    page.locator('#map-view-tabs [aria-controls=map-atlas]').click()
    click_control(page.locator('[data-atlas-mode="3d"]'))


def main():
    output = ROOT / 'build/building-browser';output.mkdir(parents=True,exist_ok=True)
    report = []
    with tempfile.TemporaryDirectory() as folder:
        engine = GameEngine(ROOT,Path(folder)/'saves')
        game = engine._load(engine.create_game('洞府验收','heavenly','dao',317,preset_id='core')['id'])
        game.pending_event=None;add_item(game.player,'spirit_stone',100000);engine.store.save(game)
        start_age,start_rng=game.player.age,game.rng_state
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            httpd=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=httpd.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for theme in ('a','b','d','f'):
                        for width,height in ((1440,960),(393,852)):
                            page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce')
                            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                            page.goto(f'http://127.0.0.1:{httpd.server_port}')
                            page.wait_for_function('window.GameThemes&&configData')
                            page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]').click()
                            page.evaluate('async id=>loadGame(id)',game.id)
                            open_map(page)
                            if theme=='a' and width==1440:
                                page.locator('#map-view-tabs [aria-controls=map-locations]').click()
                                page.locator('#map-locations [data-building-action=construct]').click()
                                page.wait_for_function('!busy&&game.buildings.inside')
                                assert page.locator('#event-card').is_visible()
                                choice(page,'level:2');choice(page,'plan:2:professional')
                                # A stale confirmation must refresh disabled choices without charging.
                                saved=engine.store.load(game.id);funds=balance(saved,'player')
                                remove_item(saved.player,'spirit_stone',funds);engine.store.save(saved)
                                page.locator('#event-choices button').first.click()
                                page.wait_for_function('!busy&&!game.pending_event.choices[0].enabled')
                                assert page.locator('#event-choices button').first.is_disabled()
                                assert not engine.store.load(game.id).building_state['records']
                                saved=engine.store.load(game.id);add_item(saved.player,'spirit_stone',funds);engine.store.save(saved)
                                page.evaluate('async id=>loadGame(id)',game.id)
                                choice(page,'confirm');choice(page,'leave');open_map(page)
                            page.wait_for_function('document.querySelector(".atlas-building-marker")')
                            page.wait_for_function('document.querySelector(".atlas-scene")?.dataset.artworkState!=="loading"')
                            assert page.locator('.atlas-scene').get_attribute('data-artwork-state')=='ready'
                            pixels=page.locator('.atlas-viewport').screenshot(path=str(output/f'atlas-{theme}-{width}.png'))
                            assert len(Image.open(io.BytesIO(pixels)).convert('RGB').getcolors(1000000))>1000
                            assert page.locator('#map-atlas .building-row[data-building-id^="cave:"]').count()==1
                            assert '8%' in page.evaluate('String(Math.round((game.buildings.qi_multiplier-1)*100))+"%"')
                            # Both projection modes show the same current-world building.
                            click_control(page.locator('[data-atlas-mode=flat]'))
                            assert page.locator('.atlas-building-marker').count()==page.evaluate('game.map.locations.filter(p=>p.buildings.length).length')
                            click_control(page.locator('[data-atlas-mode="3d"]'))
                            remote=page.evaluate('game.map.locations.find(p=>!p.current&&!p.buildings.length).id')
                            page.locator('[aria-label="地图地点"]').select_option(remote)
                            assert page.locator('#map-atlas .building-row').count()==0
                            assert page.evaluate('game.map.current')==game.player.location_id
                            page.locator('[aria-label="地图地点"]').select_option(game.player.location_id)
                            page.locator('#map-atlas .building-row[data-building-id^="cave:"]').scroll_into_view_if_needed()
                            page.screenshot(path=str(output/f'map-{theme}-{width}.png'))
                            page.locator('#map-atlas .building-row[data-building-id^="cave:"] [data-building-action=enter]').click()
                            page.wait_for_function('!busy&&game.buildings.inside')
                            choice(page,'qi');assert '8%' in page.locator('#event-body').inner_text()
                            choice(page,'back');choice(page,'details');choice(page,'back')
                            page.screenshot(path=str(output/f'interior-{theme}-{width}.png'))
                            # A superseded saved event rejects the visible button and recovers once.
                            engine.building_action(game.id,'choose',event_id=engine.get_game(game.id)['pending_event']['id'],choice_id='qi')
                            page.locator('#event-choices button').first.click()
                            page.wait_for_function('!busy&&game.pending_event.choices[0].id==="back"')
                            choice(page,'back');choice(page,'leave')
                            saved=engine.store.load(game.id)
                            assert (saved.player.age,saved.rng_state)==(start_age,start_rng)
                            assert not page.evaluate('busy') and page.locator('[data-action=cultivate]').is_enabled()
                            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
                            assert not errors,errors
                            report.append(dict(theme=theme,width=width,height=height,zero_years=True,map_art=True))
                            page.close()
                    # The original temple is projected, upgraded and preserved on DLC removal.
                    saved=engine.store.load(game.id);saved.player.path='buddhist';engine.store.save(saved)
                    with patch.dict(buddhist_config(),enabled=True):
                        page=browser.new_page(viewport=dict(width=393,height=852))
                        page.goto(f'http://127.0.0.1:{httpd.server_port}')
                        page.wait_for_function('configData');page.evaluate('async id=>loadGame(id)',game.id)
                        open_map(page);page.locator('#map-atlas [data-building-action=temple-plan]').click()
                        page.wait_for_function('!busy&&game.buildings.inside');choice(page,'confirm')
                        choice(page,'temple');choice(page,'temple:upgrade');choice(page,'back')
                        saved=engine.store.load(game.id)
                        preserved=copy.deepcopy(saved.buddhist_state)
                        saved.pending_event['_followup_event']=copy.deepcopy(engine.events_by_id['EVT_SECT_FIRST_WARNING_001'])
                        engine.store.save(saved)
                        with patch.dict(buddhist_config(),enabled=False):
                            page.evaluate('async id=>loadGame(id)',game.id)
                            assert page.evaluate('game.pending_event.id')=='EVT_SECT_FIRST_WARNING_001'
                            assert not page.evaluate('game.buildings.inside')
                            page.locator('#event-choices button').first.click()
                            page.wait_for_function('!busy&&!game.pending_event')
                        assert engine.store.load(game.id).buddhist_state==preserved
                        page.close()
                    browser.close()
            finally:
                httpd.shutdown();httpd.server_close()
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Buildings UI passed: 4 themes x desktop/mobile, map art and markers, construction, stale choices, temple, followup and zero-year menus')


if __name__=='__main__':main()
