"""Actual body unlock, paid light training, stale recovery and battle text."""
import sys,tempfile,threading
from dataclasses import asdict
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item,max_hp,max_mp
from cultivation_life.runtime import decode_rng,encode_rng
from cultivation_life.system.divine_lights import definitions
from cultivation_life.system.combat.contracts import VoisinageDefinition,VoisinageEffect
from scripts.browser_navigation import navigation_locator,click_control,reveal_subpage


def prepare_battle(e,g):
    g.pending_event=None;g.settings.update(combat_popup=False,silent_events=True)
    g.player.hp=max_hp(g.player)*.6;g.player.mp=max_mp(g.player)
    field=VoisinageDefinition('light-proof','神光演武域','light-proof',1,100,3,2,
        'strike',3,.08,authority=100,stability=200,
        effects=(VoisinageEffect('strike',3,.08),VoisinageEffect('restore_body',3,.12,target='self')))
    state=dict(version=1,conversion=1,capacity=1000,current=1000,force_tier=2,attack_cost=1,
               voisinage_ids=[field.id],attainments={field.attainment:1},plan={'stance':'press'})
    g.player.transcendence=dict(state)
    target=dict(target_name='神光演武',target_power=e._player_battle_power(g),target_realm_index=9,target_layer=1,
        kind='environment',combat_type='cultivator',max_rounds=3,transcendence=dict(state),
        voisinages=[asdict(field)],static_resource_ids=['enemy-0'])
    rng=decode_rng(g.seed,g.rng_state);e._combat(g,target,False,rng);g.rng_state=encode_rng(rng)
    assert g.last_combat_report and g.last_combat_report.get('rounds'),g.last_combat_report
    e.store.save(g)


def main():
    output=ROOT/'build/divine-lights-browser';output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='five-lights-ui-') as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for theme,width,height in [('light',1440,1000),('dark',390,844),('light',754,365)]:
                        made=engine.create_game('五色神光验收','supreme_metal','dao',350,preset_id='true_immortal')
                        g=engine._load(made['id']);g.pending_event=None;g.player.next_tribulation_age=None
                        g.player.immortal_body.update(level=9,manuals=['jade_marrows'],active_manual='jade_marrows',failures=100)
                        for key in ('immortal_jade_herb','nine_leaf_immortal_lingzhi'):add_item(g.player,key,10000)
                        add_item(g.player,'great_sun_divine_light',20);engine.store.save(g)
                        page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce');errors=[]
                        page.on('pageerror',lambda error:errors.append(str(error)))
                        base=f'http://127.0.0.1:{http.server_port}';page.goto(base);page.wait_for_function('!!configData&&!busy')
                        page.locator('#theme-open').click();pixel=theme in ('light','dark')
                        page.locator(f'#theme-dialog [data-pixel-theme-choice={theme}]').click()
                        page.locator('[data-close-dialog=theme-dialog]').click();page.evaluate('GameThemes.saved')
                        page.evaluate('id=>loadGame(id)',g.id)
                        assert page.evaluate('!game.golden_light.available')
                        navigation_locator(page,'[data-panel-target=immortal-body]').click()
                        click_control(page.get_by_role('button',name='以仙药淬炼下一层',exact=True))
                        page.wait_for_function('!busy&&game.golden_light.available&&game.golden_light.body_level===10')
                        click_control(page.locator('#immortal-body-toggle'))
                        navigation_locator(page,'[data-panel-target=golden-light]').click()
                        page.locator('[data-divine-light-train=kun]').wait_for()
                        assert page.locator('.divine-light-card.locked').count()==4
                        payload=dict(action='train_divine_light',axis='kun',expected_level=0)
                        response=page.request.post(base+f'/api/games/{g.id}/immortal-action',data=payload);assert response.status==200
                        with page.expect_response(lambda r:r.url.endswith('/immortal-action')) as stale:
                            click_control(page.locator('[data-divine-light-train=kun]'))
                        assert stale.value.status==400
                        page.wait_for_function('!busy&&game.golden_light.lights[0].level===1')
                        assert page.locator('[data-divine-light-train=kun]').is_disabled()
                        saved=engine._load(g.id)
                        assert next(i.quantity for i in saved.player.inventory if i.id=='great_sun_divine_light')==12
                        click_control(page.locator('#golden-light-toggle'))
                        saved.player.immortal_body['level']=50
                        for row in definitions():
                            for key in row['recipe']:add_item(saved.player,key,10000)
                        engine.store.save(saved);page.evaluate('id=>loadGame(id)',g.id)
                        navigation_locator(page,'[data-panel-target=golden-light]').click()
                        assert page.locator('.divine-light-card.locked').count()==0
                        assert page.locator('#golden-light-content[data-body-family=immortal] .body-cultivation-stages li').count()==5
                        assert page.locator('#golden-light-content [role=meter]').count()==5
                        path=engine.store._path(g.id);snapshot=path.read_bytes()
                        assert page.locator('#golden-light-card').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                        assert page.locator('#golden-light-card').evaluate("n=>{const h=n.querySelector('h2').getBoundingClientRect(),r=n.getBoundingClientRect();return h.top>=r.top&&h.bottom<=r.bottom}")
                        page.screenshot(path=str(output/f'{theme}-{width}.png'),animations='disabled')
                        assert path.read_bytes()==snapshot
                        click_control(page.locator('#golden-light-toggle'))
                        prepare_battle(engine,engine._load(g.id));page.evaluate('id=>loadGame(id)',g.id)
                        navigation_locator(page,'#battle-report-open').click()
                        page.wait_for_selector('#battle-round-list section',state='attached')
                        reveal_subpage(page,page.locator('#battle-round-list'))
                        if not page.locator('.battle-round-details').evaluate('n=>n.open'):
                            click_control(page.locator('.battle-round-details>summary'))
                        text=page.locator('#battle-round-list').inner_text()
                        assert all(row['name'] in text for row in definitions()),text
                        assert '概率' in text and '离上朱光随' in text,text
                        assert not errors,errors
                        page.close();print(f'{theme} {width}x{height}: real tenth body layer, paid light, stale recovery, locked/capped state, unchanged viewing save and actual battle text passed',flush=True)
                    browser.close()
            finally:http.shutdown();http.server_close()


if __name__=='__main__':main()
