"""Real page commands for local expansion, work, stale recovery and export."""
import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.system.heavens.outpost_runtime import get
from test_heavens_outposts import frontier, quiet, act, dispatch, wait
from scripts.browser_navigation import navigation_locator


def main():
    output = ROOT / 'build/heavens-development-browser'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        # The first-batch prerequisites use its real command/save protocol.
        # The page below runs the normal engine and actual annual settlement.
        bundle = quiet(frontier.__wrapped__(Path(folder)))
        engine, key, _ = bundle
        act(bundle, 'outpost_authorize'); dispatch(bundle); dispatch(bundle)
        wait(bundle, 16); act(bundle, 'outpost_depart'); wait(bundle, 10)
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)):
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    page = browser.new_page(viewport={'width':1440,'height':1000})
                    page.set_default_timeout(60000)
                    errors, commands = [], []
                    page.on('pageerror', lambda e: errors.append(str(e)))
                    page.on('request', lambda r: commands.append(r.post_data_json) if r.method=='POST' and r.url.endswith('/heavens-command') else None)
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('window.GameThemes && configData')
                    page.evaluate('async id=>loadGame(id)',key)
                    navigation_locator(page,'[data-panel-target=heavens]').click()
                    page.get_by_role('tab',name='诸界',exact=True).click()
                    page.get_by_role('button',name='查看跨界开拓',exact=True).click()
                    page.get_by_role('button',name='查看天剑宗·异界分驻地',exact=True).click()
                    page.get_by_role('tab',name='地方经营',exact=True).click()

                    def command(action, *, stale=False):
                        label='选择开拓事务' if action=='outpost_wait' or action=='outpost_return' else '选择经营事务'
                        page.get_by_label(label,exact=True).select_option(action)
                        seq=page.evaluate('game.heavens.next_command_seq')
                        page.locator(f'[data-heavens-action={action}]').click()
                        page.locator('#game-confirm-backdrop:not(.hidden)').wait_for()
                        if stale:
                            game=engine.store.load(key)
                            engine.heavens_command(key,game.heavens_state['command_seq']+1,game.heavens_state['revision'],'configure',None,{'watch':False})
                        page.locator('#game-confirm-accept').click()
                        page.wait_for_function('seq=>!busy && game.heavens.next_command_seq>=seq+1',arg=seq)

                    command('outpost_develop',stale=True)
                    assert not get(engine.store.load(key),'outpost:tianjian').get('development')
                    assert len([c for c in commands if c['action']=='outpost_develop'])==1
                    command('outpost_develop')
                    assert get(engine.store.load(key),'outpost:tianjian')['development']
                    places=page.evaluate('game.heavens.outposts.find(r=>r.id==="outpost:tianjian").development.locations')
                    place=next(p for p in places if p['id']!='red_marrow_city' and any(a['action']=='outpost_expand' and a['enabled'] for a in p['actions']))
                    page.get_by_label('经营地点',exact=True).select_option(place['id'])
                    command('outpost_expand')
                    assert page.locator('[data-heavens-action=outpost_expand]').is_disabled()
                    row=get(engine.store.load(key),'outpost:tianjian')
                    worker=next(u['person_id'] for u in row['units'] if u.get('local_job'))
                    assert engine.store.load(key).world_npcs[worker].location_id=='red_marrow_city'
                    page.get_by_role('tab',name='授权与往返',exact=True).click()
                    for _ in range(100):
                        row=get(engine.store.load(key),'outpost:tianjian')
                        if next(u for u in row['units'] if u['person_id']==worker)['local_job']['status']!='active': break
                        command('outpost_wait')
                    else: raise AssertionError('Original local worker failed to return')
                    game=engine.store.load(key)
                    assert game.world_npcs[worker].location_id=='red_marrow_city'
                    assert game.intrigue_state['territory']['holdings']['demon'][place['id']]['tianjian']['value']>0
                    page.get_by_role('tab',name='地方经营',exact=True).click()
                    page.get_by_label('经营地点',exact=True).select_option(place['id'])
                    command('outpost_build_site')
                    page.get_by_role('tab',name='授权与往返',exact=True).click()
                    for _ in range(100):
                        row=get(engine.store.load(key),'outpost:tianjian')
                        if next(u for u in row['units'] if u['person_id']==worker)['local_job']['status']!='active': break
                        command('outpost_wait')
                    else: raise AssertionError('Original builder failed to return')
                    game=engine.store.load(key)
                    assert game.intrigue_state['territory']['holdings']['demon'][place['id']]['tianjian']['outpost']
                    page.get_by_role('tab',name='地方经营',exact=True).click()
                    for theme in 'abdf':
                        page.locator('#heavens-toggle').click()
                        page.locator('#theme-open').click()
                        page.locator(f'[data-theme-picker=dialog] [data-theme-choice={theme}]').click()
                        page.evaluate('GameThemes.saved')
                        page.locator('[data-close-dialog=theme-dialog]').click()
                        navigation_locator(page,'[data-panel-target=heavens]').click()
                        for width,height in ((1440,1000),(412,915),(915,412)):
                            page.set_viewport_size({'width':width,'height':height})
                            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                            page.screenshot(path=str(output/f'{theme}-{width}.png'))
                    page.set_viewport_size({'width':1440,'height':1000})
                    page.get_by_label('经营地点',exact=True).select_option('')
                    command('outpost_invest')
                    command('outpost_export')
                    page.get_by_role('tab',name='授权与往返',exact=True).click()
                    for _ in range(8): command('outpost_wait')
                    assert engine.store.load(key).world_npcs[worker].world=='human'
                    command('outpost_return')
                    game=engine.store.load(key);row=get(game,'outpost:tianjian')
                    assert game.player.world=='human' and game.sects['tianjian'].location_id=='wudi_plain'
                    assert next(u for u in row['units'] if u['person_id']==worker)['phase']=='home'
                    assert game.world_npcs[row['governor_id']].world=='demon'
                    assert not errors,errors
                    report=dict(commands=len(commands),original_worker=worker,location=place['id'],
                                expanded=True,built=True,returned=True,themes=4,sizes=3,page_errors=errors)
                    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                    print(json.dumps(report,ensure_ascii=False))
                    browser.close()
            finally:
                httpd.shutdown();httpd.server_close()


if __name__=='__main__': main()
