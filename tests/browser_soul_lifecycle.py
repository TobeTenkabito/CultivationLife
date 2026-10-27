"""Real details/secret/nascent clicks, stale responses and mobile layout."""
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.models import SectNpc, Item
from cultivation_life.rules import add_item
from scripts.browser_navigation import navigation_locator, set_theme
from playwright.sync_api import sync_playwright


def main():
    output=ROOT/'build/soul-ui';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        e=GameEngine(ROOT,Path(folder)/'saves')
        g=e._load(e.create_game('身魂界面验收','supreme_metal','dao',320,preset_id='core')['id'])
        g.pending_event=None;p=g.player;p.realm_index=4;p.layer=1;p.lifespan=10000;p.divine_sense_rank=20;p.soul_energy=600
        add_item(p,'spirit_stone',100000);add_item(p,Item('test-soul-gear','验收法剑',combat_bonus=100,tags=['artifact']))
        n=SectNpc('nascent-ui','清澜','散修',4,1,30,10000,spirit_root='supreme_metal');g.world_npcs[n.id]=n
        p.prisoners.append(g.detain_person(n.to_dict()));e.store.save(g)
        class Quiet(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',e),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Quiet);threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch();page=browser.new_page(viewport=dict(width=1440,height=960));errors=[]
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    base=f'http://127.0.0.1:{http.server_port}'
                    page.goto(base);page.wait_for_function('!!configData&&!busy');page.evaluate('id=>loadGame(id)',g.id)
                    page.wait_for_function('!!game?.soul&&!busy')
                    navigation_locator(page,'[data-panel-target=secret-art]').click()
                    assert page.locator('#soul-details [data-soul-action=leave]').count()==0
                    # A stale leave click refreshes once without spending soul energy.
                    revision=page.evaluate('game.soul.revision')
                    energy=page.evaluate('game.soul.soul.current')
                    response=page.request.post(base+f'/api/games/{g.id}/soul',data=dict(action='study',id='path_ghost',revision=revision))
                    assert response.ok
                    page.locator('#soul-secrets [data-soul-action=leave]').click()
                    page.wait_for_function('r=>!busy&&game.soul.revision===r',arg=revision+1)
                    assert page.evaluate('game.soul.mode')=='普通'
                    assert page.evaluate('game.soul.soul.current')==energy
                    page.locator('#soul-secrets [data-soul-action=leave]').click();page.wait_for_function('!busy&&game.soul.mode==="神游"')
                    assert page.locator('[data-soul-action=leave]').is_disabled()
                    page.locator('#secret-art-toggle').click()
                    page.locator('.hud-identity').click()
                    page.locator('[data-soul-action=return]').click();page.wait_for_function('!busy&&game.soul.mode==="普通"')
                    page.locator('[data-close-dialog=player-details-dialog]').click()
                    navigation_locator(page,'[data-panel-target=secret-art]').click()
                    page.locator('#soul-secrets [data-soul-action=study]').first.click();page.wait_for_function('!busy&&game.soul.secrets[0].known')
                    page.locator('#secret-art-toggle').click()
                    navigation_locator(page,'[data-panel-target=nascent]').click()
                    for count in range(3):
                        page.locator('#nascent-content [data-soul-action=refine]').click()
                        page.wait_for_function('(n)=>!busy&&(game.soul.second||game.soul.refining?.years===n)',arg=count+1)
                    assert page.evaluate('game.soul.second.id')==n.id
                    wrap=page.locator('#nascent-content .soul-actions').filter(has=page.locator('[data-soul-action=equip]'))
                    wrap.locator('select').select_option('test-soul-gear');wrap.locator('button').click()
                    page.wait_for_function('!busy&&game.soul.second.equipment.length===1')
                    revision=page.evaluate('game.soul.revision')
                    response=page.request.post(base+f'/api/games/{g.id}/soul',data=dict(action='auto',revision=revision));assert response.ok
                    page.locator('[data-soul-action=auto]').click();page.wait_for_function('r=>!busy&&game.soul.revision===r',arg=revision+1)
                    assert page.evaluate('game.soul.second.auto') is False
                    page.locator('[data-soul-action=auto]').click();page.wait_for_function('!busy&&game.soul.second.auto')
                    # Control is independent and the real button restores it once.
                    current=e.store.load(g.id);current.player.nascent_state['second']['control']=49
                    e.store.save(current);page.evaluate('async id=>loadGame(id)',g.id)
                    page.wait_for_function('!busy&&game.soul.second.control===49')
                    assert '控制力 49 / 100' in page.locator('#nascent-content').inner_text()
                    assert '剩余' in page.locator('#nascent-content').inner_text()
                    page.locator('[data-soul-action=assimilate]').click()
                    page.wait_for_function('!busy&&game.soul.second.control===69')
                    for theme in ['a','b','d','f']:
                        set_theme(page,theme)
                        for width,height in [(1440,960),(390,844),(844,390),(320,740)]:
                            page.set_viewport_size(dict(width=width,height=height));page.wait_for_timeout(700)
                            if not page.locator('#nascent-card').evaluate('n=>n.scrollWidth<=n.clientWidth+2'):
                                page.screenshot(path=str(output/'overflow.png'))
                                print(page.locator('#nascent-card').evaluate('n=>({w:n.clientWidth,s:n.scrollWidth,bad:[...n.querySelectorAll("*")].filter(x=>x.scrollWidth>x.clientWidth+2).map(x=>[x.tagName,x.className,x.clientWidth,x.scrollWidth]),pseudo:["::before","::after"].map(x=>getComputedStyle(n,x).width)})'),flush=True)
                                raise AssertionError((theme,width))
                            if theme=='a':page.screenshot(path=str(output/f'nascent-{width}.png'))
                    page.locator('#nascent-toggle').click();page.locator('.hud-identity').click()
                    assert page.locator('#soul-details progress').count()==2
                    assert page.locator('#player-details-dialog').evaluate('n=>n.scrollWidth<=n.clientWidth+2')
                    page.screenshot(path=str(output/'details-320.png'))
                    page.locator('[data-close-dialog=player-details-dialog]').click()
                    # Real load drops a retired event but retains its earned follow-up.
                    import random
                    current=e.store.load(g.id)
                    reward=e._prepare_treasure_reward_event(current,random.Random(2))
                    legacy=dict(id='SYS_POST_BATTLE_POSSESSION',version=1,title='旧战陨夺舍',
                        choices=[dict(id=n.id,text='旧夺舍按钮',enabled=True)],runtime={})
                    current.pending_event=dict(legacy,_followup_event=reward)
                    e.store.save(current);page.evaluate('async id=>loadGame(id)',g.id)
                    page.wait_for_function('(id)=>!busy&&game.pending_event?.id===id',arg=reward['id'])
                    assert page.locator('#post-battle-possession').is_hidden()
                    page.locator('#event-choices button').first.click()
                    page.wait_for_function('!busy&&!game.pending_event')
                    # Emulate a browser still showing the retired button from before this fix.
                    current=e.store.load(g.id);current.player.alive=False;current.player.hp=0
                    current.player.death_reason='特殊死亡';current.pending_event=legacy;e.store.save(current)
                    page.evaluate('(old)=>{game.player.alive=false;game.pending_event=old;render(game);}',legacy)
                    page.locator('#post-battle-possession-choices button').click()
                    page.wait_for_function('!busy&&!game.player.alive&&!game.pending_event')
                    assert page.locator('#post-battle-possession').is_hidden()
                    assert not e.store.load(g.id).player.alive
                    assert not errors,errors
                    browser.close()
            finally:http.shutdown();http.server_close()
    print('Soul UI passed: real leave/return/study/refine/equip/stale recovery, four themes and 320/390/844/1440 widths')

if __name__=='__main__':main()
