"""One browser/page at a time: fiscal disclosure, guard buttons and trust switch."""
import json
import os
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.system.economy import organizations, caravans
from cultivation_life.system.economy.enterprise_acquisition import acquire, price
from cultivation_life.system.economy.fleet_network import new_fleet, guard_required
from cultivation_life.system.economy.ledger import transfer_value, balance
from scripts.browser_navigation import navigation_locator, click_control, reveal_subpage
from test_family_expansion import family_game


def prepare(engine):
    game = family_game(engine)
    game = engine._load(game.id)
    game.player.realm_index = 2
    game.player.next_tribulation_age = None
    game.settings['silent_events'] = True
    game.family.location_id = game.player.location_id
    game.family.npcs[0].realm_index = 4
    game.player.faction_id = 'tianjian'
    game.sects['tianjian'].founded_by_player = True
    organizations.ensure_organizations(game, engine.maps)
    game.player.age += 5
    organizations.advance_organizations(game, engine.maps)
    caravans.ensure_caravans(game, engine.maps)
    region = game.economy_v2['transport']['worlds']['human']
    ids = {}
    for kind, identity in [('family', game.family.id), ('sect', 'tianjian'), ('independent', 'player')]:
        f = new_fleet(game, region, 'human', identity, kind, game.player.location_id, '护卫验收'+kind, player=kind!='family')
        transfer_value(game, 'background:human', 'caravan:'+f['id'], 5000, '验收商队周转金')
        f['investment'] = 5000
        f['trade_order'] = {'mode':'hold'}
        ids[kind] = f['id']
    row = acquire(game, engine.maps, 'human', game.player.location_id, 'mine', 'player', game.id, 'player', 2)
    transfer_value(game, 'player', 'estate:'+row['id'], 10000, '验收产业周转金')
    engine.store.save(game)
    return game.id, ids, row['id']


def expand(target):
    reveal_subpage(target.page, target)
    if target.get_attribute('open') is None:
        click_control(target.locator(':scope > summary'))


def main():
    output = ROOT/'build/economy-trust-browser'
    output.mkdir(exist_ok=True)
    reports = []
    layouts = [('a',1440,1000),('a',393,852)]
    if os.environ.get('CULTIVATION_BROWSER_LOW_MEMORY') != '1':
        layouts += [('f',1440,1000),('f',393,852)]
    with tempfile.TemporaryDirectory() as folder:
        engine = GameEngine(ROOT, Path(folder)/'saves')
        class Handler(server.Handler):
            def log_message(self, *args): pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)):
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = None
                    try:
                        for theme, width, height in layouts:
                            browser = pw.chromium.launch(args=['--disable-gpu','--renderer-process-limit=1'])
                            gid, ids, estate = prepare(engine)
                            page = browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce')
                            # These checks exercise fiscal controls, not terrain
                            # artwork. Avoid decoding the unrelated large maps.
                            page.route('**/assets/maps/**', lambda route: route.abort())
                            errors = []
                            page.on('pageerror', lambda error: errors.append(str(error)))
                            try:
                                page.goto(f'http://127.0.0.1:{httpd.server_port}')
                                page.wait_for_function('configData && window.GameThemes')
                                click_control(page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]'))
                                page.evaluate('async id=>loadGame(id)', gid)
                                for kind, panel in [('family','family'),('sect','faction')]:
                                    navigation_locator(page,f'[data-panel-target={panel}]').click()
                                    box = page.locator(f'#{panel}-card .organization-finance')
                                    expand(box)
                                    text = box.inner_text()
                                    assert '年度收入' in text and '年度支出' in text and '本期成交额' in text
                                    row = page.locator(f'#{panel}-card [data-fleet-id="{ids[kind]}"]')
                                    business = page.locator(f'#{panel}-card .organization-business')
                                    expand(business)
                                    guard = row.locator('[data-org-business=guard]')
                                    before = balance(engine._load(gid),'player')
                                    click_control(guard)
                                    page.wait_for_function('id => !busy && game.fleet_network.fleets.find(f=>f.id===id).guard_power>0', arg=ids[kind])
                                    saved = engine._load(gid)
                                    f = saved.economy_v2['transport']['worlds']['human']['fleets'][ids[kind]]
                                    assert f['guard_power'] == guard_required('human') and balance(saved,'player') < before
                                    expand(business)
                                    assert guard.is_disabled()
                                    page.screenshot(path=str(output/f'{theme}-{width}-{kind}.png'))
                                # Another client buys guards first; stale page clicks
                                # must recover without charging or enabling twice.
                                navigation_locator(page,'[data-panel-target=merchant]').click()
                                expand(page.locator('#fleet-network-content > details').first)
                                guard = page.locator(f'#fleet-network-content [data-fleet-id="{ids["independent"]}"] [data-fleet-action=guard]')
                                engine.fleet_action(gid, {'action':'guard','fleet_id':ids['independent']})
                                frozen = engine.store._path(gid).read_bytes()
                                click_control(guard)
                                page.wait_for_function('id => !busy && game.fleet_network.fleets.find(f=>f.id===id).guard_power>0',arg=ids['independent'])
                                assert engine.store._path(gid).read_bytes() == frozen
                                expand(page.locator('#fleet-network-content > details').first)
                                assert guard.is_disabled()
                                navigation_locator(page,'[data-panel-target=settings]').click()
                                toggle = page.locator('#setting-economy-trust')
                                assert not toggle.is_checked()
                                click_control(toggle)
                                page.wait_for_function('!busy && game.settings.economy_trust')
                                assert engine._load(gid).settings['economy_trust']
                                page.screenshot(path=str(output/f'{theme}-{width}-settings.png'))
                                click_control(page.locator('#settings-toggle'))
                                click_control(page.locator('[data-action=rest]'))
                                page.wait_for_function('!busy')
                                assert 'trust_config' in engine._load(gid).economy_v2['estates'][estate]
                                navigation_locator(page,'[data-panel-target=settings]').click()
                                click_control(toggle)
                                page.wait_for_function('!busy && !game.settings.economy_trust')
                                saved = engine._load(gid)
                                assert 'trust_config' not in saved.economy_v2['estates'][estate]
                                assert not saved.economy_v2['estates'][estate]['enabled']
                                frozen = engine.store._path(gid).read_bytes()
                                page.reload(); page.wait_for_function('configData')
                                page.evaluate('async id=>loadGame(id)',gid)
                                assert engine.store._path(gid).read_bytes() == frozen
                                assert not errors, errors
                                reports.append(dict(theme=theme,width=width,status='passed'))
                            finally:
                                page.close()
                                browser.close()
                                browser = None
                    finally:
                        if browser: browser.close()
            finally:
                httpd.shutdown(); httpd.server_close()
    (output/'report.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Trust browser: {len(reports)} layouts passed; real organization guard clicks, settings, time, restoration and reload')


if __name__ == '__main__': main()
