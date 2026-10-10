"""Actual page commands and responsive military/depot/conversion projections."""
import json
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
from cultivation_life.system.economy import depot, organizations
from cultivation_life.system.economy.ledger import transfer_value
from browser_caravan_economy import prepare as prepare_caravans


from scripts.browser_navigation import navigation_locator

def prepare(engine):
    gid=prepare_caravans(engine);game=engine._load(gid)
    game.player.realm_index=4;game.player.faction_id='tianjian';game.player.faction_contribution=10
    game.player.location_id=game.sects['tianjian'].location_id
    game.pending_event=None
    for identity in ('tianjian','wanmo'):
        e=game.sects[identity];organizations.register(game,'sect',identity,e.world)
        transfer_value(game,'background:human',depot.treasury(game,e),1000000,'浏览器验收军费')
    engine._start_war(game,'sect','tianjian','wanmo',initiated_by_player=True)
    e=game.sects['tianjian'];market=game.economy_v2['markets'][f'human:{e.location_id}']
    key=next(k for k,v in depot.catalog('human').items() if v['kind']=='item' and v['tier']<=5 and market['commodities'].get(v['id'],{}).get('stock',0)>=3)
    depot.purchase(game,engine.maps,e,key,3)
    for n in depot.seniors(game,e):n.affinity=100
    engine.store.save(game)
    return gid


