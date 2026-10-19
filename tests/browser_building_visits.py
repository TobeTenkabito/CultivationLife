"""Four-theme gazetteer layout and real scenery/industry/temple choices."""
import copy
import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.building_rules import config
from cultivation_life.rules import add_item
from cultivation_life.system.buddhist.rules import buddhist_config
from test_economy_enterprises import buy
from scripts.browser_navigation import navigation_locator
from fixtures.city_management_release import prepare_city_management, landscape_management, inspect_city_management


def choice(page,identity):
    page.wait_for_function("!busy&&!document.documentElement.classList.contains('theme-switching')")
    old=page.evaluate('game.pending_event.id')
    index=page.evaluate('id=>game.pending_event.choices.findIndex(c=>c.id===id)',identity)
    assert index>=0,identity
    try:
        with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/choice')) as response:
            page.locator('#event-choices button').nth(index).click()
        actual=response.value
        assert actual.ok,actual.text()
        page.wait_for_function('id=>!busy&&game.pending_event?.id!==id',arg=old)
    except Exception as error:
        output=ROOT/'build/building-visits-browser'
        page.screenshot(path=str(output/'failed-choice.png'),full_page=True)
        snapshot=page.evaluate('JSON.stringify({busy,event:game?.pending_event,toast:document.querySelector("#toast")?.textContent,theme:document.documentElement.dataset.theme})')
        (output/'failed-choice.json').write_text(snapshot,encoding='utf-8')
        raise AssertionError(f'Actual choice {identity}: {error}; state={snapshot}') from error


def open_map(page):
    if not page.locator('#map-view-tabs').is_visible():
        navigation_locator(page,'[data-panel-target=map]').click()
    page.locator('#map-view-tabs [aria-controls=map-locations]').click()


def fixture(engine):
    game=engine._load(engine.create_game('山河访客','heavenly','buddhist',2171,preset_id='core')['id'])
    game.pending_event=None;game.player.path='buddhist';game.settings.update(silent_events=True,combat_popup=False)
    add_item(game.player,'spirit_stone',10**8);engine.store.save(game)
    game,identity=buy(engine,game,'mine')
    engine.building_action(game.id,'temple-plan')
    shown=engine.get_game(game.id);engine.choose(game.id,'confirm',event_id=shown['pending_event']['id'])
    shown=engine.get_game(game.id);engine.choose(game.id,'leave',event_id=shown['pending_event']['id'])
    return engine.store.load(game.id),identity


def enter(page,identity):
    open_map(page)
    escaped=page.evaluate('s=>CSS.escape(s)',identity)
    page.locator(f'#map-locations .current .building-row[data-building-id="{escaped}"] [data-building-action=enter]').click()
    page.wait_for_function('!busy&&game.buildings.inside')


def management_check(engine,page,output,theme,width):
    from browser_city_buildings import click_prefix
    game=engine.create_game('城市经营实测','heavenly','dao',2172,preset_id='core')
    prepare_city_management(engine,game['id'])
    page.evaluate('async id=>loadGame(id)',game['id']);open_map(page)
    page.locator('#map-locations [data-building-action=city-plan]').click();page.wait_for_function('!busy&&game.buildings.inside')
    choice(page,'city:economic');choice(page,'city:economic:mixed');click_prefix(page,'city:build:')
    city=page.evaluate('game.buildings.rows.find(r=>r.id.startsWith("city:player:")).id')
    choice(page,'civic:main');choice(page,'civic:facilities');choice(page,'civic:exchange');click_prefix(page,'civic:commit:')
    choice(page,'civic:settle');assert page.locator('#event-choices button').first.is_disabled();choice(page,'leave')
    age=page.evaluate('game.player.age');page.locator('[data-action=rest]').first.click()
    page.wait_for_function('age=>!busy&&game.player.age>age',arg=age)
    assert page.evaluate('game.player.age')==age+1
    enter(page,city);choice(page,'civic:main');choice(page,'civic:settle');click_prefix(page,'civic:commit:')
    page.screenshot(path=str(output/f'management-{theme}-{width}.png'))
    choice(page,'civic:settle');assert page.locator('#event-choices button').first.is_disabled();choice(page,'leave')
    landscape_management(engine,game['id']);page.evaluate('async id=>loadGame(id)',game['id'])
    enter(page,'scenery:human:reed_letter')
    choice(page,'explore:main');choice(page,'explore:route:0');choice(page,'explore:finish:0:1')
    page.screenshot(path=str(output/f'landscape-story-{theme}-{width}.png'))
    choice(page,'explore:main');choice(page,'explore:route:1');choice(page,'explore:finish:1:1');choice(page,'leave')
    inspect_city_management(engine,game['id'])
    assert not page.evaluate('busy') and not page.evaluate('document.documentElement.scrollWidth>innerWidth+1')


