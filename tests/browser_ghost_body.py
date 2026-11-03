"""Real UI clicks: independent ghost body, transactions, stale recovery and report."""
import json,sys,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.rules import max_hp,max_mp
from cultivation_life.runtime import decode_rng,encode_rng
from cultivation_life.content_registry import WORLD_SYSTEMS
from test_ghost_body import supply_materials
from cultivation_life.ghost_body_content import MATERIAL_IDS
from scripts.browser_navigation import navigation_locator,click_control,reveal_subpage


def main():
    output=ROOT/'build/ghost-body-browser';output.mkdir(exist_ok=True);results=[]
    with tempfile.TemporaryDirectory(prefix='ghost-body-ui-') as folder:
        e=GameEngine(ROOT,Path(folder)/'saves')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',e),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for theme,width,height in [('light',1440,1000),('dark',390,844),('f',754,365)]:
                        made=e.create_game('鬼躯验收','supreme_metal','ghost',221,preset_id='reincarnation_upper')
                        g=e._load(made['id']);g.pending_event=None;g.player.body_training=100;g.player.opportunity=10**12;g.player.next_tribulation_age=None
                        g.player.immortal_body={'level':9};supply_materials(g,120);e.store.save(g)
                        page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce');errors=[]
                        page.on('pageerror',lambda error:errors.append(str(error)))
                        page.goto(f'http://127.0.0.1:{http.server_port}');page.wait_for_function('!!configData&&!busy')
                        page.locator('#theme-open').click();pixel=theme!='f'
                        page.locator('#theme-dialog [data-pixel-setting]').set_checked(pixel)
                        page.locator('#theme-dialog '+(f'[data-pixel-theme-choice={theme}]' if pixel else '[data-theme-choice=f]')).click()
                        page.locator('[data-close-dialog=theme-dialog]').click();page.evaluate('id=>loadGame(id)',g.id)
                        page.wait_for_function('!busy&&!!game?.upper_voisinages?.ghost_body?.available')
                        before=e.store._path(g.id).read_bytes()
                        navigation_locator(page,'[data-panel-target=ghost-body]').click()
                        assert page.locator('#ghost-body-card').is_visible()
                        assert page.locator('#ghost-body-card h2').inner_text()=='鬼躯'
                        assert e.store._path(g.id).read_bytes()==before
                        click_control(page.locator('[data-ghost-body-train]'))
                        page.wait_for_function('!busy&&game.upper_voisinages.ghost_body.level===10')
                        saved=e._load(g.id);before=saved.player.opportunity
                        bill=page.evaluate('game.upper_voisinages.ghost_body.rows[0].cost')
                        click_control(page.locator('[data-ghost-refine=wuxiang]'))
                        page.wait_for_function('!busy&&game.upper_voisinages.ghost_body.rows[0].level===1')
                        assert e._load(g.id).player.opportunity==before-bill['opportunity']
                        # Change the real server state while retaining the old visible button.
                        saved=e._load(g.id);saved.player.immortal_body['ghost_training']['wuxiang']=2;e.store.save(saved)
                        op=saved.player.opportunity
                        with page.expect_response(lambda r:r.url.endswith('/upper-voisinage')) as stale:
                            click_control(page.locator('[data-ghost-refine=wuxiang]'))
                        assert stale.value.status==400
                        page.wait_for_function('!busy&&game.upper_voisinages.ghost_body.rows[0].level===2')
                        assert e._load(g.id).player.opportunity==op
                        saved=e._load(g.id);saved.player.inventory=[i for i in saved.player.inventory if i.id not in MATERIAL_IDS];e.store.save(saved)
                        with page.expect_response(lambda r:r.url.endswith('/upper-voisinage')) as missing:
                            click_control(page.locator('[data-ghost-refine=wuxiang]'))
                        assert missing.value.status==400
                        page.wait_for_function('!busy&&!game.upper_voisinages.ghost_body.rows[0].can_train')
                        assert page.locator('[data-ghost-refine=wuxiang]').is_disabled()
                        g=e._load(g.id);g.player.immortal_body={'level':50};supply_materials(g);e.store.save(g)
                        page.evaluate('id=>loadGame(id)',g.id)
                        assert page.locator('.ghost-body-change').count()==5
                        if pixel:
                            for img in page.locator('.ghost-body-material img').all():img.scroll_into_view_if_needed()
                            page.wait_for_function('''()=>[...document.querySelectorAll('.ghost-body-material img')].length===5&&[...document.querySelectorAll('.ghost-body-material img')].every(i=>i.complete&&i.naturalWidth===128)''')
                        assert page.locator('[data-body-family=ghost] .body-cultivation-card').count()==5
                        assert page.locator('.ghost-body').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                        page.locator('.ghost-body-title').scroll_into_view_if_needed();page.screenshot(path=str(output/f'{theme}-{width}.png'))
                        click_control(page.locator('#ghost-body-toggle'))
                        navigation_locator(page,'[data-panel-target=ghost-body]').click()
                        assert page.locator('.ghost-body-title').inner_text().endswith('50/50层')
                        capped=e._load(g.id);capped.player.immortal_body['ghost_training']={k:10 for k in ('wuxiang','zhaoye','yuhun','wangqing','yinguo')};e.store.save(capped)
                        page.evaluate('id=>loadGame(id)',g.id)
                        assert page.locator('[data-ghost-refine=wuxiang]').is_disabled()
                        assert page.locator('[data-ghost-refine=wuxiang]').inner_text()=='已修至十重'
                        assert page.locator('[data-ghost-change=wuxiang] [role=meter]').get_attribute('aria-valuenow')=='10'
                        assert '培养圆满' in page.locator('[data-ghost-change=wuxiang]').inner_text()
                        assert '每段继承65%' in page.locator('[data-ghost-change=zhaoye]').inner_text()
                        assert '溢出60%' in page.locator('[data-ghost-change=wangqing]').inner_text()
                        assert '容量的15%' in page.locator('[data-ghost-change=yinguo]').inner_text()
                        assert '强度18%' in page.locator('[data-ghost-change=yinguo]').inner_text()
                        click_control(page.locator('#ghost-body-toggle'))
                        g=e._load(g.id);g.pending_event=None;g.settings.update(combat_popup=False,silent_events=True)
                        field=WORLD_SYSTEMS['upper_voisinages']['worlds']['reincarnation']['fields'][0]['id']
                        g.player.world_voisinages.setdefault('reincarnation',{}).update(active=field,levels={field:8})
                        g.player.immortal_aperture['current']=g.player.immortal_aperture['capacity'];g.player.hp=max_hp(g.player);g.player.mp=max_mp(g.player)
                        target=dict(target_name='鬼躯演武',target_power=e._player_battle_power(g)*.8,target_realm_index=9,target_layer=1,combat_type='cultivator',kind='environment',max_rounds=3)
                        rng=decode_rng(g.seed,g.rng_state);e._combat(g,target,False,rng);g.rng_state=encode_rng(rng);e.store.save(g)
                        page.evaluate('id=>loadGame(id)',g.id);navigation_locator(page,'#battle-report-open').click()
                        page.locator('#battle-round-list section').first.wait_for(state='attached');reveal_subpage(page,page.locator('#battle-round-list'))
                        if not page.locator('.battle-round-details').evaluate('n=>n.open'):click_control(page.locator('.battle-round-details>summary'))
                        text=page.locator('#battle-round-list').inner_text()
                        assert all(name in text for name in ('无相','照业','御魂','忘情','因果'))
                        core=e.create_game('入口资格验收','supreme_metal','dao',112,preset_id='core')
                        page.evaluate('id=>loadGame(id)',core['id'])
                        assert page.locator('[data-panel-target=ghost-body]').evaluate('n=>n.classList.contains("hidden")')
                        assert not errors,errors
                        results.append(dict(theme=theme,width=width,independent_entry=True,readonly_open=True,paid_once=True,stale_safe=True,missing_recovery=True,five_mechanisms=True,battle_text=True));page.close()
                    browser.close()
            finally:http.shutdown();http.server_close()
    (output/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Ghost body UI passed: real fees, stale/missing recovery, three layouts, qualification and actual battle report')


if __name__=='__main__':main()
