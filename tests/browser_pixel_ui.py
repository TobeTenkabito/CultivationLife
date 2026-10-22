"""Real loading, appearance switching, canvas, original actions and stale events."""
import json
import hashlib
import random
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from test_pixel_assets import STATIC_REDRAWS


def verify_details(page, output, gender, width, height, path='dao'):
    page.set_viewport_size({'width':width, 'height':height})
    page.wait_for_timeout(100)
    before = page.evaluate('JSON.stringify(game)')
    page.evaluate("window.__techniqueList=document.querySelector('#technique-list')")
    page.locator('.hud-identity').click()
    page.locator('.pixel-details-art').wait_for(state='visible')
    canvas = page.locator('.pixel-details-art canvas')
    assert canvas.get_attribute('data-actor') == f'actor.human.{path}.{gender}'
    assert f'{path}-{gender}-static-portrait.png' in page.locator('.pixel-portrait').get_attribute('src')
    assert page.locator('.pixel-portrait').evaluate('i=>i.naturalWidth===128&&i.naturalHeight===128')
    assert canvas.evaluate('c=>c.width===256&&c.height===288')
    for kind in ('figure','portrait'):
        src=page.evaluate("id=>{const c=PixelAssetCatalog;return c.base+c.assets[id].file}",f'actor.human.{path}.{gender}.{kind}')
        response=page.request.get(urljoin(page.url,src))
        assert response.ok
        assert hashlib.sha256(response.body()).hexdigest()==STATIC_REDRAWS[f'{path}.{gender}.{kind}']
    assert canvas.evaluate('''c => c.getContext('2d').getImageData(0,0,c.width,c.height).data.filter((v,i)=>i%4===3&&v>0).length>500''')
    assert canvas.evaluate('''async c => {
      const bitmap=await VisualAssets.load(c.dataset.actor+'.figure');
      const expected=document.createElement('canvas');expected.width=256;expected.height=288;
      expected.getContext('2d').drawImage(bitmap,0,0);
      const a=c.getContext('2d').getImageData(0,0,c.width,c.height).data;
      const b=expected.getContext('2d').getImageData(0,0,c.width,c.height).data;
      return a.every((value,i)=>value===b[i]);
    }''')
    figure = page.locator('.pixel-details-art').bounding_box()
    data = page.locator('#player-details-content .character-card').bounding_box()
    summary = page.locator('.pixel-character-summary').bounding_box()
    realm = page.locator('.pixel-character-summary>.realm').bounding_box()
    heading = page.locator('.pixel-character-summary>.character-head').bounding_box()
    resources = page.locator('#player-details-content .character-card>.meter-block').first.bounding_box()
    assert figure['x'] >= realm['x'] + realm['width']
    assert figure['x'] >= heading['x'] + heading['width']
    assert resources['y'] >= summary['y'] + summary['height']
    assert abs(resources['width'] - data['width']) <= 1
    assert canvas.evaluate('''c => {
      const pixels=c.getContext('2d').getImageData(0,0,c.width,c.height).data;
      const r=c.getBoundingClientRect(),f=c.parentElement.getBoundingClientRect();
      for(let y=0;y<c.height;y++)for(let x=0;x<c.width;x++)if(pixels[(y*c.width+x)*4+3]){
        if(r.left+x*r.width/c.width<f.left-1 || r.left+(x+1)*r.width/c.width>f.right+1 ||
           r.top+y*r.height/c.height<f.top-1 || r.top+(y+1)*r.height/c.height>f.bottom+1)return false;
      }return true;
    }''')
    assert page.locator('#player-details-dialog').evaluate('(d) => d.scrollWidth <= d.clientWidth + 1')
    assert page.evaluate("window.__techniqueList===document.querySelector('#technique-list')")
    assert page.evaluate('JSON.stringify(game)') == before
    page.screenshot(path=str(output / f'details-{path}-{gender}-{width}.png'))
    page.keyboard.press('Escape')


