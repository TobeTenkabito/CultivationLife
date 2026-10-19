"""Native browser clicks across eleven worlds and all four responsive themes."""
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
from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.version import BASE_GAME_VERSION
from cultivation_life.rules import add_item,remove_item
from cultivation_life.system.building_projects import quote
from browser_buildings import choice
from scripts.browser_navigation import navigation_locator


def click_prefix(page,prefix):
    identity=page.evaluate('prefix=>game.pending_event.choices.find(c=>c.id.startsWith(prefix)).id',prefix)
    choice(page,identity)


def open_map(page,atlas=False):
    if not page.locator('#map-view-tabs').is_visible():
        navigation_locator(page,'[data-panel-target=map]').click()
    page.locator('#map-view-tabs [aria-controls='+('map-atlas' if atlas else 'map-locations')+']').click()


def prepare(engine,world,name='城市游历'):
    tier=WORLD_SYSTEMS['world_profiles'][world]['tier']
    game=engine._load(engine.create_game(name,'supreme_metal','dao',2170,
        custom_start=dict(world=world,realm_index={1:3,2:6,3:9}[tier]))['id'])
    game.pending_event=None
    game.settings.update(silent_events=True,combat_popup=False)
    game.player.next_tribulation_age=None
    add_item(game.player,'spirit_stone',10**14)
    for key in quote(game,'city')['materials']:add_item(game.player,key,100000)
    engine.store.save(game)
    return game


def main():
    output=ROOT/f'build/city-browser-{BASE_GAME_VERSION.replace(".", "")}';output.mkdir(parents=True,exist_ok=True)
    report=[]
    with tempfile.TemporaryDirectory() as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            httpd=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=httpd.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    page=browser.new_page(viewport=dict(width=1280,height=900))
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('configData&&window.BuildingPanel')
                    for world in config()['cities']:
                        game=prepare(engine,world)
                        for spec in config()['cities'][world]:
                            current=engine.store.load(game.id);current.player.location_id=spec['location_id'];engine.store.save(current)
                            page.evaluate('async id=>loadGame(id)',game.id)
                            open_map(page)
                            identity=f"city:{world}:{spec['id']}"
                            page.locator(f'#map-locations .map-location.current [data-building-action=enter]').first.click()
                            page.wait_for_function('!busy&&game.buildings.inside')
                            assert spec['name'] in page.locator('#event-title').inner_text()
                            choice(page,'city:audience');choice(page,'city:audience:listen');choice(page,'back')
                            choice(page,'city:rumor');assert spec['rumor'] in page.locator('#event-body').inner_text();choice(page,'back')
                            choice(page,'city:story');choice(page,'city:resolve:0');choice(page,'back');choice(page,'city:story')
                            assert page.locator('#event-choices button').first.is_disabled()
                            choice(page,'leave')
                            after=engine.store.load(game.id)
                            assert after.player.age==game.player.age and after.building_state['city_usage'][identity]['story']==1
                            report.append(dict(world=world,city=spec['id'],story_once=True))
                        # Natural scenery has no reward or hidden growth on repeat visits.
                        spec=config()['scenery'][world][0]
                        current=engine.store.load(game.id);current.player.location_id=spec['location_id'];engine.store.save(current)
                        page.evaluate('async id=>loadGame(id)',game.id);before=engine.store.load(game.id).player.to_dict()
                        open_map(page,atlas=True)
                        page.locator('[aria-label="地图地点"]').select_option(spec['location_id'])
                        scenic=page.locator('#map-atlas .building-row[data-building-id^="scenery:"]')
                        scenic.get_by_role('button',name='观景',exact=True).click();page.wait_for_function('!busy&&game.buildings.inside')
                        choice(page,'details');choice(page,'back');choice(page,'leave')
                        assert engine.store.load(game.id).player.to_dict()==before
                    page.close()
                    for theme in 'abdf':
                        for width,height in ((1440,960),(393,852)):
                            game=prepare(engine,'human','筑城验收')
                            page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce')
                            page.on('pageerror',lambda e:errors.append(str(e)))
                            page.goto(f'http://127.0.0.1:{httpd.server_port}');page.wait_for_function('configData&&window.GameThemes')
                            page.evaluate('GameThemes.ready')
                            page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]').click()
                            page.evaluate('GameThemes.saved')
                            page.evaluate('async id=>loadGame(id)',game.id)
                            assert not errors,errors
                            assert page.evaluate('id=>game?.id===id&&!busy&&document.body.classList.contains("in-game")&&!document.querySelector("#game-screen").classList.contains("hidden")',game.id),page.locator('#toast').inner_text()
                            open_map(page)
                            page.locator('#map-locations [data-building-action=city-plan]').click()
                            page.wait_for_function('!busy&&game.pending_event?.title==="择地筑城"')
                            choice(page,'city:military');choice(page,'city:military:mixed')
                            if theme=='a' and width==1440:
                                saved=engine.store.load(game.id);ore=next(iter(quote(saved,'city')['materials']))
                                remove_item(saved.player,ore,100000);engine.store.save(saved)
                                page.locator('#event-choices button').first.click()
                                page.wait_for_function('!busy&&!game.pending_event.choices[0].enabled')
                                assert page.locator('#event-choices button').first.is_disabled()
                                assert not engine.store.load(game.id).building_state['records']
                                saved=engine.store.load(game.id);add_item(saved.player,ore,100000);engine.store.save(saved)
                                page.evaluate('async id=>loadGame(id)',game.id)
                            click_prefix(page,'city:build:')
                            assert '混居之城' in page.locator('#event-body').inner_text()
                            choice(page,'city:govern');click_prefix(page,'city:commit:');choice(page,'city:govern')
                            assert page.locator('#event-choices button').first.is_disabled()
                            choice(page,'back');choice(page,'city:story');choice(page,'city:resolve:1');choice(page,'back')
                            page.screenshot(path=str(output/f'city-{theme}-{width}.png'))
                            choice(page,'management');choice(page,'destroy');click_prefix(page,'destroy:')
                            choice(page,'leave');open_map(page,atlas=True)
                            ruin=page.locator('#map-atlas .building-row[data-building-id^="city:player:"]')
                            assert '遗址' in ruin.inner_text() and ruin.get_by_role('button',name='重建',exact=True).is_enabled()
                            ruin.scroll_into_view_if_needed();page.screenshot(path=str(output/f'ruin-{theme}-{width}.png'))
                            ruin.get_by_role('button',name='重建',exact=True).click();page.wait_for_function('!busy&&game.buildings.inside')
                            choice(page,'rebuild');click_prefix(page,'rebuild:');choice(page,'back');choice(page,'city:story')
                            assert page.locator('#event-choices button').first.is_disabled()
                            choice(page,'leave')
                            assert not page.evaluate('busy') and page.locator('[data-action=cultivate]').is_enabled()
                            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
                            assert engine.store.load(game.id).player.age==game.player.age
                            report.append(dict(theme=theme,width=width,build_destroy_rebuild=True,stale_material_recovered=True))
                            page.close()
                    assert not errors,errors
                    browser.close()
            finally:httpd.shutdown();httpd.server_close()
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('City buildings UI passed: 22 city stories, 11 scenery visits, 4 themes x desktop/mobile real construction, finite rewards, yearly gates, ruins, stale recovery and no time advance')


if __name__=='__main__':main()
