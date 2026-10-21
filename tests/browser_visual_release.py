"""Actual optional UI, original controls, eleven maps and legacy fallback."""
import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from fixtures.visual_release import prepare_visual_release
from scripts.browser_navigation import navigation_locator,click_control,set_theme


def toggle(page,value):
    for panel in page.locator('.utility-panel.panel-open').all():
        page.locator('#'+panel.get_attribute('id').removesuffix('-card')+'-toggle').click()
    page.locator('#theme-open').click()
    page.locator('#theme-dialog [data-pixel-setting]').set_checked(value)
    page.evaluate('GameThemes.saved')
    page.locator('[data-close-dialog=theme-dialog]').click()


def verify(page,identity,output):
    page.evaluate('id=>loadGame(id)',identity)
    before=page.evaluate('JSON.stringify(game)')
    toggle(page,True)
    page.wait_for_function('!!PixelLibrary.catalog')
    assert page.evaluate('JSON.stringify(game)')==before
    owned_dlc=page.evaluate("configData.extensions.some(e=>e.id==='official.guixu-tide'&&e.status==='loaded')")
    navigation_locator(page,'[data-panel-target=inventory]').click()
    page.locator('[data-pixel-item=guixu_canghai_equipment_01]').click()
    private_art=page.locator('#pixel-inventory>.pixel-bag-detail .pixel-bag-art img')
    private_art.wait_for(state='visible')
    assert private_art.get_attribute('data-asset')==('treasure.guixu_canghai_equipment_01' if owned_dlc else 'gear.other')
    page.wait_for_function("document.querySelector('#pixel-inventory>.pixel-bag-detail .pixel-bag-art img').naturalWidth===32")
    if not owned_dlc:
        assert not page.evaluate("!!PixelLibrary.catalog.items.guixu_canghai_equipment_01")
    page.locator('#inventory-toggle').click()
    for theme in 'abdf':
        set_theme(page,theme)
        for width,height in [(1440,960),(390,844),(320,740)]:
            page.set_viewport_size(dict(width=width,height=height))
            navigation_locator(page,'[data-panel-target=inventory]').click()
            page.locator('#pixel-inventory').wait_for(state='visible')
            assert not page.locator('#inventory-list').is_visible()
            assert page.locator('[data-pixel-item]').count()==page.evaluate('game.player.inventory.length')
            assert page.locator('.pixel-item-quantity').evaluate_all('rows=>rows.every(n=>{const r=n.getBoundingClientRect(),p=n.parentElement.getBoundingClientRect();return r.left>=p.left&&r.right<=p.right;})')
            assert page.locator('#inventory-card').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
            search=page.locator('.pixel-bag-tools input');search.fill('听雨伞')
            assert page.locator('[data-pixel-item]').count()==2
            ids=page.locator('[data-pixel-item]').evaluate_all('rows=>rows.map(n=>n.dataset.pixelItem)')
            assert len(set(ids))==2
            page.locator('[data-pixel-item]').first.click()
            detail=page.locator('.pixel-item-sheet .pixel-bag-detail' if width<=800 else '#pixel-inventory>.pixel-bag-detail')
            detail.locator('.pixel-bag-art img').wait_for(state='visible')
            assert detail.locator('.pixel-bag-art img').get_attribute('data-asset')=='gear.umbrella'
            assert detail.locator('.item').count()==1
            assert detail.evaluate('n=>n.scrollWidth<=n.clientWidth+1')
            page.screenshot(path=str(output/f'bag-{theme}-{width}.png'))
            if width<=800:page.keyboard.press('Escape')
            search.fill('');page.locator('#inventory-toggle').click()
            assert page.evaluate('JSON.stringify(game)')==before
    page.set_viewport_size(dict(width=390,height=844))
    navigation_locator(page,'[data-panel-target=inventory]').click()
    page.locator('[data-pixel-item=healing_pill]').click()
    hp=page.evaluate('game.player.hp');quantity=page.evaluate("game.player.inventory.find(i=>i.id==='healing_pill').quantity")
    page.locator('.pixel-item-sheet .item-use').click()
    page.wait_for_function('!busy && !document.querySelector(".pixel-item-sheet").open')
    assert page.evaluate('game.player.hp')>hp
    assert page.evaluate("game.player.inventory.find(i=>i.id==='healing_pill').quantity")==quantity-1
    page.locator('#inventory-toggle').click()
    navigation_locator(page,'[data-panel-target=natal-artifact]').click()
    assert page.locator('.pixel-natal-art img').get_attribute('data-asset')=='gear.umbrella'
    click_control(page.locator('.natal-slot.slot-0'))
    choice=page.locator('.natal-material-choice').first
    material=choice.get_attribute('data-material-id')
    assert choice.locator('img').count()==1
    click_control(choice)
    page.wait_for_function('id=>!busy&&game.natal_artifact.slots[0].material_id===id',arg=material)
    assert page.locator('.natal-slot.slot-0 img').get_attribute('src')
    click_control(page.locator('.natal-slot.slot-0'))
    page.wait_for_function('!busy&&!game.natal_artifact.slots[0].material_id')
    page.screenshot(path=str(output/'natal-mobile.png'))
    page.locator('#natal-artifact-toggle').click()
    page.locator('.hud-identity').click()
    page.locator('.pixel-natal-on-actor').wait_for(state='visible')
    assert page.locator('.pixel-natal-on-actor').get_attribute('data-asset')=='gear.umbrella'
    page.keyboard.press('Escape')
    for width,height in [(1440,960),(390,844),(320,740),(844,390)]:
        page.set_viewport_size(dict(width=width,height=height))
        page.wait_for_timeout(100)
        page.evaluate('scrollTo(0,0)')
        compact=page.evaluate('document.documentElement.dataset.pixelDrawer==="true"')
        if compact:page.locator('#pixel-scenery-toggle').click()
        else:
            scene=page.locator('.pixel-scene').bounding_box();action=page.locator('#action-card').bounding_box()
            assert scene['x']+scene['width']<=action['x']+1
            assert page.locator('.action-tabs').evaluate("n=>n.getBoundingClientRect().bottom<=document.querySelector('.action-units').getBoundingClientRect().top+1")
        age=page.evaluate('game.player.age')
        with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/building-action')) as response:
            page.locator('#pixel-buildings [data-building-action=enter]:not(:disabled)').first.click()
        assert response.value.ok
        page.wait_for_function('!busy&&!!game.buildings.inside')
        assert not page.locator('#pixel-scenery-drawer').is_visible()
        assert page.locator('#event-card').bounding_box()['height']>=200
        if not compact:
            assert page.locator('#event-card').evaluate("n=>n.closest('.pixel-workbench')!==null")
            assert page.locator('.pixel-scene').is_visible()
        else:
            assert page.locator('#player-hud').bounding_box()['y']<page.locator('#event-card').bounding_box()['y']
        page.screenshot(path=str(output/f'home-event-{width}.png'))
        leave=page.evaluate("game.pending_event.choices.findIndex(c=>c.id==='leave')")
        assert leave>=0
        with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/choice')) as response:
            page.locator('#event-choices button').nth(leave).click()
        assert response.value.ok
        page.wait_for_function('!busy&&!game.buildings.inside')
        assert page.evaluate('game.player.age')==age
    before=page.evaluate('JSON.stringify(game)')
    toggle(page,False)
    navigation_locator(page,'[data-panel-target=inventory]').click()
    assert page.locator('#inventory-list').is_visible()
    assert not page.locator('#pixel-inventory').is_visible()
    assert page.locator('#inventory-list .item').count()==page.evaluate('game.player.inventory.length')
    assert not page.locator('.pixel-item-sheet').is_visible()
    assert page.evaluate('JSON.stringify(game)')==before
    page.locator('#inventory-toggle').click()
    navigation_locator(page,'[data-panel-target=map]').click()
    page.locator('#map-view-tabs [aria-controls=map-atlas]').click()
    assert page.locator('[data-atlas-mode="3d"]').is_visible()
    page.locator('#map-toggle').click()