def main():
    output = ROOT / 'build/pixel-ui'
    output.mkdir(parents=True, exist_ok=True)
    results = {'viewports': [], 'performance_ms': {}}
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        engine = GameEngine(ROOT, root / 'saves')
        male = engine.create_game('沈清和', 'heavenly', 'dao', 137, preset_id='core')['id']
        female = engine.create_game('云知微', 'heavenly', 'dao', 138, preset_id='core', gender='female')['id']
        demonic = {gender: engine.create_game('魔修立绘' + gender, 'heavenly', 'demonic', 139,
                                             preset_id='demonic_core', gender=gender)['id']
                   for gender in ('male', 'female')}
        class Handler(server.Handler):
            def log_message(self, *args):
                pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', root):
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    page = browser.new_page(viewport={'width':1440, 'height':960})
                    errors, requests, submits = [], [], []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.on('request', lambda req: requests.append((req.method, req.url)))
                    page.on('request', lambda req: submits.append(req.post_data_json)
                            if req.method == 'POST' and req.url.endswith('/choice') else None)
                    url = f'http://127.0.0.1:{httpd.server_port}'
                    page.goto(url)
                    page.wait_for_function('window.GameThemes && configData && window.PixelHome')
                    page.evaluate('GameThemes.ready')
                    page.evaluate('async id => loadGame(id)', male)
                    assert not any('/assets/pixel/v1/' in path and path.endswith('.png') for _, path in requests)
                    before = engine.store._path(male).read_bytes()
                    original = page.evaluate('JSON.stringify(game)')
                    page.evaluate("window.__originalCultivate=document.querySelector('#cultivate-action');window.__originalMerchant=document.querySelector('#merchant-card')")

                    def toggle(value):
                        page.locator('#theme-open').click()
                        page.locator('#theme-dialog [data-pixel-setting]').set_checked(value)
                        page.evaluate('GameThemes.saved')
                        page.locator('[data-close-dialog=theme-dialog]').click()

                    toggle(True)
                    page.wait_for_function("!document.querySelector('.pixel-portrait').hidden")
                    assert page.locator('#pixel-home canvas').count() == 0
                    assert page.evaluate('''async () => {const image=await VisualAssets.load('actor.human.dao.male.atlas'),c=document.createElement('canvas');c.width=c.height=96;VisualAssets.frame(c.getContext('2d'),image,'idle_s');const p=c.getContext('2d').getImageData(0,0,96,96).data;return p.filter((v,i)=>i%4===3&&v>0).length>500}''')
                    assert page.evaluate('''() => {const img=document.querySelector('.pixel-background'),c=document.createElement('canvas');c.width=64;c.height=32;const x=c.getContext('2d');x.drawImage(img,0,0,64,32);const p=x.getImageData(0,0,64,32).data;return new Set(Array.from({length:2048},(_,i)=>p.slice(i*4,i*4+3).join(','))).size>100}''')
                    page.evaluate("document.querySelector('#action-units').value=3;document.querySelector('#action-units').dispatchEvent(new Event('change'))")
                    page.evaluate("window.__originalScenery=document.querySelector('#pixel-home')")
                    for theme in 'abdf':
                        page.locator('#theme-open').click()
                        page.locator(f'[data-theme-picker=dialog] [data-theme-choice={theme}]').click()
                        page.evaluate('GameThemes.saved')
                        page.keyboard.press('Escape')
                        for width, height in [(1440, 960), (390, 844), (320, 740)]:
                            page.set_viewport_size({'width':width, 'height':height})
                            page.wait_for_timeout(100)
                            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), (theme, width)
                            assert page.locator('#hud-hp').is_visible()
                            assert page.locator('#player-hud').bounding_box()['height'] < 250, (theme, width)
                            assert page.locator('#cultivate-action').is_visible()
                            assert page.evaluate('document.querySelectorAll("#cultivate-action").length === 1')
                            assert page.locator('#action-units').input_value() == '3'
                            if width < 800:
                                page.evaluate('scrollTo(0,0)')
                                rect = page.locator('#cultivate-action').bounding_box()
                                assert rect['y'] + rect['height'] < height - 70, (theme, rect)
                                assert not page.locator('.pixel-scene').is_visible()
                                assert not page.locator('#pixel-scenery-drawer').is_visible()
                            if width < 800:
                                assert page.evaluate('''() => [...document.querySelectorAll('#navigation-bar button')].every(b => {const p=b.getBoundingClientRect(),s=b.querySelector('small').getBoundingClientRect();return s.left>=p.left && s.right<=p.right && s.height<20})''')
                            for tab in ['living', 'combat', 'daily']:
                                page.locator(f'[data-action-tab={tab}]').click()
                                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                            page.evaluate('scrollTo(0,0)')
                            page.screenshot(path=str(output / f'{theme}-{width}.png'))
                            if width < 800:
                                page.locator('#pixel-scenery-toggle').click()
                                page.locator('#pixel-scenery-drawer').wait_for(state='visible')
                                page.wait_for_function("!document.querySelector('.pixel-background').hidden")
                                assert page.locator('#pixel-scenery-drawer').bounding_box()['x'] == 0
                                assert page.evaluate("window.__originalScenery===document.querySelector('#pixel-home')")
                                page.screenshot(path=str(output / f'{theme}-{width}-drawer.png'))
                                page.keyboard.press('Escape')
                                assert page.locator('#pixel-scenery-toggle').get_attribute('aria-expanded') == 'false'
                                assert page.locator('#pixel-scenery-toggle').evaluate('(node) => node===document.activeElement')
                            results['viewports'].append([theme, width, height])
                    assert page.evaluate('window.__originalCultivate===document.querySelector("#cultivate-action") && window.__originalMerchant===document.querySelector("#merchant-card")')
                    assert engine.store._path(male).read_bytes() == before
                    assert page.evaluate('JSON.stringify(game)') == original
                    page.locator('#pixel-scenery-toggle').click()
                    page.locator('#pixel-open-map').click()
                    assert not page.locator('#pixel-scenery-drawer').is_visible()
                    page.locator('#map-card').wait_for(state='visible')
                    page.keyboard.press('Escape')
                    page.locator('#pixel-scenery-toggle').click()
                    page.set_viewport_size({'width':1440, 'height':960})
                    page.wait_for_function("document.querySelector('#pixel-home').parentElement.classList.contains('theme-play-area')")
                    assert not page.locator('#pixel-scenery-drawer').is_visible()
                    assert page.locator('.pixel-scene').is_visible()
                    assert page.evaluate("window.__originalScenery===document.querySelector('#pixel-home')")
                    for width, height in [(1440,960),(390,844),(320,740)]:
                        verify_details(page, output, 'male', width, height)
                    # Compare the existing render path, including forced layout, on this same game.
                    page.set_viewport_size({'width':1440, 'height':960})
                    for enabled in [True, False]:
                        toggle(enabled)
                        samples = page.evaluate('''() => {const rows=[];for(let i=0;i<12;i++){const t=performance.now();render(game);void document.body.offsetHeight;rows.push(performance.now()-t);}return rows.slice(2).sort((a,b)=>a-b)}''')
                        results['performance_ms']['pixel' if enabled else 'text'] = {'median':samples[len(samples)//2], 'samples':samples}
                    assert page.evaluate('window.__originalCultivate===document.querySelector("#cultivate-action")')
                    assert not page.locator('.pixel-scene').is_visible()
                    assert not page.locator('#player-details-content').evaluate('(node) => node.classList.contains("has-pixel-figure")')
                    toggle(True)
                    page.evaluate('async id => loadGame(id)', female)
                    page.wait_for_function("document.querySelector('.pixel-portrait').src.includes('female') && !document.querySelector('.pixel-portrait').hidden")
                    assert not any('dao-female-atlas.png' in path for _, path in requests)
                    for width, height in [(1440,960),(390,844),(320,740)]:
                        verify_details(page, output, 'female', width, height)
                    page.set_viewport_size({'width':390, 'height':844})
                    page.evaluate('scrollTo(0,0)')
                    page.screenshot(path=str(output / 'female-390.png'))
                    # Real demonic saves use their own selected portrait and idle pixels.
                    for gender, identity in demonic.items():
                        page.evaluate('async id => loadGame(id)', identity)
                        assert page.evaluate('game.player.path') == 'demonic'
                        page.wait_for_function("gender => !document.querySelector('.pixel-portrait').hidden && document.querySelector('.pixel-portrait').src.includes('demonic-'+gender)", arg=gender)
                        saved = engine.store._path(identity).read_bytes()
                        for theme in 'abdf':
                            page.locator('#theme-open').click()
                            page.locator(f'[data-theme-picker=dialog] [data-theme-choice={theme}]').click()
                            page.evaluate('GameThemes.saved')
                            page.locator('[data-close-dialog=theme-dialog]').click()
                            for width, height in [(1440,960),(390,844),(320,740)]:
                                verify_details(page, output, gender, width, height, 'demonic')
                        assert engine.store._path(identity).read_bytes() == saved
                        toggle(False)
                        assert not page.locator('.pixel-portrait').is_visible()
                        toggle(True)
                        page.wait_for_function("!document.querySelector('.pixel-portrait').hidden")
                        assert page.evaluate('''() => {
                          const p=game.player,a=VisualAssets.actor;
                          return a({...p,ghost_attachment:{id:'vessel'}})===null &&
                            a({...p,ghost_host_body:{id:'host'}})===null &&
                            a({...p,race:'monster'})===null && a({...p,gender:'unknown'})===null &&
                            a({...p,lineage_race:'monster'})===null &&
                            a({...p,transformation_technique:{id:'book'},transformation_loadouts:{book:{active:['bird']}}})===null;
                        }''')
                    page.evaluate('async id => loadGame(id)', female)
                    page.wait_for_function("!document.querySelector('.pixel-portrait').hidden && document.querySelector('.pixel-portrait').src.includes('dao-female')")
                    assert page.evaluate('''() => {
                      const p=game.player,a=VisualAssets.actor;
                      return a({...p,race:'unknown'})===null && a({...p,gender:'unknown'})===null &&
                        a({...p,path:'monster'})===null && a({...p,ghost_host_body:{id:'host'}})===null &&
                        a({...p,lineage_race:'monster'})===null &&
                        a({...p,transformation_technique:{id:'book'},transformation_loadouts:{book:{active:['bird']}}})===null;
                    }''')
                    page.evaluate("() => {const d=structuredClone(game);d.player.world='unknown';d.player.world_name='未知界面';d.player.race='unknown';PixelHome.render(d)}")
                    page.wait_for_function("document.querySelector('.pixel-background').hidden && document.querySelector('.pixel-portrait').hidden")
                    assert page.locator('#pixel-world').inner_text() == '未知界面'
                    assert page.locator('#pixel-home').get_attribute('data-art') == 'text'
                    page.locator('.hud-identity').click()
                    assert not page.locator('.pixel-details-art').is_visible()
                    assert page.locator('#avatar').is_visible()
                    page.keyboard.press('Escape')
                    page.evaluate('render(game)')
                    page.evaluate("() => {const d=structuredClone(game);d.player.name='司徒长风临江听雨问道真人';d.player.hp=1;d.player.max_hp=1000000000000;GameThemes.render(d)}")
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                    assert page.locator('#player-hud').bounding_box()['height'] < 300
                    assert '1,000,000,000,000' in page.locator('#hud-hp').get_attribute('title')
                    page.evaluate('render(game)')
                    # Actual game action still goes through the original button and endpoint.
                    old_age = page.evaluate('game.player.age')
                    page.locator('#cultivate-action').click()
                    page.wait_for_function('(age) => !busy && game.player.age > age', arg=old_age)
                    if page.evaluate('!!game.pending_event'):
                        page.locator('#event-choices button:not(:disabled)').first.click()
                        page.wait_for_function('!busy')
                    # Real loading/submission of a stale page, followed by the current reward.
                    current = engine.store.load(female)
                    current.pending_event = engine._instantiate_event(engine.events_by_id['EVT_SECT_FIRST_WARNING_001'], current, random.Random(1))
                    engine.store.save(current)
                    page.evaluate('async id => loadGame(id)', female)
                    assert page.locator('#event-card').is_visible()
                    assert page.locator('#pixel-scenery-toggle').is_disabled()
                    assert not page.locator('.pixel-scene').is_visible()
                    current = engine.store.load(female)
                    reward = engine._prepare_treasure_reward_event(current, random.Random(2))
                    current.pending_event = reward
                    engine.store.save(current)
                    before = engine.store._path(female).read_bytes()
                    count = len(submits)
                    page.locator('#event-choices button').first.click()
                    page.wait_for_function('(id) => !busy && game.pending_event?.id === id', arg=reward['id'])
                    assert len(submits) == count + 1
                    assert engine.store._path(female).read_bytes() == before
                    page.locator('#event-choices button:not(:disabled)').first.click()
                    page.wait_for_function('!busy && !game.pending_event')
                    assert page.locator('#action-card').is_visible()
                    assert not page.locator('.pixel-scene').is_visible()
                    assert page.locator('#pixel-scenery-toggle').is_enabled()
                    page.emulate_media(reduced_motion='reduce')
                    snapshot = page.evaluate('JSON.stringify(game)')
                    count = len(requests)
                    page.wait_for_timeout(1200)
                    assert page.evaluate('JSON.stringify(game)') == snapshot
                    assert len(requests) == count
                    fresh = browser.new_page()
                    fresh.goto(url)
                    fresh.wait_for_function('window.GameThemes')
                    fresh.evaluate('GameThemes.ready')
                    assert fresh.locator('html').get_attribute('data-visual') == 'pixel'
                    broken = browser.new_page(viewport={'width':390, 'height':844}, reduced_motion='reduce',
                                              user_agent='Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36')
                    broken.on('pageerror', lambda error: errors.append(str(error)))
                    broken.route('**/assets/pixel/v1/*.png', lambda route: route.abort())
                    broken.goto(url)
                    broken.wait_for_function('window.GameThemes && configData')
                    broken.evaluate('GameThemes.ready')
                    broken.evaluate('async id => loadGame(id)', male)
                    assert broken.evaluate("VisualAssets.load('scene.human.reverie')") is None
                    assert not broken.locator('.pixel-background').is_visible()
                    assert broken.locator('#pixel-home').get_attribute('data-art') == 'text'
                    assert broken.locator('#cultivate-action').is_visible()
                    broken.locator('.hud-identity').click()
                    assert broken.evaluate("VisualAssets.load('actor.human.dao.male.atlas')") is None
                    assert not broken.locator('.pixel-details-art').is_visible()
                    assert broken.locator('#avatar').is_visible()
                    broken.keyboard.press('Escape')
                    for gender, identity in demonic.items():
                        broken.evaluate('async id => loadGame(id)', identity)
                        broken.locator('.hud-identity').click()
                        assert broken.evaluate(f"VisualAssets.load('actor.human.demonic.{gender}.atlas')") is None
                        assert broken.evaluate(f"VisualAssets.load('actor.human.demonic.{gender}.portrait')") is None
                        assert not broken.locator('.pixel-details-art').is_visible()
                        assert not broken.locator('.pixel-portrait').is_visible()
                        assert broken.locator('#avatar').is_visible()
                        broken.keyboard.press('Escape')
                    broken.screenshot(path=str(output / 'missing-assets-android-390.png'))
                    assert broken.evaluate('document.documentElement.dataset.pixelDrawer') == 'true'
                    broken.set_viewport_size({'width':1100, 'height':620})
                    broken.wait_for_timeout(100)
                    assert broken.evaluate('document.documentElement.dataset.pixelDrawer') == 'true'
                    assert not broken.locator('.pixel-scene').is_visible()
                    assert broken.locator('#cultivate-action').bounding_box()['y'] < 400
                    broken.locator('#pixel-scenery-toggle').click()
                    assert broken.locator('#pixel-scenery-drawer').is_visible()
                    broken.screenshot(path=str(output / 'missing-assets-android-landscape-drawer.png'))
                    broken.keyboard.press('Escape')
                    android = browser.new_page(viewport={'width':1100, 'height':620}, user_agent=broken.evaluate('navigator.userAgent'))
                    android.on('pageerror', lambda error: errors.append(str(error)))
                    android.goto(url)
                    android.wait_for_function('window.GameThemes && configData')
                    android.evaluate('GameThemes.ready')
                    android.evaluate('async id => loadGame(id)', male)
                    assert android.evaluate('document.documentElement.dataset.pixelDrawer') == 'true'
                    assert not android.locator('.pixel-scene').is_visible()
                    assert android.locator('#cultivate-action').bounding_box()['y'] < 400
                    android.screenshot(path=str(output / 'android-landscape-main.png'))
                    android.locator('#pixel-scenery-toggle').click()
                    android.wait_for_function("!document.querySelector('.pixel-background').hidden")
                    android.screenshot(path=str(output / 'android-landscape-drawer.png'))
                    android.keyboard.press('Escape')
                    missing_catalog = browser.new_page(viewport={'width':390, 'height':844})
                    missing_catalog.on('pageerror', lambda error: errors.append(str(error)))
                    missing_catalog.route('**/assets/pixel/v1/catalog.js*', lambda route: route.abort())
                    missing_catalog.goto(url)
                    missing_catalog.wait_for_function('window.GameThemes && configData')
                    missing_catalog.evaluate('GameThemes.ready')
                    missing_catalog.evaluate('async id => loadGame(id)', male)
                    assert missing_catalog.evaluate("VisualAssets.load('scene.human.reverie')") is None
                    assert missing_catalog.evaluate("VisualAssets.load('constructor')") is None
                    assert missing_catalog.locator('#cultivate-action').is_visible()
                    assert not errors, errors
                    browser.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
    (output / 'checks.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print('Pixel UI: four themes, 320/390/1440, real actions/events, canvas, fallback, state isolation and persistence passed')
    print(json.dumps(results['performance_ms']))


if __name__ == '__main__':
    main()