def main():
    output=ROOT/'build/building-visits-browser';output.mkdir(parents=True,exist_ok=True)
    report=[]
    with tempfile.TemporaryDirectory() as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)),patch.dict(buddhist_config(),enabled=True):
            httpd=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=httpd.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    errors=[]
                    for theme in 'abdf':
                        for width,height in ((1440,960),(393,852)):
                            game,estate=fixture(engine)
                            page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce')
                            page.on('pageerror',lambda e:errors.append(str(e)))
                            page.goto(f'http://127.0.0.1:{httpd.server_port}');page.wait_for_function('configData&&window.GameThemes')
                            page.evaluate('GameThemes.ready')
                            page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]').click()
                            page.evaluate('GameThemes.saved')
                            page.evaluate('async id=>loadGame(id)',game.id);open_map(page)
                            overview=page.locator('#map-locations .current .building-overview')
                            assert overview.locator('.building-art').count()==3
                            pixels=page.evaluate('''async()=>{const im=new Image();im.src='/assets/building-gazetteer-2171.png';await im.decode();const c=document.createElement('canvas');c.width=1536;c.height=1024;const x=c.getContext('2d');x.drawImage(im,0,0);return [0,1,2,3,4,5].map(i=>{const a=x.getImageData((i%3)*512,Math.floor(i/3)*512,512,512).data;let n=0;for(let j=3;j<a.length;j+=4)if(a[j]>20)n++;return n;});}''')
                            assert all(n>20000 for n in pixels),pixels
                            assert page.locator('.building-command img').first.evaluate('im=>im.complete&&im.naturalWidth>0')
                            overview.scroll_into_view_if_needed()
                            overview.screenshot(path=str(output/f'gazetteer-{theme}-{width}.png'))
                            overview.locator('.building-row>summary').first.click()
                            assert overview.locator('.building-art').first.is_visible()
                            overview.screenshot(path=str(output/f'detail-{theme}-{width}.png'))
                            for button in overview.locator('button').all():
                                assert button.evaluate('n=>n.scrollWidth<=n.clientWidth+1&&n.scrollHeight<=n.clientHeight+1')
                            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
                            initial=copy.deepcopy(engine.store.load(game.id).economy_v2)
                            enter(page,'estate:'+estate)
                            choice(page,'visit:ledger');assert '当前没有在制批次' in page.locator('#event-body').inner_text();choice(page,'back')
                            choice(page,'visit:work');choice(page,'visit:resolve:work:0');choice(page,'back')
                            choice(page,'visit:lesson');old=page.evaluate('game.pending_event.id')
                            choice(page,'visit:resolve:lesson:1');choice(page,'back');choice(page,'visit:lesson')
                            assert page.locator('#event-choices button').first.is_disabled()
                            # An actual stale HTTP submission must refresh, never grant again.
                            page.evaluate('''async old=>{try{await api(`/api/games/${game.id}/choice`,{method:'POST',body:JSON.stringify({event_id:old,choice_id:'visit:resolve:lesson:0'})});}catch(e){}await loadGame(game.id);}''',old)
                            assert page.locator('#event-choices button').first.is_disabled()
                            choice(page,'leave')
                            assert engine.store.load(game.id).economy_v2==initial
                            enter(page,f'temple:{game.player.world}:{game.player.location_id}')
                            for activity in ('bell','pilgrims','lesson'):
                                choice(page,'visit:'+activity);choice(page,'visit:resolve:'+activity+':0');choice(page,'back')
                            choice(page,'visit:lesson');assert page.locator('#event-choices button').first.is_disabled();choice(page,'leave')
                            saved=engine.store.load(game.id);spec=config()['scenery'][game.player.world][0]
                            saved.player.location_id=spec['location_id'];engine.store.save(saved)
                            page.evaluate('async id=>loadGame(id)',game.id)
                            before=engine.store.load(game.id).player.to_dict()
                            enter(page,f"scenery:{game.player.world}:{spec['id']}")
                            for activity in ('trail','weather','traces'):
                                choice(page,'visit:'+activity);choice(page,'visit:resolve:'+activity+':1');choice(page,'back')
                            page.screenshot(path=str(output/f'exploration-{theme}-{width}.png'))
                            choice(page,'leave')
                            assert engine.store.load(game.id).player.to_dict()==before
                            assert not page.evaluate('busy') and page.locator('[data-action=cultivate]').is_enabled()
                            report.append(dict(theme=theme,width=width,assets_nonblank=True,real_visits=True,claims_once=True))
                            management_check(engine,page,output,theme,width)
                            page.close()
                    assert not errors,errors
                    browser.close()
            finally:httpd.shutdown();httpd.server_close()
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Building visits UI passed: 4 themes x desktop/mobile, transparent artwork, actual bounded insight, original books and zero-reward exploration')


if __name__=='__main__':main()
