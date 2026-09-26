"""Map directory navigation, overlapping notices and responsive layout."""
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server as server_module
from cultivation_life.engine import GameEngine


def main():
    with tempfile.TemporaryDirectory() as directory:
        engine = GameEngine(ROOT, Path(directory))
        game_id = engine.create_game('山河名录验收', 'heavenly', 'dao', 13710, preset_id='core')['id']
        saved = engine._load(game_id)
        saved.player.world = 'spirit'
        saved.player.location_id = engine.maps.worlds['spirit']['default']
        engine.store.save(saved)
        with patch.object(server_module, 'ENGINE', engine):
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), server_module.Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    page = browser.new_page(viewport={'width':1440,'height':1050})
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('!!configData')
                    page.evaluate('async id=>{await loadGame(id);render(game);}', game_id)
                    # Overlap all four notice types at one actual headquarters.
                    place = page.evaluate('''() => {
                      const id=game.merchant_system.alliances[0].hq;
                      const place=game.map.locations.find(row=>row.id===id);
                      place.ghost_parade={status:'active',start_age:game.player.age};
                      game.auction_system={available:true,location_id:id,status:'scheduled',actions_until_open:2};
                      game.exchange_system={available:true,location_id:id,status:'open'};
                      renderMap(game.map,game.auction_system);
                      return {id,name:place.name};
                    }''')
                    page.locator('[data-panel-target="map"]').click()
                    card = page.locator('#map-card')
                    card.wait_for(state='visible')
                    marker = card.locator(f'.map-location[data-location="{place["id"]}"]')
                    assert marker.locator('.auction-map-marker').count() == 0
                    assert marker.get_by_role('button', name=f'查看{place["name"]}的活动（3条）').count() == 1
                    page.screenshot(path=str(ROOT/'build/map-1371-terrain.png'), animations='disabled')
                    marker.get_by_role('button', name=f'查看{place["name"]}的活动（3条）').click()
                    directory = card.locator('#map-directory')
                    assert directory.is_visible() and not card.locator('#map-locations').is_visible()
                    assert directory.locator('.map-directory-entry').count() == 3
                    assert '2个时间单位后开幕' in directory.inner_text()
                    card.get_by_role('button', name='全部', exact=True).click()
                    assert directory.locator('.map-directory-entry').count() == 6
                    assert directory.locator('.map-directory-entry.merchant').count() == 3
                    xuanji = directory.locator('.map-directory-entry.merchant').filter(has_text='璇玑商盟')
                    assert '本界总部' in xuanji.text_content() and '分总部' not in xuanji.text_content()
                    assert directory.locator('select').count() == 0
                    page.screenshot(path=str(ROOT/'build/map-1371-directory-desktop.png'), animations='disabled')
                    page.set_viewport_size({'width':430,'height':900})
                    page.screenshot(path=str(ROOT/'build/map-1371-directory-mobile.png'), animations='disabled')
                    assert card.evaluate('el=>el.scrollWidth<=el.clientWidth+2')
                    directory.get_by_role('button', name='在地图中定位').click()
                    assert marker.is_visible()
                    assert marker.evaluate('el=>el===document.activeElement')
                    page.set_viewport_size({'width':1440,'height':1050})
                    # Realm name must reach both the route and lethal confirmation.
                    lethal = card.locator('.map-location.lethal').filter(has_text='合体境').first
                    assert lethal.count()
                    assert '境界序号' not in card.text_content()
                    lethal.get_by_role('button', name='强行前往（必死）').click()
                    assert '合体境' in page.locator('#game-confirm-body').text_content()
                    page.locator('#game-confirm-cancel').click()
                    # Live data refresh updates notices without duplicating rows.
                    page.evaluate("game.auction_system.status='black_market';renderMap(game.map,game.auction_system)")
                    card.get_by_role('button',name='活动与据点',exact=True).click()
                    assert '散场黑市' in directory.inner_text()
                    directory.get_by_role('button',name='查看全界').click()
                    card.get_by_role('button',name='商盟据点',exact=True).click()
                    assert directory.locator('.map-directory-entry.event,.map-directory-entry.auction,.map-directory-entry.ghost').count()==0
                    assert not errors, errors
                    browser.close()
            finally:
                httpd.shutdown(); httpd.server_close()
    print('Map 1.37.1 browser acceptance passed')


if __name__ == '__main__':
    main()
