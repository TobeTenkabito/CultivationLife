"""Six themes and three viewports: real acquisition, training, selection and energy."""
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.rules import opportunity_required, max_hp, max_mp, add_item
from cultivation_life.system.upper_institutions import definition, account


class Quiet(server.Handler):
    def log_message(self, *args):
        pass


from scripts.browser_navigation import navigation_locator

def main():
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
        server.PERSISTENCE_ROOT = Path(folder)
        e = server.ENGINE = GameEngine(ROOT, Path(folder)/'saves')
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        errors = []
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                page = browser.new_page()
                page.emulate_media(reduced_motion='reduce')
                page.on('pageerror', lambda err: errors.append(str(err)))
                page.route('**/merchant-preview', lambda route: route.fulfill(status=400, content_type='application/json', body='{"error":"Isolated test"}'))
                page.goto(f'http://127.0.0.1:{httpd.server_port}')
                page.wait_for_function('configData!==null')
                assert page.evaluate('configData.extensions.length>0&&configData.extensions.every(e=>e.status==="loaded")')
                for world, path, title in [('asura','demonic','魔域'), ('nether','monster','幽域'), ('reincarnation','ghost','轮域')]:
                    g = e._load(e.create_game('本界修域', 'supreme_metal', 'dao', 1522, preset_id='true_immortal')['id'])
                    p = g.player
                    p.world, p.path = world, path
                    p.location_id = e.maps.normalize_location(world, None)
                    p.opportunity = opportunity_required(p)
                    p.hp, p.mp = max_hp(p), max_mp(p)
                    p.immortal_aperture['current'] = 0
                    add_item(p, 'spirit_stone', 1000000)
                    g.pending_event = None
                    g.heavenly_court['open_election'] = None
                    e.store.save(g)
                    page.wait_for_function('!busy')
                    page.evaluate('(id)=>loadGame(id)', g.id)
                    navigation_locator(page,'[data-panel-target="upper-voisinage"]').click()
                    assert page.locator('#upper-voisinage-card h2').inner_text() == title
                    rows = page.locator('#upper-voisinage-content details')
                    rows.first.locator('summary').click()
                    rows.first.get_by_role('button', name='领悟并开域', exact=True).click()
                    page.wait_for_function('!busy&&game.upper_voisinages.rows[0].level===1')
                    rows.first.get_by_role('button', name='培养下一层', exact=True).click()
                    page.wait_for_function('!busy&&game.upper_voisinages.rows[0].level===2')
                    rows.nth(1).locator('summary').click()
                    rows.nth(1).get_by_role('button', name='领悟并开域', exact=True).click()
                    page.wait_for_function('!busy&&game.upper_voisinages.rows[1].level===1')
                    rows.nth(1).get_by_role('button', name='选为斗法邻域', exact=True).click()
                    page.wait_for_function('!busy&&game.upper_voisinages.rows[1].active')
                    saved=e._load(g.id)
                    saved.player.location_id=definition(saved)['location']
                    e.store.save(saved)
                    page.wait_for_function('!busy')
                    page.evaluate('(id)=>loadGame(id)',g.id)
                    navigation_locator(page,'[data-panel-target="upper-institution"]').click()
                    page.locator('[data-section=identity] summary').click()
                    page.locator('[data-section=identity] button').first.click()
                    page.wait_for_function('!busy&&game.upper_institution.joined')
                    page.locator('[data-section=jobs] summary').click()
                    page.get_by_role('button',name='接取委托',exact=True).click()
                    page.wait_for_function('!busy&&game.upper_institution.job!==null')
                    saved=e._load(g.id)
                    state=account(saved)
                    state['job']['progress']=state['job']['years']
                    state.update(merit=2000,earned=2000,rank=2,regard=100)
                    if world=='nether':
                        state['support']=[80]*5
                        saved.player.realm_index=10
                    e.store.save(saved)
                    page.wait_for_function('!busy')
                    page.evaluate('(id)=>loadGame(id)',g.id)
                    page.evaluate("UtilityPanels.open('upper-institution')")
                    page.get_by_role('button',name='交付领取',exact=True).click()
                    page.wait_for_function('!busy&&game.upper_institution.job===null')
                    if world=='nether':
                        page.locator('[data-section=council] summary').click()
                        page.get_by_role('button',name='请求门阀授席',exact=True).click()
                        page.wait_for_function('!busy&&game.upper_institution.seat_active')
                    elif world=='reincarnation':
                        page.locator('[data-section=rites] summary').click()
                        page.get_by_role('button',name='立下济度誓愿',exact=True).click()
                        page.wait_for_function('!busy&&game.upper_institution.obligation!==null')
                        page.get_by_role('button',name='举行祭仪 · 100 功勋',exact=True).click()
                        page.wait_for_function('!busy&&game.upper_institution.blessing_until>game.upper_institution.unit')
                    page.locator('[data-section=politics] summary').click()
                    page.locator('[data-section=politics] button').first.click()
                    page.wait_for_function("!busy&&game.upper_institution.policy==='war'")
                    for theme in 'abdf':
                        page.evaluate('(t)=>document.querySelector(`[data-theme-picker=dialog] [data-theme-choice=${t}]`).click()', theme)
                        page.evaluate('GameThemes.saved')
                        for width, height in [(1440,1080), (412,915), (915,412)]:
                            page.set_viewport_size(dict(width=width, height=height))
                            for panel in ['upper-voisinage', 'immortal-aperture','upper-institution']:
                                page.evaluate('(p)=>UtilityPanels.open(p)', panel)
                                assert page.locator(f'#{panel}-card').evaluate('e=>e.scrollWidth<=e.clientWidth+1'), (world,theme,width,panel)
                            if width == 412:
                                page.evaluate("UtilityPanels.open('upper-voisinage')")
                                page.screenshot(path=str(ROOT/f'build/upper-voisinage-{world}-{theme}.png'))
                                page.evaluate("UtilityPanels.open('upper-institution')")
                                page.screenshot(path=str(ROOT/f'build/upper-institution-{world}-{theme}.png'))
                    page.evaluate("UtilityPanels.open('immortal-aperture')")
                    page.locator('#immortal-aperture-content button').first.click()
                    page.wait_for_function('!busy&&game.aperture.current>0')
                    saved = e._load(g.id)
                    assert saved.player.world_voisinages[world]['active'] == page.evaluate('game.upper_voisinages.rows[1].id')
                    assert saved.player.immortal_aperture['current'] > 0
                    saved.player.world = 'spirit'
                    saved.player.location_id = e.maps.normalize_location('spirit', None)
                    e.store.save(saved)
                    page.wait_for_function('!busy')
                    page.evaluate('(id)=>loadGame(id)', g.id)
                    assert page.locator('[data-panel-target="upper-voisinage"]').is_hidden()
                    assert page.locator('[data-panel-target="upper-institution"]').is_hidden()
                    saved = e._load(g.id)
                    saved.player.world = world
                    saved.player.location_id = e.maps.normalize_location(world, None)
                    e.store.save(saved)
                    page.wait_for_function('!busy')
                    page.evaluate('(id)=>loadGame(id)', g.id)
                    page.wait_for_function('(w)=>!busy&&game.player.world===w&&game.upper_voisinages.available',arg=world)
                    assert page.evaluate('game.upper_voisinages.rows[0].level===2&&game.upper_voisinages.rows[1].active')
                chapters = page.evaluate('TutorialHandbook.build(configData,game)')
                assert 'upper-voisinages' in {c['id'] for c in chapters}
                assert 'upper-institutions' in {c['id'] for c in chapters}
                assert not errors, errors
                browser.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
    print('Upper voisinage and institutions UI passed: three worlds, four themes, three viewports, acquisition/training/selection/refinement, membership, claims, monarchy petitions, oligarchic unequal votes, religious vows/rites, crossing persistence and handbook')


if __name__ == '__main__':
    main()
