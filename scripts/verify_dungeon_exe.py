"""Final executable dungeon commands, real loot buttons and battle overlay."""
import runpy
from pathlib import Path
from playwright.sync_api import sync_playwright
from scripts.browser_navigation import navigation_locator,click_control,set_theme

ROOT=Path(__file__).resolve().parents[1]


def verify_dungeons(base,with_dlc,folder):
    from cultivation_life.engine import GameEngine
    fixture=runpy.run_path(str(ROOT/'tests/fixtures/dungeon_release.py'))
    engine=GameEngine(ROOT,folder/'data/saves')
    with sync_playwright() as pw:
        browser=pw.chromium.launch()
        for palette,width,height in [('light',1440,960),('dark',393,852)]:
            page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce')
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(base);page.wait_for_function('!!configData&&!busy')
            response=page.request.post(base+'/api/games',data=dict(name='探境成品验收',path='dao',spirit_root='heavenly',seed=342,preset_id='core'))
            assert response.ok;identity=response.json()['id']
            fixture['prepare_dungeon_player'](engine,identity)
            page.evaluate('async id=>loadGame(id)',identity);set_theme(page,palette)
            click_control(page.locator('[data-action-tab=living]'));click_control(page.locator('[data-action=treasure]'))
            click_control(page.locator('[data-dungeon-action=discover]'));page.wait_for_function('!busy&&game.dungeons.used===1')
            loot=fixture['prepare_dungeon_loot'](engine,identity)
            page.evaluate('async id=>loadGame(id)',identity)
            click_control(page.locator('[data-dungeon-action=enter]'));page.wait_for_function('!busy&&game.dungeons.active')
            for _ in range(3):click_control(page.locator('[data-choice=seize]'));page.wait_for_function('!busy')
            fixture['prepare_dungeon_fight'](engine,identity)
            page.evaluate('async id=>loadGame(id)',identity)
            click_control(page.locator('[data-choice=fight]'));page.wait_for_function('!busy&&!!game.last_combat_report')
            close=page.locator('#battle-report-toggle');close.wait_for(state='visible')
            assert close.evaluate('n=>{const r=n.getBoundingClientRect();return n.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));}')
            click_control(close)
            click_control(page.locator('[data-dungeon-action=exit]'));page.wait_for_function('!busy&&!game.dungeons.active')
            page.keyboard.press('Escape');navigation_locator(page,'[data-panel-target=inventory]').click()
            for kind,item in [('pill',loot['pill']),('book','MANUAL_DUNGEON_'+loot['book'])]:
                click_control(page.locator(f'[data-pixel-item="{item}"]'))
                row=page.locator(f'.pixel-bag-detail .item[data-item-id="{item}"]')
                assert row.is_visible() and len(row.locator(':scope>span>small').inner_text())>10
                click_control(row.locator('.item-use' if kind=='pill' else '.dungeon-manual-learn'))
                page.wait_for_function('!busy')
                assert not any(i.id==item for i in engine.store.load(identity).player.inventory)
                if width<800 and page.locator('.pixel-item-sheet>header button').is_visible():click_control(page.locator('.pixel-item-sheet>header button'))
            saved=engine.store.load(identity)
            assert any(t.id==loot['book'] for t in saved.player.known_techniques)
            for category in ('body','divine_sense','transformation'):
                book=next(t for t in saved.player.known_techniques if t.category==category)
                assert page.request.post(base+f'/api/games/{identity}/equip-technique',data=dict(technique_id=book.id,slot='combat')).status==400
            assert not errors,errors
            page.close()
        browser.close()
    print(f'Final EXE dungeon acquisition/use/learn/battle/category checks passed: DLC={with_dlc}',flush=True)
