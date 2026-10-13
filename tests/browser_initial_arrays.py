"""Real new-game permission and travel clicks against the repaired starting layout."""
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
from scripts.browser_navigation import navigation_locator,click_control


def main():
    output=ROOT/'build/economy-estate-audit/arrays-browser'
    output.mkdir(parents=True,exist_ok=True)
    results=[]
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
                    for theme in 'abdf':
                        for width,height in ((1440,1000),(393,852)):
                            game=engine._load(engine.create_game('初始阵点验收','supreme_metal','dao',419,preset_id='core')['id'])
                            game.pending_event=None
                            game.player.faction_id=None
                            game.player.fame=10000
                            engine.store.save(game)
                            page=browser.new_page(viewport=dict(width=width,height=height))
                            errors=[]
                            page.on('pageerror',lambda error:errors.append(str(error)))
                            page.goto(f'http://127.0.0.1:{httpd.server_port}')
                            page.wait_for_function('configData && window.GameThemes')
                            click_control(page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]'))
                            page.evaluate('async id=>loadGame(id)',game.id)
                            navigation_locator(page,'[data-panel-target=map]').click()
                            click_control(page.locator('#map-view-tabs button[aria-controls=map-locations]'))
                            assert page.evaluate('game.map.teleport.origin.id')=='wudi_plain'
                            assert not page.evaluate('game.map.teleport.origin.licensed')
                            before=engine.store._path(game.id).read_bytes()
                            click_control(page.get_by_role('button',name='申请通行许可',exact=True))
                            page.wait_for_function('!busy && game.map.teleport.origin.licensed')
                            assert page.get_by_role('button',name='已取得许可',exact=True).is_disabled()
                            click_control(page.get_by_role('button',name='持许可通行',exact=True))
                            destination=page.get_by_label('传送目的地',exact=True)
                            assert destination.locator('option[value=mirror_lake]').count()==0
                            destination.select_option('expanse_human_12')
                            click_control(page.get_by_role('button',name='确认传送',exact=True))
                            page.wait_for_function("!busy && game.player.location_id==='expanse_human_12'")
                            saved=engine.store.load(game.id)
                            assert saved.player.age==game.player.age and saved.player.world=='human'
                            assert page.evaluate('game.map.teleport.origin.id')=='expanse_human_12'
                            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
                            saved_bytes=engine.store._path(game.id).read_bytes()
                            page.evaluate('async id=>loadGame(id)',game.id)
                            assert engine.store._path(game.id).read_bytes()==saved_bytes and not errors
                            page.screenshot(path=str(output/f'{theme}-{width}.png'))
                            results.append(dict(theme=theme,width=width,status='passed'))
                            page.close()
                    browser.close()
            finally:
                httpd.shutdown();httpd.server_close()
    (output/'report.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print('Initial arrays browser passed: 8 layouts, new-game permission, repaired destinations, actual instant travel and reload')


if __name__=='__main__':main()
