"""Real HTTP magic-body unlock, paid/stale training, busy gates and round text."""
import sys,tempfile,threading,json,random
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.rules import max_hp,max_mp
from cultivation_life.runtime import decode_rng,encode_rng
from scripts.browser_navigation import navigation_locator,click_control,reveal_subpage


def prepare_combat(engine,g):
    g.pending_event=None;g.settings.update(combat_popup=False,silent_events=True)
    g.player.asura_cultivation.update(route='asura',level=9,domain_rank=8,domain_power=10,
        domain_name='五蕴演武魔域',body_level=50,aggregates=dict(se=10,shou=10,xiang=10,xing=10,shi=10))
    g.player.immortal_aperture['current']=g.player.immortal_aperture['capacity']
    g.player.hp=max_hp(g.player);g.player.mp=max_mp(g.player)
    target=dict(target_name='五蕴演武',target_power=engine._player_battle_power(g),target_realm_index=9,
                target_layer=1,kind='environment',combat_type='cultivator',max_rounds=3)
    rng=decode_rng(g.seed,g.rng_state);engine._combat(g,target,False,rng);g.rng_state=encode_rng(rng)
    engine.store.save(g)


def main():
    output=ROOT/'build/wuyun-browser';output.mkdir(exist_ok=True);results=[]
    with tempfile.TemporaryDirectory(prefix='wuyun-ui-') as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for theme,width,height in [('light',1440,1000),('dark',390,844),('f',754,365)]:
                        made=engine.create_game('五蕴验收','supreme_metal','demonic',470,preset_id='asura_upper')
                        g=engine._load(made['id']);g.pending_event=None;g.player.next_tribulation_age=None
                        g.player.asura_cultivation.update(conversion=5,body_level=9,souls=100000)
                        g.player.body_training=100;g.player.opportunity=10**12;engine.store.save(g)
                        page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce');errors=[]
                        page.on('pageerror',lambda e:errors.append(str(e)))
                        base=f'http://127.0.0.1:{http.server_port}';page.goto(base);page.wait_for_function('!!configData&&!busy')
                        page.locator('#theme-open').click();pixel=theme!='f'
                        page.locator('#theme-dialog [data-pixel-setting]').set_checked(pixel)
                        page.locator('#theme-dialog '+(f'[data-pixel-theme-choice={theme}]' if pixel else f'[data-theme-choice={theme}]')).click()
                        page.locator('[data-close-dialog=theme-dialog]').click();page.evaluate('GameThemes.saved')
                        page.evaluate('id=>loadGame(id)',g.id)
                        navigation_locator(page,'[data-panel-target=asura-body]').click()
                        page.locator('[data-aggregate=se]').wait_for(state='attached')
                        assert page.locator('.asura-aggregate-card.locked').count()==5
                        click_control(page.get_by_role('button',name='锻炼下一层修罗之躯',exact=True))
                        page.wait_for_function('!busy&&game.asura.body_level===10')
                        assert page.locator('.asura-aggregate-card.locked').count()==4
                        assert not page.locator('[data-aggregate=se]').is_disabled()
                        bill=page.evaluate('game.asura.aggregates[0].cost');saved=engine._load(g.id)
                        old_souls=saved.player.asura_cultivation['souls'];old_op=saved.player.opportunity;old_rng=saved.rng_state;old_age=saved.player.age
                        payload=dict(action='train_aggregate',target_id='se',expected_level=0)
                        assert page.request.post(base+f'/api/games/{g.id}/asura',data=payload).status==200
                        with page.expect_response(lambda r:r.url.endswith('/asura')) as response:
                            click_control(page.locator('[data-aggregate=se]'))
                        assert response.value.status==400
                        page.wait_for_function('!busy&&game.asura.aggregates[0].level===1')
                        saved=engine._load(g.id)
                        assert saved.player.asura_cultivation['souls']==old_souls-bill['souls']
                        assert saved.player.opportunity==old_op-bill['opportunity']
                        assert saved.rng_state==old_rng and saved.player.age==old_age
                        click_control(page.locator('#asura-body-toggle'))
                        navigation_locator(page,'[data-panel-target=asura-route]').click()
                        assert '10层' in page.locator('#asura-route-content').inner_text()
                        click_control(page.locator('#asura-route-toggle'))
                        saved.player.asura_cultivation['body_level']=50;engine.store.save(saved)
                        page.evaluate('id=>loadGame(id)',g.id);navigation_locator(page,'[data-panel-target=asura-body]').click()
                        page.wait_for_function('document.querySelectorAll(".asura-aggregate-card.locked").length===0')
                        assert page.locator('.asura-body-track span').count()==50
                        card=page.locator('#asura-body-card')
                        assert card.evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                        path=engine.store._path(g.id);before=path.read_bytes()
                        page.screenshot(path=str(output/f'{theme}-{width}.png'))
                        assert path.read_bytes()==before
                        click_control(page.locator('#asura-body-toggle'))
                        prepare_combat(engine,engine._load(g.id));page.evaluate('id=>loadGame(id)',g.id)
                        navigation_locator(page,'#battle-report-open').click();page.locator('#battle-round-list section').first.wait_for(state='attached')
                        reveal_subpage(page,page.locator('#battle-round-list'))
                        if not page.locator('.battle-round-details').evaluate('n=>n.open'):click_control(page.locator('.battle-round-details>summary'))
                        text=page.locator('#battle-round-list').inner_text()
                        assert all(name in text for name in ('色蕴','受蕴','想蕴','行蕴','识蕴'))
                        assert '轮首暴击判定' in text and page.evaluate('game.last_combat_report.rounds.some(r=>r.voisinage?.body_mechanisms)')
                        assert not errors,errors
                        results.append(dict(theme=theme,width=width,real_tenth_layer=True,stale_safe=True,paid_once=True,readonly=True,battle_text=True))
                        page.close()
                    browser.close()
            finally:http.shutdown();http.server_close()
    (output/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Wuyun UI passed: actual tenth-layer unlock, paid/stale-safe training, 50 layers/five cards, real battle text, desktop/mobile/landscape')


if __name__=='__main__':main()
