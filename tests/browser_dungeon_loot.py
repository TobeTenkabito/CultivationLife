"""Actual loot acquisition, paged bag inspection and battle overlay clicks."""
import copy
import random
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.content_registry import ITEM_CATALOG, WORLD_SYSTEMS
from cultivation_life.rules import add_item,max_hp,max_mp
from cultivation_life.system.dungeons.rewards import recipe,bounded_recipe,RELIC_FORMS
from scripts.browser_navigation import navigation_locator


def frozen_loot(engine,identity):
    game=engine.store.load(identity);site=next(iter(game.dungeon_state['instances'].values()))
    rewards=[]
    for index,kind in enumerate(('pill','artifact','technique')):
        node=site['nodes'][index]
        for seed in range(100):
            reward=recipe(random.Random(seed),node['reward']['id'],site['realm'],'dao',site['theme'],'ordinary',world='human')
            if reward['kind']==kind:break
        else:raise AssertionError(kind)
        bounded_recipe(reward,'ordinary','human')
        node.update(kind='cache',mechanism='cache',risk=0,reward=reward)
        rewards.append(reward)
    for role in site['roles'].values():role.update(state='declined',offer_step=99)
    game.settings['combat_popup']=True
    # Put the acquired medicine beyond the old list's first page.
    for item in [i for i in ITEM_CATALOG.values() if 'pill' in i.tags][:12]:add_item(game.player,item.id)
    engine.store.save(game)
    return rewards


def main():
    output=ROOT/'build/reviews/dungeon-fixes-1118';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for theme,width,height in (('light',1440,960),('dark',393,852)):
                        page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce')
                        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                        page.goto(f'http://127.0.0.1:{http.server_port}');page.wait_for_function('!!configData')
                        page.locator(f'[data-theme-picker=start] [data-pixel-theme-choice={theme}]').click()
                        game=engine.store.load(engine.create_game('遗宝验收','heavenly','dao',342,preset_id='core')['id'])
                        game.player.realm_index=4;game.player.layer=9
                        game.player.hp=max_hp(game.player);game.player.mp=max_mp(game.player)
                        engine.store.save(game)
                        page.evaluate('async id=>{await loadGame(id);UtilityPanels.open("dungeon");}',game.id)
                        profile=WORLD_SYSTEMS['seeded_dungeons']['profiles'][game.player.world+':'+game.player.location_id]
                        with patch.dict(profile,weights=[1,0,0,0]):
                            page.locator('[data-dungeon-action=discover]').click();page.wait_for_function('!busy&&game.dungeons.used===1')
                        rewards=frozen_loot(engine,game.id)
                        page.evaluate('async id=>{await loadGame(id);}',game.id)
                        page.locator('[data-dungeon-action=enter]').click();page.wait_for_function('!busy&&game.dungeons.active')
                        for _ in range(3):
                            page.locator('[data-choice=seize]').click();page.wait_for_function('!busy')
                        saved=engine.store.load(game.id);site=saved.dungeon_state['instances'][saved.dungeon_state['active']]
                        assert len(site['claims'])==3
                        role=next(iter(site['roles'].values()))
                        role.update(state='hostile',known=True,realm=1,true_realm=1,layer=1,power_factor=1.,purpose='seek')
                        role['ledger']['domain_rank']=0
                        site['pending']=dict(kind='guardian',actor=role['id'])
                        engine.store.save(saved)
                        page.evaluate('async id=>{await loadGame(id);}',game.id)
                        page.locator('[data-choice=fight]').click()
                        page.wait_for_function('!busy&&!!game.last_combat_report')
                        report=page.locator('#battle-report-card');report.wait_for(state='visible')
                        assert page.locator('#dungeon-card').is_visible()
                        close=page.locator('#battle-report-toggle')
                        assert close.evaluate('n=>{const r=n.getBoundingClientRect();return n.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));}')
                        page.screenshot(path=str(output/f'battle-{theme}.png'))
                        close.click();report.wait_for(state='hidden')
                        page.locator('[data-dungeon-action=exit]').click();page.wait_for_function('!busy&&!game.dungeons.active')
                        page.keyboard.press('Escape')
                        navigation_locator(page,'[data-panel-target=inventory]').click()
                        icons=page.evaluate("""async forms=>{
                            await PixelLibrary.ensure();
                            return Promise.all(forms.map(async name=>{
                                const asset=PixelLibrary.resolve({id:'dungeon:legacy',name,tags:['equipment']});
                                const image=new Image();image.src=asset.file;await image.decode();
                                return asset.file;
                            }));
                        }""",list(RELIC_FORMS))
                        assert len(set(icons))==len(RELIC_FORMS)
                        def inspect(item_id):
                            page.locator(f'[data-pixel-item="{item_id}"]').click()
                            row=page.locator(f'.pixel-bag-detail .item[data-item-id="{item_id}"]')
                            assert row.is_visible(),row.evaluate('n=>n.outerHTML')
                            assert len(row.locator(':scope>span>small').inner_text())>10
                            art=page.locator('.pixel-bag-detail:visible .pixel-bag-art img')
                            assert art.evaluate('async img=>{await img.decode();return img.naturalWidth>0}')
                            key=art.get_attribute('data-asset')
                            assert key and key not in {'gear.other','extra.unknown'}
                            assert page.locator(f'[data-pixel-item="{item_id}"] img').get_attribute('data-asset')==key
                            return row
                        pill=rewards[0]['id']
                        assert page.locator(f'#inventory-list [data-item-id="{pill}"]').get_attribute('data-list-page-hidden') is not None
                        row=inspect(pill)
                        assert row.locator('.item-use').is_enabled()
                        page.screenshot(path=str(output/f'loot-{theme}.png'))
                        before=engine.store.load(game.id)
                        row.locator('.item-use').click();page.wait_for_function('!busy')
                        after=engine.store.load(game.id)
                        assert not any(i.id==pill for i in after.player.inventory)
                        assert after.player.opportunity>before.player.opportunity
                        row=inspect(rewards[1]['id'])
                        assert '随身生效' in page.locator('.pixel-bag-detail:visible .pixel-item-status').inner_text()
                        if width<800:page.locator('.pixel-item-sheet>header button').click()
                        book=rewards[2]['book']['id'];row=inspect('MANUAL_DUNGEON_'+book)
                        row.locator('.dungeon-manual-learn').click();page.wait_for_function('!busy')
                        after=engine.store.load(game.id)
                        assert any(t.id==book for t in after.player.known_techniques)
                        assert not any(i.id=='MANUAL_DUNGEON_'+book for i in after.player.inventory)
                        assert not errors,errors
                        page.close()
                    browser.close()
            finally:http.shutdown();http.server_close()
    print('Dungeon loot browser passed: paged descriptions/actions, real acquire/use/learn, relic resonance and real battle above dungeon, desktop/mobile themes')


if __name__=='__main__':main()