def main():
    output=ROOT/'build/war-logistics-browser';output.mkdir(exist_ok=True);checks=[]
    with tempfile.TemporaryDirectory() as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            httpd=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=httpd.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    for theme in 'abdf':
                        for width,height in [(1440,1000),(393,852),(852,393)]:
                            gid=prepare(engine);page=browser.new_page(viewport=dict(width=width,height=height));errors=[]
                            page.on('pageerror',lambda e:errors.append(str(e)))
                            page.goto(f'http://127.0.0.1:{httpd.server_port}');page.wait_for_function('configData && window.GameThemes')
                            page.locator(f'[data-theme-picker=start] [data-theme-choice={theme}]').click()
                            page.evaluate('async id=>loadGame(id)',gid)
                            if 'panel-open' not in page.locator('#war-card').get_attribute('class'):navigation_locator(page,'[data-panel-target=war]').click()
                            card=page.locator('.war-card').first
                            page.locator('.war-supply-card').first.wait_for(state='visible')
                            assert '敌情未明' in card.inner_text(), (errors,card.inner_text())
                            war_id=page.evaluate("game.war_system.wars.find(w=>w.player_controls && w.status==='active').id")
                            full=sum(next(w for w in engine._load(gid).wars if w['id']==war_id)['logistics']['sides']['attacker']['realm_groups'].values())
                            page.locator('[data-war-strategy=deploy_half]').first.click()
                            page.wait_for_function("id=>!busy && game.war_system.wars.find(w=>w.id===id).supply_actions.some(a=>a.action==='deploy_half' && !a.allowed)",arg=war_id)
                            assert sum(next(w for w in engine._load(gid).wars if w['id']==war_id)['logistics']['sides']['attacker']['realm_groups'].values())<full
                            assert page.locator('[data-war-strategy=deploy_half]').first.is_disabled()
                            page.locator('[data-war-strategy=scout]').first.click()
                            page.wait_for_function("id=>!busy && game.war_system.wars.find(w=>w.id===id).supply_actions.some(a=>a.action==='scout' && a.reason)",arg=war_id)
                            assert page.locator('[data-war-strategy=scout]').first.is_disabled()
                            assert page.locator('#war-card').evaluate('(n)=>n.scrollWidth<=n.clientWidth+1')
                            page.screenshot(path=str(output/f'{theme}-{width}-war.png'))
                            navigation_locator(page,'[data-panel-target=faction]').click()
                            box=page.locator('#faction-card .organization-depot');box.locator('summary').click()
                            box.get_by_role('button',name='申请一件').first.click();page.wait_for_function('!busy')
                            if box.get_attribute('open') is None:box.locator('summary').click()
                            assert '尚需推进一个行动单位' in box.inner_text()
                            assert box.get_by_role('button',name='请高层审批').is_disabled()
                            # Advance only the authoritative action clock to isolate this approval UI.
                            game=engine._load(gid);game.diplomacy_unit+=1;engine.store.save(game)
                            page.evaluate('async id=>loadGame(id)',gid)
                            if box.get_attribute('open') is None:box.locator('summary').click()
                            box.get_by_role('button',name='请高层审批').click();page.wait_for_function('!busy')
                            if box.get_attribute('open') is None:box.locator('summary').click()
                            box.get_by_role('button',name='领取物资',exact=True).click();page.wait_for_function('!busy')
                            if box.get_attribute('open') is None:box.locator('summary').click()
                            assert '已领取' in box.inner_text()
                            assert box.evaluate('(n)=>n.scrollWidth<=n.clientWidth+1')
                            page.screenshot(path=str(output/f'{theme}-{width}-depot.png'))
                            g=engine._load(gid);g.player.location_id=g.merchant_state['worlds']['human'][0]['hq'];engine.store.save(g)
                            page.evaluate('async id=>loadGame(id)',gid)
                            navigation_locator(page,'[data-panel-target=map]').click();page.get_by_role('button',name='本地市场',exact=True).click()
                            assert page.locator('.economy-good[data-supply]').count()>0
                            atlas=page.locator('.caravan-atlas')
                            assert atlas.count()==1
                            if atlas.count():
                                atlas.locator('xpath=..').evaluate('(n)=>n.open=true')
                                atlas.locator('.caravan-map-roster button').first.click()
                                assert atlas.locator('[aria-pressed=true]').count()==1
                                assert atlas.locator('svg').evaluate('(n)=>!n.innerHTML.includes("NaN")')
                                atlas.scroll_into_view_if_needed()
                            page.screenshot(path=str(output/f'{theme}-{width}-map.png'))
                            cid=engine.create_game('仙元验收','supreme_metal','dao',9921,preset_id='true_immortal')['id']
                            g=engine._load(cid);g.pending_event=None;g.heavenly_court['open_election']=None
                            g.player.immortal_conversion_stage=0;g.player.immortal_power_converted=False;g.player.opportunity=100;engine.store.save(g)
                            page.evaluate('async id=>loadGame(id)',cid)
                            # A tab still displaying the retired event must recover via
                            # the real stale-choice endpoint and preserve its reward.
                            g=engine.store.load(cid)
                            reward=engine._prepare_treasure_reward_event(g,random.Random(2))
                            old=engine._instantiate_event(engine.events_by_id['EVT_SECT_FIRST_WARNING_001'],g,random.Random(1))
                            old['id']='EVT_IMMORTAL_CONVERSION_1';old['_followup_event']=reward
                            g.pending_event=old;engine.store.save(g)
                            page.evaluate('(event)=>{game.pending_event=event;render(game);}',old)
                            page.keyboard.press('Escape')
                            page.locator('#event-choices button').first.click()
                            page.wait_for_function('(id)=>!busy && game.pending_event?.id===id',arg=reward['id'])
                            assert engine.store.load(cid).player.immortal_conversion_stage==0
                            page.locator('#event-choices button').first.click()
                            page.wait_for_function('!busy && !game.pending_event')
                            navigation_locator(page,'[data-panel-target=immortal-conversion]').click()
                            page.get_by_role('button',name='推进下一阶段',exact=True).click()
                            page.wait_for_function('!busy && game.player.immortal_conversion_stage===1')
                            assert page.get_by_role('button',name='推进下一阶段',exact=True).is_disabled()
                            assert engine.store.load(cid).player.opportunity==0
                            page.screenshot(path=str(output/f'{theme}-{width}-conversion.png'))
                            aid=engine.create_game('煞元验收','supreme_metal','demonic',9922,preset_id='asura_upper')['id']
                            g=engine._load(aid);g.pending_event=None;g.active_trial=None
                            g.player.asura_cultivation['conversion']=0;g.player.opportunity=100;engine.store.save(g)
                            page.evaluate('async id=>loadGame(id)',aid)
                            navigation_locator(page,'[data-panel-target=asura-conversion]').click()
                            page.locator('[data-asura-action=convert]').click()
                            page.wait_for_function('!busy && game.asura.conversion===1')
                            assert page.locator('[data-asura-action=convert]').is_disabled()
                            assert engine.store.load(aid).player.opportunity==0
                            assert not errors,errors
                            checks.append(dict(theme=theme,width=width,status='passed'));page.close()
                    browser.close()
            finally:httpd.shutdown();httpd.server_close()
    (output/'report.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    print('War logistics UI passed: 12 layouts; real scout/request/approval/collect; stock and caravan maps; paid conversion and retired-event recovery')


if __name__=='__main__':main()
