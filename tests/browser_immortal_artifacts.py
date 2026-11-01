"""Actual promotion and four quality advances, stale recovery and mobile art."""
import sys,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item,combat_power
from cultivation_life.system.immortal_artifacts import MATERIALS
from scripts.browser_navigation import navigation_locator,click_control


def main():
    output=ROOT/'build/immortal-artifacts-browser';output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='immortal-artifact-ui-') as folder:
        e=GameEngine(ROOT,Path(folder)/'saves')
        class Quiet(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',e),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Quiet);threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for theme,width,height in [('a',1440,960),('f',390,844),('light',390,844),('dark',754,365)]:
                        made=e.create_game('仙器界面','supreme_metal','demonic',1101,preset_id='asura_upper')
                        g=e._load(made['id']);g.pending_event=None;g.player.inventory.clear()
                        add_item(g.player,'starfall_blade');add_item(g.player,'spirit_stone',10**12)
                        for key,_ in MATERIALS:add_item(g.player,key,4 if key==MATERIALS[0][0] else 3)
                        e.store.save(g);e.natal_artifact_action(g.id,'bind','starfall_blade')
                        g=e._load(g.id);g.natal_artifact['refinement_count']=36;e.store.save(g)
                        page=browser.new_page(viewport=dict(width=width,height=height));errors=[]
                        page.on('pageerror',lambda x:errors.append(str(x)))
                        base=f'http://127.0.0.1:{http.server_port}'
                        page.goto(base);page.wait_for_function('!!configData&&!busy')
                        page.locator('#theme-open').click();pixel=theme in ('light','dark')
                        page.locator('#theme-dialog [data-pixel-setting]').set_checked(pixel)
                        selector=f'[data-pixel-theme-choice={theme}]' if pixel else f'[data-theme-choice={theme}]'
                        page.locator('#theme-dialog '+selector).click();page.locator('[data-close-dialog=theme-dialog]').click();page.evaluate('GameThemes.saved')
                        page.evaluate('id=>loadGame(id)',g.id)
                        navigation_locator(page,'[data-panel-target=natal-artifact]').click()
                        assert page.locator('.natal-promote').is_disabled()
                        click_control(page.locator('.natal-refine-tools .natal-action').first)
                        page.wait_for_function('!busy&&game.natal_artifact.refinement_count===37')
                        before=e._load(g.id);power=combat_power(before.player)
                        click_control(page.locator('.natal-promote'))
                        page.wait_for_function('!busy&&game.natal_artifact.damage_type==="仙"')
                        assert page.locator('.natal-promote').is_disabled()
                        assert combat_power(e._load(g.id).player)==power
                        click_control(page.locator('#natal-artifact-toggle'))
                        entry=navigation_locator(page,'[data-panel-target=immortal-artifacts]')
                        assert entry.locator('small').inner_text()=='魔器'
                        entry.click();page.locator('.immortal-artifact-entry').wait_for()
                        if pixel:page.wait_for_function('Array.from(document.querySelectorAll(".immortal-artifact-materials img")).every(i=>i.complete&&i.naturalWidth===128)')
                        assert page.locator('.immortal-artifact-entry').count()==1
                        assert page.locator('#immortal-artifacts-card').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                        assert page.locator('.ia-grade-track [aria-current=step]').inner_text()=='五品'
                        assert page.locator('.ia-cost').inner_text().find('三铸神魔铁')>=0
                        page.locator('#immortal-artifacts-card').evaluate('n=>n.scrollTop=0')
                        page.screenshot(path=str(output/f'{theme}-{width}-ready.png'))
                        for rank in (5,4,3,2):
                            if rank==5:
                                old=page.evaluate('({artifact_id:game.immortal_artifacts.equipment[0].id,expected_grade:5,expected_revision:game.immortal_artifacts.revision})')
                                reply=page.request.post(base+f'/api/games/{g.id}/immortal-artifact',data=old);assert reply.status==200
                                with page.expect_response(lambda r:r.url.endswith('/immortal-artifact')) as stale:click_control(page.locator('[data-immortal-refine]'))
                                assert stale.value.status==400
                                page.wait_for_function('!busy&&game.immortal_artifacts.equipment[0].grade===4')
                            else:
                                with page.expect_response(lambda r:r.url.endswith('/immortal-artifact')) as action:click_control(page.locator('[data-immortal-refine]'))
                                assert action.value.status==200
                                page.wait_for_function('old=>!busy&&game.immortal_artifacts.equipment[0].grade===old-1',arg=rank)
                        assert page.locator('[data-immortal-refine]').count()==0
                        assert '一品已成' in page.locator('#immortal-artifacts-content').inner_text()
                        assert page.locator('.ia-grade-track [aria-current=step]').inner_text()=='一品'
                        final=e._load(g.id);assert combat_power(final.player)==power
                        assert final.player.age==before.player.age and final.rng_state==before.rng_state
                        assert all(not any(i.id==key for i in final.player.inventory) for key,_ in MATERIALS)
                        snapshot=e.store._path(g.id).read_bytes()
                        click_control(page.locator('#immortal-artifacts-toggle'))
                        navigation_locator(page,'[data-panel-target=immortal-artifacts]').click()
                        page.locator('.immortal-artifact-max').scroll_into_view_if_needed()
                        page.screenshot(path=str(output/f'{theme}-{width}.png'))
                        assert e.store._path(g.id).read_bytes()==snapshot
                        assert not errors,errors
                        page.close();print(f'{theme} {width}x{height}: promotion, four grades, real costs, stale recovery, one-grade limit and unchanged power/time/RNG passed',flush=True)
                    browser.close()
            finally:http.shutdown();http.server_close()


if __name__=='__main__':main()