def main():
    output=ROOT/'build/visual-release-browser';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        identity=engine.create_game('像素验收','heavenly','dao',322,preset_id='core')['id']
        prepare_visual_release(engine,identity)
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch();page=browser.new_page(viewport=dict(width=1440,height=960),reduced_motion='reduce')
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto(f'http://127.0.0.1:{http.server_port}');page.wait_for_function('!!configData');page.evaluate('GameThemes.ready')
                    verify(page,identity,output)
                    toggle(page,True)
                    for world in page.evaluate('Object.keys(PixelLibrary.catalog.maps)'):
                        rank=4 if world in ['human','demon'] else 9 if world in ['celestial','asura','nether','reincarnation'] else 7
                        made=engine.create_game('山河验收','supreme_metal','dao',322,custom_start=dict(world=world,realm_index=rank))
                        page.evaluate('id=>loadGame(id)',made['id'])
                        original=engine.store._path(made['id']).read_bytes()
                        page.set_viewport_size(dict(width=1440,height=960))
                        image=page.locator('#pixel-home .pixel-background');image.wait_for(state='visible')
                        page.wait_for_function('document.querySelector("#pixel-home .pixel-background").naturalWidth===768')
                        assert image.get_attribute('src').endswith('/'+world+'.png')
                        assert page.evaluate('''()=>{const i=document.querySelector('#pixel-home .pixel-background'),c=document.createElement('canvas');c.width=c.height=48;const x=c.getContext('2d');x.drawImage(i,0,0,48,48);return new Set(x.getImageData(0,0,48,48).data).size>80}''')
                        assert image.evaluate("n=>getComputedStyle(n).imageRendering==='pixelated'")
                        previous=page.locator('.pixel-world-plane').get_attribute('style')
                        page.locator('.pixel-world-tools [aria-label=放大绘景]').click()
                        assert page.locator('.pixel-world-plane').get_attribute('style')!=previous
                        assert page.locator('.pixel-world-tools [aria-label=放大绘景]').is_disabled()
                        page.locator('[aria-label=浏览绘景地域]').select_option(index=1)
                        assert page.locator('#pixel-place-name').inner_text()==page.evaluate('game.map.locations[1].name')
                        assert engine.store._path(made['id']).read_bytes()==original
                        page.locator('[aria-label=返回所在地]').click()
                        page.screenshot(path=str(output/f'home-{world}.png'))
                        navigation_locator(page,'[data-panel-target=map]').click()
                        page.locator('#map-view-tabs [aria-controls=map-atlas]').click()
                        assert page.locator('[data-atlas-mode="3d"]').is_visible()
                        assert page.locator('#map-atlas .pixel-background').count()==0
                        assert page.locator('#map-atlas .atlas-viewport').count()==1
                        page.locator('[aria-label=地图地点]').select_option(index=1)
                        filter=page.locator('[aria-label=影响力宗门]')
                        if filter.count() and filter.locator('option').count()>1:
                            filter.select_option(index=1)
                            assert filter.input_value()
                        assert engine.store._path(made['id']).read_bytes()==original
                        page.screenshot(path=str(output/f'map-{world}.png'))
                        page.locator('#map-toggle').click()
                    assert not errors,errors
                    browser.close()
            finally:http.shutdown();http.server_close()
    (output/'result.json').write_text(json.dumps(dict(status='passed',themes=4,worlds=11,widths=[1440,390,320],real_commands=['healing','socket','unsocket'],legacy=True)),encoding='utf-8')
    print('Visual release: four themes, three widths, true inventory/natal, eleven maps and legacy fallback passed')


if __name__=='__main__':main()
