"""Both pixel themes, actual temple requests, stale recovery and annual interruption."""
import random
import json
import copy
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.building_rules import config
from cultivation_life.rules import add_item
from cultivation_life.system.earth_temple import bill
from cultivation_life.system.earth_temple_rules import state
from scripts.westward_navigation import open_westward
from scripts.browser_navigation import navigation_locator, click_control, set_theme
from browser_buildings import choice
from cultivation_life.system.economy.ledger import balance


def main():
    output = ROOT / 'build/earth-temple-browser'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='earth-temple-ui-') as folder:
        engine = GameEngine(ROOT, Path(folder) / 'saves')
        class Handler(server.Handler):
            def log_message(self, *args): pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{http.server_port}'
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    for theme, width, height in [('light',1440,1000), ('dark',1440,1000), ('light',390,844), ('dark',390,844), ('dark',754,365)]:
                        if len(sys.argv)>1 and sys.argv[1]!=f'{theme}-{width}':continue
                        g = engine._load(engine.create_game('地仙庙域验收', 'supreme_metal', 'dao', 360, preset_id='true_immortal')['id'])
                        g.pending_event = None
                        g.player.location_id = next(c['location_id'] for c in config()['cities']['celestial'] if c['population']=='mixed')
                        g.player.next_tribulation_age = None
                        g.heavenly_court['open_election'] = None
                        g.settings.update(silent_events=True, combat_popup=False, court_election_popup=False)
                        add_item(g.player, 'spirit_stone', 10**11)
                        for key in bill(g)['materials']: add_item(g.player, key, 1000)
                        engine.store.save(g)
                        page = browser.new_page(viewport=dict(width=width, height=height), reduced_motion='reduce')
                        errors = []
                        page.on('pageerror', lambda error: errors.append(str(error)))
                        page.goto(base); page.wait_for_function('!!configData && !busy')
                        set_theme(page, theme); page.evaluate('id=>loadGame(id)', g.id)
                        open_westward(page,'地仙庙域')
                        open_westward(page,'地仙庙域')
                        page.locator('.earth-temple').wait_for()
                        portrait=page.locator('#building-affairs-content .temple-portrait img')
                        page.wait_for_function("(()=>{const i=document.querySelector('#building-affairs-content .temple-portrait img');return i?.complete&&i.naturalWidth>0})()")
                        assert portrait.get_attribute('src').endswith('land-temple-intact-361.png')
                        saved = engine.store._path(g.id).read_bytes()
                        open_westward(page,'专修')
                        open_westward(page,'地仙庙域')
                        assert engine.store._path(g.id).read_bytes() == saved
                        # Same visible quote becomes obsolete through a real current command.
                        payload = page.evaluate("({action:'earth_build',target_id:game.yaochi.earth.token+'|'+game.yaochi.earth.cities.find(c=>!c.reason).id})")
                        response = page.request.post(base+f'/api/games/{g.id}/yaochi-action', data=payload)
                        assert response.status == 200
                        with page.expect_response(lambda r:r.url.endswith('/yaochi-action')) as stale:
                            click_control(page.locator('[data-earth-action=earth_build]:enabled').first)
                        assert stale.value.status == 400
                        page.wait_for_function('!busy && !!game.yaochi.earth.temple')
                        assert page.locator('[data-earth-action=earth_cultivate]').is_disabled()
                        # Return locates the real building even after entering from a different map tab.
                        click_control(page.locator('#building-affairs-content .building-return'))
                        page.locator('#map-view-tabs [aria-controls=map-locations]').click()
                        temple_id=page.evaluate('game.yaochi.earth.temple.id')
                        click_control(page.locator('#map-locations [data-building-affairs='+json.dumps(temple_id)+']').first)
                        click_control(page.locator('#building-affairs-content .building-return'))
                        assert page.locator('#map-atlas').is_visible()
                        assert page.locator('#map-atlas [aria-label="地图地点"]').input_value()==page.evaluate('game.map.current')
                        art=page.locator('#map-atlas [data-building-id='+json.dumps(temple_id)+'] img.building-art')
                        assert art.get_attribute('src')==portrait.get_attribute('src')
                        open_westward(page,'地仙庙域')
                        assert page.locator('.utility-panel.panel-open').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                        page.locator('.utility-panel.panel-open').evaluate('n=>n.scrollTop=0')
                        page.screenshot(path=str(output/f'{theme}-{width}-overview.png'), animations='disabled')
                        click_control(page.locator('[data-earth-action=earth_accept][data-earth-target=watch]'))
                        page.wait_for_function('!busy && !!game.yaochi.earth.duty')
                        age = engine._load(g.id).player.age
                        original = engine._advance_world_year
                        def interrupt(game, rng, news, **kwargs):
                            result = original(game, rng, news, **kwargs)
                            if game.player.age == age+3:
                                warning = engine._instantiate_event(engine.events_by_id['EVT_SECT_FIRST_WARNING_001'], game, random.Random(1))
                                warning['_followup_event'] = engine._prepare_treasure_reward_event(game, random.Random(2))
                                game.pending_event = warning
                                return False
                            return result
                        with patch.object(engine, '_advance_world_year', side_effect=interrupt):
                            click_control(page.locator('[data-earth-action=earth_work]'))
                            page.wait_for_function('!busy && !!game.pending_event')
                        assert page.evaluate('game.yaochi.earth.duty.progress') == 3
                        assert page.locator('[data-earth-action=earth_work]').is_disabled()
                        page.locator('.utility-panel.panel-open .section-title > button[id$="-toggle"]').click()
                        click_control(page.locator('#event-choices button'))
                        page.wait_for_function('!busy && game.pending_event?.id !== "EVT_SECT_FIRST_WARNING_001"')
                        click_control(page.locator('#event-choices button:enabled').first)
                        page.wait_for_function('!busy && !game.pending_event')
                        open_westward(page,'地仙庙域')
                        assert page.locator('[data-earth-action=earth_work]').is_enabled()
                        with patch('cultivation_life.engine.orchestration.advancement._finish_action_events', return_value=None):
                            click_control(page.locator('[data-earth-action=earth_work]'))
                            page.wait_for_function('!busy && game.yaochi.earth.duty.progress===10')
                        assert page.locator('[data-earth-action=earth_plan]').count() == 2
                        assert page.locator('.utility-panel.panel-open').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                        page.screenshot(path=str(output/f'{theme}-{width}-plans.png'), animations='disabled')
                        click_control(page.locator('[data-earth-action=earth_plan][data-earth-target=standard]'))
                        page.wait_for_function('!busy && game.yaochi.earth.duty.stage==="service"')
                        if width == 1440 and theme == 'dark':
                            with patch('cultivation_life.engine.orchestration.advancement._finish_action_events', return_value=None):
                                click_control(page.locator('[data-earth-action=earth_work]'))
                                page.wait_for_function('!busy && game.yaochi.earth.duty.progress===100', timeout=90000)
                                click_control(page.locator('[data-earth-action=earth_claim]'))
                                page.wait_for_function('!busy && !game.yaochi.earth.duty')
                                assert page.evaluate('game.yaochi.earth.allowance') == 400
                                click_control(page.locator('[data-earth-action=earth_cultivate]'))
                                page.wait_for_function('!busy && game.yaochi.earth.allowance===300', timeout=90000)
                            page.screenshot(path=str(output/f'{theme}-{width}-faith.png'), animations='disabled')
                            held = copy.deepcopy(state(engine._load(g.id)))
                            cash = balance(engine._load(g.id), 'player')
                            page.locator('.utility-panel.panel-open .section-title > button[id$="-toggle"]').click()
                            navigation_locator(page, '[data-panel-target=map]').click()
                            page.locator('#map-view-tabs [aria-controls=map-locations]').click()
                            row = page.locator(f'#map-locations [data-building-id="{held["temple_id"]}"]')
                            assert '土地庙' in row.locator('.building-meta').inner_text()
                            click_control(row.locator('[data-building-action=manage]'))
                            page.wait_for_function('!busy && !!game.pending_event')
                            choice(page, 'destroy')
                            choice(page, page.evaluate('game.pending_event.choices.find(c=>c.id.startsWith("destroy:")).id'))
                            assert page.evaluate('game.yaochi.earth.temple.status') == 'destroyed'
                            open_westward(page,'地仙庙域')
                            ruin=page.locator('#building-affairs-content .temple-portrait img')
                            page.wait_for_function("(()=>{const i=document.querySelector('#building-affairs-content .temple-portrait img');return i?.complete&&i.naturalWidth>0})()")
                            assert ruin.get_attribute('src').endswith('land-temple-ruin-361.png')
                            page.screenshot(path=str(output/f'{theme}-{width}-temple-ruin.png'),animations='disabled')
                            page.locator('#building-affairs-toggle').click()
                            choice(page, 'rebuild')
                            choice(page, page.evaluate('game.pending_event.choices.find(c=>c.id.startsWith("rebuild:")).id'))
                            choice(page, 'leave')
                            assert state(engine._load(g.id)) == held
                            assert balance(engine._load(g.id), 'player') == cash-5600000000
                            # Seed damage on the same isolated original temple, then repair via its real UI.
                            from cultivation_life.system.westward_rules import adopt_merit,credit_merit
                            from cultivation_life.system.economy.ledger import account
                            damaged=engine._load(g.id)
                            damaged.building_state['records'][held['temple_id']]['status']='destroyed'
                            adopt_merit(damaged);credit_merit(damaged,50)
                            account(damaged,'background:celestial')['balance']+=10**8
                            engine.store.save(damaged);before_repair=balance(damaged,'player')
                            page.evaluate('id=>loadGame(id)',g.id);open_westward(page,'地仙庙域')
                            repair=page.evaluate('game.yaochi.relief.offers[0]');assert repair['subsidy']>0
                            with page.expect_response(lambda r:r.url.endswith('/yaochi-action')) as response:
                                click_control(page.locator('[data-finale-action=relief_rebuild]'))
                            assert response.value.status==200
                            page.wait_for_function('!busy && game.yaochi.earth.temple.status==="intact"')
                            assert page.evaluate('game.yaochi.earth.temple.id')==held['temple_id']
                            assert balance(engine._load(g.id),'player')==before_repair-repair['personal']
                            assert page.locator('.temple-portrait img').get_attribute('src').endswith('land-temple-intact-361.png')
                        else:
                            click_control(page.locator('.earth-current .yaochi-exit summary'))
                            click_control(page.locator('[data-earth-action=earth_cancel]'))
                            page.wait_for_function('!busy && !game.yaochi.earth.duty')
                            assert state(engine._load(g.id))['trust'] == 40
                        assert not errors, errors
                        page.close()
                        print(f'{theme} {width}x{height}: actual temple, stale recovery, staged work, event/followup, disabled guards and layout passed', flush=True)
                    browser.close()
            finally:
                http.shutdown(); http.server_close()


if __name__ == '__main__': main()
