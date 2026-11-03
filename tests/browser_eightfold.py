"""Real HTTP training, plans, stale submissions and battle-text acceptance."""
import json,sys,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.asura_discipline_content import ROUTES
from scripts.browser_navigation import navigation_locator,click_control,reveal_subpage
from browser_wuyun import prepare_combat


def main():
    output=ROOT/'build/eightfold-browser';output.mkdir(exist_ok=True);results=[]
    with tempfile.TemporaryDirectory(prefix='eightfold-ui-') as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for theme,width,height in [('light',1440,1000),('dark',390,844),('light',754,365)]:
                        made=engine.create_game('八部验收','supreme_metal','demonic',471,preset_id='asura_upper')
                        g=engine._load(made['id']);g.pending_event=None;g.player.next_tribulation_age=None
                        g.player.asura_cultivation.update(route='deva',level=1,conversion=5,body_level=50,souls=100000,
                            domain_rank=8,domain_power=10,domain_name='八部演武魔域')
                        g.player.body_training=100;g.player.opportunity=10**12;engine.store.save(g)
                        page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce');errors=[]
                        page.on('pageerror',lambda e:errors.append(str(e)))
                        base=f'http://127.0.0.1:{http.server_port}';page.goto(base);page.wait_for_function('!!configData&&!busy')
                        page.locator('#theme-open').click();pixel=theme!='f'
                        page.locator(f'#theme-dialog [data-pixel-theme-choice={theme}]').click()
                        page.locator('[data-close-dialog=theme-dialog]').click();page.evaluate('GameThemes.saved')
                        page.evaluate('id=>loadGame(id)',g.id);navigation_locator(page,'[data-panel-target=asura-route]').click()
                        page.locator('.asura-field-ability').first.wait_for(state='attached')
                        assert page.locator('.asura-field-ability.locked').count()==3
                        before=engine._load(g.id);souls=before.player.asura_cultivation['souls']
                        response=page.request.post(base+f'/api/games/{g.id}/asura',data=dict(action='train_route',expected_level=1))
                        assert response.status==200
                        with page.expect_response(lambda r:r.url.endswith('/asura')) as stale:
                            click_control(page.locator('[data-asura-action=train_route]'))
                        assert stale.value.status==400
                        page.wait_for_function('!busy&&game.asura.level===2')
                        saved=engine._load(g.id)
                        assert saved.player.asura_cultivation['souls']==souls-60
                        assert saved.player.age==before.player.age and saved.rng_state==before.rng_state
                        assert page.locator('.asura-field-ability.locked').count()==2
                        for old,remaining in ((3,1),(6,0)):
                            saved=engine._load(g.id);saved.player.asura_cultivation['level']=old;engine.store.save(saved)
                            page.evaluate('id=>loadGame(id)',g.id)
                            if not page.locator('#asura-route-card').is_visible():navigation_locator(page,'[data-panel-target=asura-route]').click()
                            paid=saved.player.asura_cultivation['souls']
                            click_control(page.locator('[data-asura-action=train_route]'))
                            page.wait_for_function('n=>!busy&&game.asura.level===n',arg=old+1)
                            assert engine._load(g.id).player.asura_cultivation['souls']==paid-60*old
                            assert page.locator('.asura-field-ability.locked').count()==remaining
                        click_control(page.locator('#asura-route-toggle'))
                        for route in ROUTES:
                            saved=engine._load(g.id);s=saved.player.asura_cultivation
                            s.update(route=route,level=9);s.pop('discipline_plan',None);engine.store.save(saved)
                            page.evaluate('id=>loadGame(id)',g.id)
                            navigation_locator(page,'[data-panel-target=asura-route]').click()
                            assert page.locator('.asura-field-ability').count()==3
                            assert page.locator('.asura-field-ability.locked').count()==0
                            assert page.locator('#asura-route-content').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                            click_control(page.locator('#asura-route-toggle'))
                            navigation_locator(page,'[data-panel-target=asura-domain]').click()
                            select=page.get_by_label('八部权能预案',exact=True)
                            assert select.is_enabled()
                            last=select.locator('option').last.get_attribute('value')
                            saved=engine._load(g.id);frozen=(saved.player.age,saved.rng_state,saved.player.asura_cultivation['souls'],saved.player.opportunity)
                            with page.expect_response(lambda r:r.url.endswith('/asura')) as chosen:select.select_option(last)
                            assert chosen.value.status==200
                            page.wait_for_function('mode=>!busy&&game.asura.field_discipline.mode===mode',arg=last)
                            saved=engine._load(g.id)
                            assert frozen==(saved.player.age,saved.rng_state,saved.player.asura_cultivation['souls'],saved.player.opportunity)
                            assert saved.player.asura_cultivation['discipline_plan']['mode']==last
                            if route=='kinnara':
                                page.get_by_label('三奏起曲',exact=True).select_option('2')
                                page.wait_for_function('!busy&&game.asura.field_discipline.opening===2')
                                assert engine._load(g.id).player.asura_cultivation['discipline_plan']['opening']==2
                            assert page.locator('#asura-domain-content').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                            if route=='asura':page.screenshot(path=str(output/f'{theme}-{width}.png'))
                            click_control(page.locator('#asura-domain-toggle'))
                        # Locked plans are rejected atomically even when requested directly.
                        saved=engine._load(g.id);saved.player.asura_cultivation.update(route='deva',level=2,discipline_plan={});engine.store.save(saved)
                        page.evaluate('id=>loadGame(id)',g.id);navigation_locator(page,'[data-panel-target=asura-domain]').click()
                        page.wait_for_function('game.asura.level===2&&document.querySelector("option[value=judgment]")?.disabled')
                        frozen=engine.store._path(g.id).read_bytes()
                        assert page.request.post(base+f'/api/games/{g.id}/asura',data=dict(action='set_field_plan',target_id='mode:judgment',expected_level=2)).status==400
                        assert engine.store._path(g.id).read_bytes()==frozen
                        click_control(page.locator('#asura-domain-toggle'))
                        # Production combat and actual report navigation, including blood payment.
                        saved=engine._load(g.id);saved.player.asura_cultivation.update(discipline_plan={'mode':'blood'})
                        prepare_combat(engine,saved);page.evaluate('id=>loadGame(id)',g.id)
                        navigation_locator(page,'#battle-report-open').click()
                        page.locator('#battle-round-list section').first.wait_for(state='attached');reveal_subpage(page,page.locator('#battle-round-list'))
                        if not page.locator('.battle-round-details').evaluate('n=>n.open'):click_control(page.locator('.battle-round-details>summary'))
                        text=page.locator('#battle-round-list').inner_text()
                        assert '歃血' in text and '六臂' in text and '实扣肉身完整度' in text,text[-2000:]
                        assert not errors,errors
                        results.append(dict(theme=theme,width=width,all_eight_routes=True,unlocks=[2,4,7],stale_safe=True,
                            paid_once=True,plans_free=True,locked_atomic=True,melody_opening=True,battle_text=True,no_overflow=True))
                        page.close()
                    browser.close()
            finally:http.shutdown();http.server_close()
    (output/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
    print('Eightfold UI passed: all routes, 2/4/7 paid unlocks, stale/locked plans, free selection, real battle text; three layouts/themes.')


if __name__=='__main__':main()
