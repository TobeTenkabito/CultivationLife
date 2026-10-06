"""Unseen mirror -> resident discovers and enters -> first player entry -> shared research."""
import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.rules import max_hp, max_mp
from test_heavens_autonomy import annual
from test_heavens_mirror_discovery import undiscovered


def main():
    output = ROOT/'build/heavens-mirror-discovery-browser'
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        engine=GameEngine(ROOT,root/'saves')
        key=engine.create_game('镜廊相逢','supreme_metal','dao',4242,preset_id='core')['id']
        game=engine.store.load(key)
        p=game.player
        p.world,p.location_id,p.realm_index='human','wudi_plain',4
        p.hp,p.mp=max_hp(p),max_mp(p)
        p.lifespan,p.next_tribulation_age=None,999999
        game.settings['silent_events']=True
        engine.store.save(game)
        original_people=game.world_npcs
        site=(engine,game,engine._dependencies.heavens)
        _,identity=undiscovered(site)
        saved=annual(site,3)
        saved.world_npcs.update(original_people)
        saved.player.location_id='muling_desert'
        engine.store.save(saved)
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',root):
            httpd=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
            threading.Thread(target=httpd.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(headless=True)
                    page=browser.new_page(viewport={'width':1440,'height':1050})
                    errors=[]
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('window.GameThemes && configData')
                    page.evaluate('async id=>{await loadGame(id)}',key)
                    page.locator('[data-panel-target=heavens]').click()
                    assert '访古客' not in page.locator('#heavens-content').inner_text()
                    assert not page.evaluate('game.heavens.mirror.known')
                    assert engine.store.load(key).heavens_state['runtime']['mirror']['capacity_pending']
                    assert page.evaluate('game.heavens.mirror.survey.status')=='unmet'
                    page.get_by_role('tab',name='异象',exact=True).click()
                    page.get_by_role('button',name='查看镜律场域',exact=True).click()
                    def act(label,years):
                        disk=engine.store._path(key).read_bytes()
                        seq=page.evaluate('game.heavens.next_command_seq')
                        page.get_by_role('button',name=label,exact=True).click()
                        page.locator('#game-confirm-backdrop:not(.hidden)').wait_for()
                        assert f'{years} 年' in page.locator('#game-confirm-body').inner_text()
                        assert engine.store._path(key).read_bytes()==disk
                        page.locator('#game-confirm-accept').click()
                        page.wait_for_function('seq=>!busy && game.heavens.next_command_seq===seq+1',arg=seq)
                    expected_capacity=max_mp(engine.store.load(key).player)*.25
                    act('进入镜律场域',0)
                    created=engine.store.load(key).heavens_state['runtime']['mirror']
                    assert created['mana_capacity']==expected_capacity and 'capacity_pending' not in created
                    page.get_by_role('tab',name='同勘',exact=True).click()
                    assert '自行探访' in page.locator('[data-survey]').inner_text()
                    assert page.get_by_role('button',name='商请结束勘察',exact=True).is_disabled()
                    disk=engine.store._path(key).read_bytes()
                    for theme in 'abdf':
                        page.locator('#theme-open').click()
                        page.locator(f'[data-theme-picker=dialog] [data-theme-choice={theme}]').click()
                        page.evaluate('GameThemes.saved')
                        page.locator('[data-close-dialog=theme-dialog]').click()
                        for width in (1440,393):
                            page.set_viewport_size({'width':width,'height':1050 if width==1440 else 852})
                            page.locator('[data-survey] h3').scroll_into_view_if_needed()
                            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),(theme,width)
                            assert page.locator('#heavens-content').evaluate('(el)=>el.scrollWidth<=el.clientWidth+1'),(theme,width)
                            assert page.get_by_role('button',name='低耗破解',exact=True).count()==0
                            page.screenshot(path=str(output/f'{theme}-{width}.png'))
                    assert engine.store._path(key).read_bytes()==disk
                    visits=0
                    while engine.store.load(key).world_npcs[identity].affinity<20:
                        if visits: act('等候一年',1)
                        page.get_by_role('button',name='前往交往页交流',exact=True).click()
                        page.locator('#npc-contacts .contact-detail h3').wait_for(state='visible')
                        assert page.locator('#npc-contacts .contact-detail h3').inner_text()=='访古客'
                        affinity=engine.store.load(key).world_npcs[identity].affinity
                        page.locator('#npc-contacts [data-contact-action=improve]').click()
                        page.wait_for_function('args=>!busy && game.world_npcs.find(n=>n.id===args[0]).affinity>args[1]',arg=[identity,affinity])
                        page.locator('[data-panel-target=heavens]').click()
                        visits+=1
                        assert visits<=5
                    while engine.store.load(key).heavens_state['runtime']['mirror']['survey']['phase']=='studying':
                        act('等候一年',1)
                    act('交换勘察笔记',0)
                    act('等候一年',1)
                    page.reload()
                    page.wait_for_function('window.GameThemes && configData')
                    page.evaluate('async id=>{await loadGame(id)}',key)
                    if not page.locator('#heavens-card').is_visible():page.locator('[data-panel-target=heavens]').click()
                    page.get_by_role('tab',name='机关',exact=True).click()
                    act('低耗试探',2)
                    assert page.locator('#heavens-detail-body').count()==1
                    assert page.locator('#heavens-chamber-body').count()==1
                    assert page.locator('#heavens-chamber-0').get_attribute('aria-controls')=='heavens-chamber-body'
                    act('低耗破解',2)
                    saved=engine.store.load(key)
                    assert saved.world_npcs[identity].world=='human'
                    assert saved.world_npcs[identity].location_id=='muling_desert'
                    assert saved.heavens_state['runtime']['mirror']['paid_mana']>0
                    assert len(saved.player.formation_materials)==1
                    # A second actual world-year encounter reveals the entrance
                    # before anyone asks the player to enter or anchor capacity.
                    key=engine.create_game('沙中会面','supreme_metal','dao',4242,preset_id='core')['id']
                    surface=engine.store.load(key)
                    surface.player.world,surface.player.realm_index='human',4
                    surface.player.hp,surface.player.mp=max_hp(surface.player),max_mp(surface.player)
                    surface.player.lifespan,surface.player.next_tribulation_age=None,999999
                    surface.settings['silent_events']=True
                    original_people=surface.world_npcs
                    engine.store.save(surface)
                    site=(engine,surface,engine._dependencies.heavens)
                    undiscovered(site)
                    surface=engine.store.load(key)
                    surface.player.location_id='muling_desert'
                    engine.store.save(surface)
                    surface=annual(site)
                    surface.world_npcs.update(original_people)
                    engine.store.save(surface)
                    page.evaluate('async id=>{await loadGame(id)}',key)
                    page.evaluate("HeavensPanel.openTarget('mirror_field')")
                    page.get_by_role('tab',name='入口',exact=True).click()
                    assert '首次亲自入场' in page.locator('#heavens-content').inner_text()
                    assert '已知入口' in page.locator('#heavens-content').inner_text()
                    assert '可重访' not in page.locator('#heavens-content').inner_text()
                    before=engine.store._path(key).read_bytes()
                    page.get_by_role('tab',name='同勘',exact=True).click()
                    page.get_by_role('tab',name='入口',exact=True).click()
                    page.get_by_role('button',name='进入镜律场域',exact=True).click()
                    page.locator('#game-confirm-backdrop:not(.hidden)').wait_for()
                    assert engine.store._path(key).read_bytes()==before
                    page.locator('#game-confirm-cancel').click()
                    assert engine.store.load(key).heavens_state['runtime']['mirror']['mana_capacity']==0
                    page.screenshot(path=str(output/'surface-entrance-393.png'))
                    assert not errors,errors
                    (output/'report.json').write_text(json.dumps(dict(themes=list('abdf'),widths=[1440,393],
                        hidden_before_meeting=True,first_entry_anchors_capacity=True,surface_meeting_preview_pure=True,
                        real_social_contacts=visits,reload=True,unique_material=True,errors=errors),indent=2),encoding='utf-8')
                    browser.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
    print('Independent mirror discovery browser checks passed')


if __name__=='__main__':main()
