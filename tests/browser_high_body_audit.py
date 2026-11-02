"""Stale real buttons reject wandering cultivation and recover on all four paths."""
import json,sys,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item
from cultivation_life.system.divine_lights import definitions as lights
from cultivation_life.system.wuyun import definitions as aggregates
from cultivation_life.system.monster_body import config as monster_config
from cultivation_life.ghost_body_content import MATERIAL_IDS
from scripts.browser_navigation import navigation_locator,click_control

CASES=(('dao','true_immortal','golden-light','[data-divine-light-train=kun]','/immortal-action'),
    ('demonic','asura_upper','asura-body','[data-aggregate=se]','/asura'),
    ('monster','nether_upper','monster-body','[data-monster-change=xuanfu]','/upper-voisinage'),
    ('ghost','reincarnation_upper','ghost-body','[data-ghost-refine=wuxiang]','/upper-voisinage'))


def main():
    output=ROOT/'build/high-body-audit-browser';output.mkdir(exist_ok=True);results=[]
    with tempfile.TemporaryDirectory(prefix='body-audit-ui-') as folder:
        e=GameEngine(ROOT,Path(folder)/'saves')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',e),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for path,preset,panel,selector,endpoint in CASES:
                        made=e.create_game('炼体边界验收','supreme_metal',path,610,preset_id=preset,
                            **({'monster_species_id':'serpent'} if path=='monster' else {}))
                        g=e._load(made['id']);p=g.player;g.pending_event=None;p.next_tribulation_age=None;p.body_training=100;p.opportunity=10**12
                        p.immortal_body.update(level=50,monster={'level':50});p.asura_cultivation.update(conversion=5,body_level=50,souls=100000)
                        keys={k for row in lights() for k in row['recipe']}|{k for row in aggregates() for k in row['recipe']}|{k for row in monster_config()['mechanisms'] for k in row['recipe']}|set(MATERIAL_IDS)
                        for key in keys:add_item(p,key,10000)
                        e.store.save(g)
                        page=browser.new_page(viewport=dict(width=1440,height=1000),reduced_motion='reduce');errors=[]
                        page.on('pageerror',lambda err:errors.append(str(err)))
                        page.goto(f'http://127.0.0.1:{http.server_port}');page.wait_for_function('!!configData&&!busy')
                        page.evaluate('id=>loadGame(id)',g.id);navigation_locator(page,f'[data-panel-target={panel}]').click()
                        assert page.locator(selector).is_enabled()
                        g=e._load(g.id);g.player.spirit_state=dict(mode='wandering',body_intact=True,entered=g.player.age,
                            deadline=g.player.age+1000,address=dict(world=g.player.world,location_id=g.player.location_id,instance_id=None))
                        e.store.save(g);e.get_game(g.id);blob=e.store._path(g.id).read_bytes()
                        with page.expect_response(lambda r:r.url.endswith(endpoint)) as rejected:
                            click_control(page.locator(selector))
                        assert rejected.value.status==400;page.wait_for_function('!busy')
                        if page.locator(selector).count():assert not page.locator(selector).is_visible() or page.locator(selector).is_disabled()
                        else:assert page.locator(f'#{panel}-card').evaluate('n=>n.classList.contains("hidden")')
                        assert e.store._path(g.id).read_bytes()==blob
                        g=e._load(g.id);g.player.spirit_state={};e.store.save(g)
                        page.evaluate('id=>loadGame(id)',g.id)
                        if not page.locator(selector).is_visible():navigation_locator(page,f'[data-panel-target={panel}]').click()
                        assert page.locator(selector).is_enabled()
                        with page.expect_response(lambda r:r.url.endswith(endpoint)) as paid:
                            click_control(page.locator(selector))
                        assert paid.value.status==200;page.wait_for_function('!busy')
                        saved=e._load(g.id)
                        rank=(saved.player.immortal_body.get('divine_lights',{}).get('kun') if path=='dao' else
                            saved.player.asura_cultivation.get('aggregates',{}).get('se') if path=='demonic' else
                            saved.player.immortal_body.get('monster',{}).get('training',{}).get('xuanfu') if path=='monster' else
                            saved.player.immortal_body.get('ghost_training',{}).get('wuxiang'))
                        assert rank==1 and not errors,(path,rank,errors)
                        page.screenshot(path=str(output/f'{path}.png'));page.close()
                        results.append(dict(path=path,stale_wandering_rejected=True,no_payment_on_reject=True,button_recovered=True,paid_exactly_once=True))
                    browser.close()
            finally:http.shutdown();http.server_close()
    (output/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Four high-body paths: actual stale clicks rejected while wandering, no save mutation, return and paid-button recovery passed')


if __name__=='__main__':main()
