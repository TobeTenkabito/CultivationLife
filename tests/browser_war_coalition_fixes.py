"""One small browser: real idle transfer and stale in-war candidate recovery."""
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
from cultivation_life.engine.composition.strategic_war import bind
from test_war_coalition_fixes import idle_vassal
from scripts.browser_navigation import navigation_locator, click_control


def main():
    with tempfile.TemporaryDirectory(prefix='coalition-fixes-browser-') as directory:
        engine = GameEngine(ROOT, Path(directory)/'saves')
        class Handler(server.Handler):
            def log_message(self, *args): pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(directory)):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(args=['--disable-gpu', '--renderer-process-limit=1', '--js-flags=--max-old-space-size=128'])
                    try:
                        page = browser.new_page(viewport=dict(width=1440, height=960), reduced_motion='reduce')
                        errors = []; page.on('pageerror', lambda e: errors.append(str(e)))
                        page.goto(f'http://127.0.0.1:{http.server_port}')
                        page.wait_for_function('!!configData')
                        g, source, person, _ = idle_vassal(engine)
                        place = (person.world, person.location_id)
                        engine.store.save(g)
                        page.evaluate('async id=>loadGame(id)', g.id)
                        navigation_locator(page, '[data-panel-target=faction]').click()
                        form = page.locator('form.governance-form').filter(has_text=f'从{source.name}调遣外援')
                        form.wait_for(state='visible')
                        form.get_by_role('combobox').select_option(person.id)
                        for width, height in [(1440, 960), (393, 852), (852, 393)]:
                            page.set_viewport_size(dict(width=width, height=height))
                            for theme in 'abdf':
                                page.evaluate('(theme)=>document.documentElement.dataset.theme=theme', theme)
                                assert form.evaluate('(n)=>n.scrollWidth<=n.clientWidth+1')
                        # The old visible candidate becomes occupied in a real original war.
                        fresh = engine._load(g.id)
                        enemy = next(o for o in fresh.sects.values() if o.world == fresh.player.world and o.id not in {source.id, 'taixuan'} and not o.extinct and o.kind == 'sect')
                        war = engine._start_war(fresh, 'sect', source.id, enemy.id, initiated_by_player=True)
                        engine.store.save(fresh)
                        before = engine.store._path(g.id).read_bytes()
                        with page.expect_response(lambda r: r.url.endswith('/vassal-transfer')) as response:
                            click_control(form.get_by_role('button', name='执行调动', exact=True))
                        assert response.value.status == 400, response.value.text()
                        page.wait_for_function('!busy')
                        assert engine.store._path(g.id).read_bytes() == before
                        assert form.count() == 0
                        assert not page.locator('body').evaluate('(n)=>n.classList.contains("busy")')
                        # The same original person may transfer after the real war settles.
                        fresh = engine._load(g.id)
                        actual = next(w for w in fresh.wars if w['id'] == war['id'])
                        engine._conclude_war(fresh, actual, 'white_peace', 'attacker', automatic=True)
                        engine.store.save(fresh)
                        page.evaluate('async id=>loadGame(id)', g.id)
                        form.wait_for(state='visible')
                        form.get_by_role('combobox').select_option(person.id)
                        with page.expect_response(lambda r: r.url.endswith('/vassal-transfer')) as response:
                            click_control(form.get_by_role('button', name='执行调动', exact=True))
                        assert response.value.status == 200, response.value.text()
                        page.wait_for_function('!busy')
                        saved = engine._load(g.id)
                        actual = bind(engine).find_person(saved, person.id)
                        assert actual.faction_id == 'taixuan' and (actual.world, actual.location_id) == place
                        assert not any(n.id == person.id for n in saved.sects[source.id].npcs)
                        assert not errors, errors
                        print('Coalition fixes browser passed: four themes x three sizes; stale transfer 400 and refresh; busy released; real idle transfer with original identity and location', flush=True)
                    finally: browser.close()
            finally: http.shutdown(); http.server_close(); thread.join(timeout=2)


if __name__ == '__main__': main()
