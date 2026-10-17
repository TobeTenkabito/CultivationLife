"""Real equip, root supplement and manual-upgrade clicks; one browser process."""
import copy
import json
import random
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
from cultivation_life.content_registry import ITEM_CATALOG, TECHNIQUE_CATALOG
from cultivation_life.rules import acquire_technique, add_technique_copy, add_item
from scripts.browser_navigation import navigation_locator, click_control


def main():
    output=ROOT/'build/common-techniques-browser';output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='common-techniques-ui-') as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(args=['--disable-gpu','--renderer-process-limit=1','--js-flags=--max-old-space-size=128'])
                    try:
                        for width,height,theme in [(1280,1000,'a'),(430,920,'f')]:
                            made=engine.create_game('合根参玄','supreme_metal','dao',71681)
                            game=engine._load(made['id']);game.pending_event=None
                            game.player.spirit_root='supreme_metal';game.player.additional_roots=[]
                            game.player.realm_index=4;game.player.layer=1
                            art=copy.deepcopy(TECHNIQUE_CATALOG['TECH_OPEN_SONGCHUANG_METAL_WATER_MAIN'])
                            acquire_technique(game.player,art);add_technique_copy(game.player,art)
                            manual=ITEM_CATALOG['jinque_water']
                            add_item(game.player,manual.id)
                            add_item(game.player,'spirit_stone',10000)
                            engine._ensure_market(game,random.Random(7))
                            rare=TECHNIQUE_CATALOG['TECH_OPEN_SONGCHUANG_WIND_YIN_YANG_MAIN']
                            ordinary=TECHNIQUE_CATALOG['TECH_OPEN_SONGCHUANG_METAL_COMBAT']
                            for identity,t in [('old-rare-art',rare),('ordinary-art',ordinary)]:
                                game.market_offers.append(dict(id=identity,kind='technique',content_id=t.id,
                                    name=t.name,description='坊市传承玉简',element=t.element,price=100,tier=1,
                                    tier_name='练气',market_name='书坊',world=game.player.world,
                                    location_id=game.player.location_id,sold=False,locked=False))
                            engine.store.save(game)
                            page=browser.new_page(viewport=dict(width=width,height=height),reduced_motion='reduce')
                            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                            page.goto(f'http://127.0.0.1:{http.server_port}')
                            page.wait_for_function('!!configData')
                            page.evaluate('async id=>loadGame(id)',game.id)
                            page.evaluate('t=>document.documentElement.dataset.theme=t',theme)
                            navigation_locator(page,'[data-panel-target=market]').click()
                            assert page.locator('.market-buy[data-offer-id="old-rare-art"]').count()==0
                            before=page.evaluate('game.market.spirit_stones')
                            # Render a previously fetched shelf through the real UI, then submit its stale button.
                            page.evaluate('offer=>{game.market.offers.push(offer);renderMarket(game.market)}',
                                dict(id='old-rare-art',kind='technique',content_id=rare.id,name=rare.name,
                                     price=100,tier_name='练气',description='旧坊市页面',compatible=True,
                                     sold=False,locked=False,market_group='general'))
                            with page.expect_response(lambda response:response.url.endswith('/market-buy')) as rejected:
                                click_control(page.locator('.market-buy[data-offer-id="old-rare-art"]'))
                            assert rejected.value.status==400
                            page.wait_for_function('!busy && !game.market.offers.some(o=>o.id==="old-rare-art")')
                            assert page.evaluate('game.market.spirit_stones')==before
                            assert not any(t.id==rare.id for t in engine._load(game.id).player.known_techniques)
                            with page.expect_response(lambda response:response.url.endswith('/market-buy')) as bought:
                                click_control(page.locator('.market-buy[data-offer-id="ordinary-art"]'))
                            assert bought.value.status==200
                            page.wait_for_function('id=>!busy && game.player.known_techniques.some(t=>t.id===id)',arg=ordinary.id)
                            assert page.evaluate('game.market.spirit_stones')==before-100
                            click_control(page.locator('#market-toggle'))
                            click_control(page.locator('.hud-identity'))
                            click_control(page.locator('.technique-library summary'))
                            row=page.locator('#known-technique-list .known-technique').filter(has_text=art.name)
                            assert '金、水（须全部具备）' in row.inner_text()
                            assert row.get_by_role('button',name='主',exact=True).is_disabled()
                            click_control(page.locator('[data-close-dialog=player-details-dialog]'))
                            navigation_locator(page,'[data-panel-target=inventory]').click()
                            item=page.locator('#inventory-card .item').filter(has_text=manual.name)
                            page.wait_for_function('document.querySelector("#inventory-card").classList.contains("panel-open")')
                            click_control(item.locator('.item-use'))
                            page.wait_for_function('!busy && game.player.additional_roots.includes("water")')
                            click_control(page.locator('#inventory-toggle'))
                            click_control(page.locator('.hud-identity'))
                            if not page.locator('.technique-library').evaluate('e=>e.open'):
                                click_control(page.locator('.technique-library summary'))
                            row=page.locator('#known-technique-list .known-technique').filter(has_text=art.name)
                            click_control(row.get_by_role('button',name='主',exact=True))
                            page.wait_for_function('id=>!busy && game.player.technique.id===id',arg=art.id)
                            click_control(row.locator('.technique-upgrade'))
                            page.wait_for_function('!busy && game.player.technique.level===2')
                            assert row.locator('.technique-growth').inner_text().startswith('下一级增益')
                            page.screenshot(path=str(output/f'combined-roots-{width}.png'))
                            saved=engine._load(game.id)
                            assert saved.player.technique.required_affinities==['metal','water']
                            assert not any(i.technique_id==art.id for i in saved.player.inventory)
                            assert not errors,errors
                            page.close()
                    finally:browser.close()
            finally:http.shutdown();http.server_close()
    (output/'result.json').write_text(json.dumps(dict(passed=True,checks=['restricted-shelf-hidden','stale-purchase-rejected','stale-page-recovered','ordinary-purchase-succeeds','all-roots-disabled','actual-root-item','live-equip','manual-consumed','upgrade-retains-roots','desktop-mobile']),indent=2),encoding='utf-8')
    print('Common elemental techniques browser passed: real supplement, equip and upgrade; desktop/mobile')


if __name__=='__main__':main()
