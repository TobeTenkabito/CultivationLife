"""Single browser: stale peace rejection, reward recovery and member intelligence."""
import random
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.system.economy.ledger import balance
from test_war_presence_fixes import independent_peace
from test_strategic_war import own_campaign
from scripts.browser_navigation import navigation_locator, click_control


def main():
    with tempfile.TemporaryDirectory(prefix='war-presence-browser-') as folder:
        engine = GameEngine(ROOT, Path(folder)/'saves')
        class Handler(server.Handler):
            def log_message(self, *args): pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(args=['--disable-gpu', '--renderer-process-limit=1', '--js-flags=--max-old-space-size=128'])
                    try:
                        page = browser.new_page(viewport=dict(width=1440, height=960), reduced_motion='reduce')
                        errors = []; page.on('pageerror', lambda e: errors.append(str(e)))
                        page.on('dialog', lambda dialog: dialog.accept())
                        page.goto(f'http://127.0.0.1:{http.server_port}'); page.wait_for_function('!!configData')
                        g, war = independent_peace(engine)
                        engine.store.save(g)
                        page.evaluate('async id=>loadGame(id)', g.id)
                        navigation_locator(page, '[data-panel-target=war]').click()
                        form = page.locator('.war-peace-form')
                        form.wait_for(state='visible')
                        form.locator('select').first.select_option('stones')
                        for width, height in [(1440, 960), (393, 852), (852, 393)]:
                            page.set_viewport_size(dict(width=width, height=height))
                            for theme in 'abdf':
                                page.evaluate('v=>document.documentElement.dataset.theme=v', theme)
                                assert form.evaluate('(n)=>n.scrollWidth<=n.clientWidth+1')
                        # Another page opened an original event after this form rendered.
                        fresh = engine._load(g.id)
                        reward = engine._prepare_treasure_reward_event(fresh, random.Random(22))
                        fresh.pending_event = reward
                        engine.store.save(fresh)
                        before = engine.store._path(g.id).read_bytes()
                        submissions = []
                        page.on('request', lambda r: submissions.append(r.url) if r.method == 'POST' and r.url.endswith('/war-peace') else None)
                        with page.expect_response(lambda r: r.url.endswith('/war-peace')) as response:
                            click_control(form.get_by_role('button', name='以战果提出条件', exact=True))
                        assert response.value.status == 400, response.value.text()
                        page.wait_for_function('(id)=>!busy && game.pending_event?.id===id', arg=reward['id'])
                        assert len(submissions) == 1 and engine.store._path(g.id).read_bytes() == before
                        assert form.count() == 0
                        assert not page.locator('body').evaluate('(n)=>n.classList.contains("busy")')
                        assert page.evaluate('game.war_system.wars.every(w=>!w.player_controls && !w.can_negotiate)')
                        # Claim the unchanged reward through its actual choice button.
                        page.keyboard.press('Escape')
                        click_control(page.locator('#event-choices button').first)
                        page.wait_for_function('!busy && !game.pending_event')
                        ready = engine._load(g.id)
                        original = (balance(ready, 'organization:sect:wanmo'), balance(ready, 'organization:sect:tianjian'))
                        navigation_locator(page, '[data-panel-target=war]').click()
                        form.wait_for(state='visible')
                        form.locator('select').first.select_option('stones')
                        with patch.object(engine, '_vote_probability', return_value=1.):
                            with page.expect_response(lambda r: r.url.endswith('/war-peace')) as response:
                                click_control(form.get_by_role('button', name='以战果提出条件', exact=True))
                        assert response.value.status == 200, response.value.text()
                        page.wait_for_function('!busy && game.war_system.wars.every(w=>w.status==="ended")')
                        saved = engine._load(g.id)
                        paid = original[0] - balance(saved, 'organization:sect:wanmo')
                        assert paid > 0 and balance(saved, 'organization:sect:tianjian') - original[1] == paid
                        assert len(submissions) == 2 and form.count() == 0
                        # The ordinary member's actual GET response and DOM hide the enemy.
                        g, row, child = own_campaign(engine)
                        g.sects['taixuan'].founded_by_player = False
                        g.player.realm_index, g.player.layer = 1, 1
                        engine.store.save(g)
                        page.evaluate('async id=>loadGame(id)', g.id)
                        root = page.locator('#strategic-war-panel')
                        root.get_by_role('tab', name='战役', exact=True).click()
                        root.locator(f'[data-campaign-id="{child["id"]}"]').click()
                        assert page.evaluate('(id)=>game.war_system.strategic.wars[0].campaigns.find(c=>c.id===id).field.defender.supplies===null', child['id'])
                        assert '敌方军需未侦明' in root.locator('.strategy-army-defender').inner_text()
                        assert '军需可支撑' in root.locator('.strategy-army-attacker').inner_text()
                        assert not errors, errors
                        print('War presence UI passed: 12 form layouts; stale peace 400 without payment/retry; original reward; legal peace payment; ordinary-member enemy supply hidden', flush=True)
                    finally: browser.close()
            finally: http.shutdown(); http.server_close(); thread.join(timeout=2)


if __name__ == '__main__': main()
