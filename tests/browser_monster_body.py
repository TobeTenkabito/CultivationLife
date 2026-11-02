"""Real HTTP five-change training, choice, material art and battle report clicks."""
import json,sys,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item,remove_item,max_hp,max_mp
from cultivation_life.system.monster_body import config
from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.runtime import decode_rng,encode_rng
from scripts.browser_navigation import navigation_locator,click_control,reveal_subpage


def main():
    output=ROOT/'build/monster-body-browser';output.mkdir(exist_ok=True);results=[]
    with tempfile.TemporaryDirectory(prefix='monster-body-ui-') as folder:
        e=GameEngine(ROOT,Path(folder)/'saves')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',e),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for theme,width,height in [('light',1440,1000),('dark',390,844),('f',754,365)]:
                        made=e.create_game('妖躯验收','supreme_metal','monster',111,preset_id='nether_upper',monster_species_id='serpent')
                        g=e._load(made['id']);g.pending_event=None;g.player.body_training=100;g.player.opportunity=10**12;g.player.next_tribulation_age=None
                        g.player.immortal_body['monster']={'level':9}
                        for row in config()['mechanisms']:
                            for key in row['recipe']:add_item(g.player,key,10000)
                        e.store.save(g);page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce');errors=[]
                        page.on('pageerror',lambda error:errors.append(str(error)))
                        base=f'http://127.0.0.1:{http.server_port}';page.goto(base);page.wait_for_function('!!configData&&!busy')
                        page.locator('#theme-open').click();pixel=theme!='f'
                        page.locator('#theme-dialog [data-pixel-setting]').set_checked(pixel)
                        page.locator('#theme-dialog '+(f'[data-pixel-theme-choice={theme}]' if pixel else '[data-theme-choice=f]')).click()
                        page.locator('[data-close-dialog=theme-dialog]').click();page.evaluate('id=>loadGame(id)',g.id)
                        navigation_locator(page,'[data-panel-target=upper-voisinage]').click()
                        assert page.locator('#upper-voisinage-content .monster-body').count()==0
                        click_control(page.locator('#upper-voisinage-toggle'))
                        before_open=e.store._path(g.id).read_bytes()
                        navigation_locator(page,'[data-panel-target=monster-body]').click()
                        assert page.locator('#monster-body-card').is_visible()
                        assert page.locator('#monster-body-card h2').inner_text()=='妖躯'
                        assert page.locator('[data-panel-target=monster-body]').evaluate('n=>{const s=getComputedStyle(n);return s.backgroundColor!=="rgba(0, 0, 0, 0)"&&s.color!==s.backgroundColor}')
                        assert e.store._path(g.id).read_bytes()==before_open
                        click_control(page.locator('[data-monster-body-train]'))
                        page.wait_for_function('!busy&&game.upper_voisinages.monster_body.level===10')
                        assert sum(r['unlocked'] for r in page.evaluate('game.upper_voisinages.monster_body.rows'))==1
                        payload=dict(action='monster_body_refine',voisinage_id='xuanfu',expected_level=0)
                        bill=page.evaluate('game.upper_voisinages.monster_body.rows[0].cost')
                        old=e._load(g.id);old_qty={i.id:i.quantity for i in old.player.inventory};old_op=old.player.opportunity
                        assert page.request.post(base+f'/api/games/{g.id}/upper-voisinage',data=payload).status==200
                        with page.expect_response(lambda r:r.url.endswith('/upper-voisinage')) as stale:
                            click_control(page.locator('[data-monster-change=xuanfu]'))
                        assert stale.value.status==400;page.wait_for_function('!busy&&game.upper_voisinages.monster_body.rows[0].level===1')
                        saved=e._load(g.id);assert saved.player.opportunity==old_op-bill['opportunity']
                        for key,amount in bill['materials'].items():assert next(i.quantity for i in saved.player.inventory if i.id==key)==old_qty[key]-amount
                        assert saved.rng_state==old.rng_state and saved.player.age==old.player.age
                        for key in bill['materials']:remove_item(saved.player,key,next(i.quantity for i in saved.player.inventory if i.id==key))
                        e.store.save(saved)
                        with page.expect_response(lambda r:r.url.endswith('/upper-voisinage')) as missing:
                            click_control(page.locator('[data-monster-change=xuanfu]'))
                        assert missing.value.status==400;page.wait_for_function('!busy&&!game.upper_voisinages.monster_body.rows[0].can_train')
                        assert page.locator('[data-monster-change=xuanfu]').is_disabled()
                        saved=e._load(g.id);saved.player.immortal_body['monster'].update(level=50,training={'liezang':5})
                        for key in bill['materials']:add_item(saved.player,key,10000)
                        e.store.save(saved);page.evaluate('id=>loadGame(id)',g.id)
                        choice=page.get_by_label('烈脏每次施权择一');choice.select_option('seal')
                        page.wait_for_function('!busy&&game.upper_voisinages.monster_body.reaction==="seal"')
                        assert e._load(g.id).player.immortal_body['monster']['reaction']=='seal'
                        assert page.locator('.monster-change').count()==5
                        assert page.locator('[data-body-family=monster] .body-cultivation-stages li').count()==5
                        assert page.locator('[data-body-family=monster] [role=meter]').count()==5
                        assert page.locator('.monster-body').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                        if pixel:
                            for img in page.locator('.monster-change .monster-body-material img').all():img.scroll_into_view_if_needed()
                            page.wait_for_function('''()=>[...document.querySelectorAll('.monster-change .monster-body-material img')].length===5&&[...document.querySelectorAll('.monster-change .monster-body-material img')].every(i=>i.complete&&i.naturalWidth===128)''')
                        page.locator('.monster-body-title').scroll_into_view_if_needed();page.screenshot(path=str(output/f'{theme}-{width}.png'))
                        click_control(page.locator('#monster-body-toggle'))
                        navigation_locator(page,'[data-panel-target=monster-body]').click()
                        assert page.get_by_label('烈脏每次施权择一').input_value()=='seal'
                        click_control(page.locator('#monster-body-toggle'))
                        g=e._load(g.id);g.pending_event=None;g.settings.update(combat_popup=False,silent_events=True)
                        field=WORLD_SYSTEMS['upper_voisinages']['worlds']['nether']['fields'][0]['id']
                        g.player.world_voisinages.setdefault('nether',{}).update(active=field,levels={field:8})
                        g.player.immortal_aperture['current']=g.player.immortal_aperture['capacity'];g.player.hp=max_hp(g.player);g.player.mp=max_mp(g.player)
                        target=dict(target_name='五蜕演武',target_power=e._player_battle_power(g)*.8,target_realm_index=9,target_layer=1,combat_type='cultivator',kind='environment',max_rounds=3)
                        rng=decode_rng(g.seed,g.rng_state);e._combat(g,target,False,rng);g.rng_state=encode_rng(rng);e.store.save(g)
                        page.evaluate('id=>loadGame(id)',g.id);navigation_locator(page,'#battle-report-open').click()
                        page.locator('#battle-round-list section').first.wait_for(state='attached');reveal_subpage(page,page.locator('#battle-round-list'))
                        if not page.locator('.battle-round-details').evaluate('n=>n.open'):click_control(page.locator('.battle-round-details>summary'))
                        text=page.locator('#battle-round-list').inner_text();assert all(name in text for name in ('玄肤','逆骨','烈脏','沸血','神魂'))
                        core=e.create_game('入口资格验收','supreme_metal','dao',112,preset_id='core')
                        page.evaluate('id=>loadGame(id)',core['id'])
                        assert page.locator('[data-panel-target=monster-body]').evaluate('n=>n.classList.contains("hidden")')
                        assert not page.locator('#monster-body-card').evaluate('n=>n.classList.contains("panel-open")')
                        assert not errors,errors;results.append(dict(theme=theme,width=width,independent_entry=True,readonly_open=True,qualification=True,tenth_layer=True,stale_safe=True,missing_recovery=True,paid_once=True,select_one=True,material_art=pixel,battle_text=True));page.close()
                    browser.close()
            finally:http.shutdown();http.server_close()
    (output/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Monster body UI passed: tenth-layer unlock, real fees/stale recovery, choices, material art, 3 layouts and real battle text')


if __name__=='__main__':main()
