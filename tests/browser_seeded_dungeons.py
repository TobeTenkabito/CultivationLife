"""Real HTTP and DOM acceptance for both pixel palettes and expedition recovery."""
import sys
import copy
import re
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
from cultivation_life.rules import max_hp,max_mp
from scripts.browser_navigation import navigation_locator, click_control, reveal_subpage


def panel_view(page,name):
    tab=page.locator(f'[data-dungeon-view={name}]')
    if tab.is_visible():tab.click()


def check_workspace(page):
    result=page.evaluate('''() => {
      const card=document.querySelector('#dungeon-card'),panel=document.querySelector('#dungeon-panel');
      const frame=card.getBoundingClientRect(),actions=document.querySelector('.dungeon-actions').getBoundingClientRect();
      const exit=document.querySelector('.dungeon-retreat').getBoundingClientRect();
      return {frame:frame.toJSON(),actions:actions.toJSON(),exit:exit.toJSON(),
        overflow:card.scrollHeight-card.clientHeight,bodyOverflow:panel.scrollHeight-panel.clientHeight,
        horizontal:card.scrollWidth-card.clientWidth};
    }''')
    assert result['overflow']<=2 and result['bodyOverflow']<=2,result
    assert result['horizontal']<=1,result
    assert result['frame']['y']>=0 and result['frame']['bottom']<=page.viewport_size['height'],result
    assert result['exit']['bottom']<=result['frame']['bottom'] and result['actions']['y']>=result['frame']['y'],result
    assert result['actions']['height']>=44,result
    assert page.locator('.dungeon-scene-reading').bounding_box()['height']>=24,result
    for button in page.locator('.dungeon-actions button,.dungeon-retreat button').all():
        assert button.evaluate('''n=>{const r=n.getBoundingClientRect();return n.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));}''')
    if page.viewport_size['width']>=1100 and page.viewport_size['height']>540:
        for name in ('team','scene','manuals' if page.locator('.dungeon-manuals').is_visible() else 'journal'):
            assert page.locator('.dungeon-'+name).is_visible()
            bounds=page.locator('.dungeon-'+name).bounding_box()
            assert bounds['height']>200 and bounds['y']+bounds['height']<=result['frame']['bottom'],(name,bounds)


def check_quality_palettes(browser,engine,url,output):
    from cultivation_life.system.dungeons import generation
    for theme in ('light','dark'):
        page=browser.new_page(viewport=dict(width=1366,height=768))
        page.emulate_media(reduced_motion='reduce')
        page.goto(url);page.wait_for_function('window.GameThemes && configData')
        page.locator(f'[data-theme-picker=start] [data-pixel-theme-choice={theme}]').click()
        colors=[]
        for index,quality in enumerate(('ordinary','rare','epic','legendary')):
            game=engine.store.load(engine.create_game('险境配色验收','heavenly','dao',342,preset_id='core')['id'])
            page.evaluate('async id=>{await loadGame(id);window.UtilityPanels.open("dungeon");}',game.id)
            assert page.locator('#dungeon-card').get_attribute('data-quality')=='neutral'
            cfg=copy.deepcopy(generation.config())
            cfg['profiles'][game.player.world+':'+game.player.location_id]['weights']=[int(i==index) for i in range(4)]
            with patch.object(generation,'config',lambda:cfg):
                page.locator('[data-dungeon-action=discover]').click();page.wait_for_function('!busy && game.dungeons.used===1')
            assert page.locator('#dungeon-card').get_attribute('data-quality')=='neutral'
            page.locator('[data-dungeon-action=enter]').click();page.wait_for_function('!busy && game.dungeons.active')
            assert page.locator('#dungeon-card').get_attribute('data-quality')==quality
            check_workspace(page)
            palette=page.locator('.dungeon-actions .dungeon-button--primary').first.evaluate('n=>({fg:getComputedStyle(n).color,bg:getComputedStyle(n).backgroundColor})')
            def luminance(value):
                rgb=[float(v)/255 for v in re.findall(r'[\d.]+',value)[:3]]
                linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in rgb]
                return sum(v*w for v,w in zip(linear,(.2126,.7152,.0722)))
            lights=sorted(luminance(v) for v in palette.values())
            assert (lights[1]+.05)/(lights[0]+.05)>=4.5,palette
            colors.append(palette['bg'])
            page.screenshot(path=str(output/f'workspace-{theme}-{quality}.png'),animations='disabled')
            page.locator('[data-dungeon-action=exit]').click();page.wait_for_function('!busy && !game.dungeons.active')
            assert page.locator('#dungeon-card').get_attribute('data-quality')=='neutral'
        assert len(set(colors))==4,colors
        page.close()


def main():
    output=ROOT/'build/reviews/seeded-dungeons';output.mkdir(parents=True,exist_ok=True)
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
                    for theme in ('light','dark'):
                        for width,height in ((393,852),(1440,960)):
                            page=browser.new_page(viewport=dict(width=width,height=height))
                            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                            page.goto(f'http://127.0.0.1:{httpd.server_port}')
                            page.wait_for_function('window.GameThemes && configData')
                            page.locator(f'[data-theme-picker=start] [data-pixel-theme-choice={theme}]').click()
                            game=engine.store.load(engine.create_game('探境浏览器','heavenly','dao',341,preset_id='core')['id'])
                            game.player.realm_index=4;game.player.layer=9
                            game.player.hp=max_hp(game.player);game.player.mp=max_mp(game.player)
                            engine.store.save(game)
                            page.evaluate('async id=>{await loadGame(id);await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));}',game.id)
                            page.locator('[data-action-tab=living]').click()
                            page.locator('#mailbox-main-open').click()
                            assert not errors,errors
                            page.locator('#mailbox-card').wait_for(state='visible')
                            page.locator('#mailbox-toggle').click()
                            navigation_locator(page,'[data-panel-target=mailbox]').click()
                            assert not errors,errors
                            page.locator('#mailbox-card').wait_for(state='visible')
                            page.keyboard.press('Escape')
                            # The actual replacement entry opens a read-only view.
                            page.locator('[data-action=treasure]').click()
                            assert not engine.store.load(game.id).dungeon_state
                            page.locator('[data-dungeon-action=discover]').click()
                            page.wait_for_function('!busy && game.dungeons.used===1')
                            page.locator('[data-dungeon-action=enter]').click()
                            page.wait_for_function('!busy && game.dungeons.active')
                            assert engine.store.load(game.id).player.age==game.player.age
                            for _ in range(8):
                                choices=page.locator('#dungeon-panel [data-dungeon-action=choose]')
                                accept=choices.filter(has_text='接受同行')
                                if accept.count():
                                    accept.click();page.wait_for_function('!busy && game.dungeons.session.party_count>1');break
                                choices.filter(has_text='绕开此处').click();page.wait_for_function('!busy')
                            else:raise AssertionError('missing join encounter')
                            assert page.locator('.dungeon-person').count()>0
                            assert page.locator('.dungeon-log').filter(has_text='加入队伍').count()>0
                            assert page.locator('[role=meter]').count()>=5
                            assert page.locator('.dungeon-compare').evaluate('n=>n.open')
                            assert page.locator('.dungeon-compare .dungeon-metric').count()==3
                            check_workspace(page)
                            panel_view(page,'team')
                            page.locator('.dungeon-person > summary').first.click()
                            page.locator('[aria-label="对照一方"]').select_option(index=1)
                            page.locator('[aria-label="对照另一方"]').select_option('player')
                            panel_view(page,'journal')
                            page.locator('[aria-label="筛选境中见闻"]').select_option('实证')
                            assert page.locator('.dungeon-log').filter(has_text='加入队伍').count()>0
                            page.locator('[aria-label="筛选境中见闻"]').select_option('全部')
                            subject=page.locator('[aria-label="筛选见闻对象"]')
                            subject.select_option(index=1)
                            assert page.locator('.dungeon-log').count()>0
                            subject.select_option('')
                            panel_view(page,'team')
                            page.get_by_role('button',name='商议交药换取辨阵',exact=True).first.click()
                            page.wait_for_function('!busy && game.dungeons.session.people.some(p=>p.contract?.state==="promised")')
                            assert page.get_by_role('button',name='交付一份恢复药物',exact=True).is_disabled()
                            page.get_by_role('button',name='撤回交付约定',exact=True).click()
                            page.wait_for_function('!busy && game.dungeons.session.people.some(p=>p.contract?.state==="broken")')
                            assert 'assassinate' not in page.locator('#dungeon-panel').inner_text()
                            assert page.evaluate('document.querySelector("#dungeon-card").scrollWidth <= document.querySelector("#dungeon-card").clientWidth+1')
                            primary=page.locator('#dungeon-panel [data-choice=seize]')
                            assert primary.bounding_box()['height']>=44
                            survey=page.locator('#dungeon-panel [data-choice=survey]')
                            assert primary.evaluate('(el)=>getComputedStyle(el).backgroundColor')!=survey.evaluate('(el)=>getComputedStyle(el).backgroundColor')
                            primary.focus()
                            page.keyboard.press('Shift+Tab');page.keyboard.press('Tab')
                            assert primary.evaluate('(el)=>getComputedStyle(el).outlineStyle')=='solid'
                            page.locator('#dungeon-card').evaluate('(el)=>{el.scrollTop=0;el.querySelectorAll(".dungeon-person[open]").forEach(d=>d.open=false);}')
                            panel_view(page,'journal')
                            page.screenshot(path=str(output/f'{theme}-{width}.png'),animations='disabled')
                            panel_view(page,'manuals')
                            assert page.locator('.dungeon-manuals').is_visible()
                            check_workspace(page)
                            panel_view(page,'journal')
                            # Long histories and short laptop windows retain every action.
                            page.locator('.dungeon-log-rows').evaluate('n=>{const row=n.firstElementChild;if(row)for(let i=0;i<80;i++)n.append(row.cloneNode(true));}')
                            check_workspace(page)
                            if width==1440:
                                for size in ((1366,768),(1280,720),(1024,768),(852,393)):
                                    page.set_viewport_size(dict(width=size[0],height=size[1]))
                                    page.wait_for_timeout(120)
                                    panel_view(page,'journal');check_workspace(page)
                                    if size in ((1366,768),(1280,720)):
                                        reading=page.locator('.dungeon-scene-reading').bounding_box()
                                        factors=page.locator('.dungeon-compare').bounding_box()
                                        assert factors['y']+factors['height']<=reading['y']+reading['height']+2,(size,reading,factors)
                                    page.screenshot(path=str(output/f'{theme}-{size[0]}x{size[1]}.png'),animations='disabled')
                                    if size==(852,393):
                                        page.locator('.dungeon-actions').evaluate('''n=>{for(const label of ['拆除阵钉（法力 123456）','沿西北方绕行']){const b=n.lastElementChild.cloneNode(true);b.textContent=label;b.classList.add('layout-stress');n.append(b);}}''')
                                        check_workspace(page)
                                        page.locator('.layout-stress').evaluate_all('nodes=>nodes.forEach(n=>n.remove())')
                                page.set_viewport_size(dict(width=width,height=height));page.wait_for_timeout(120)
                            # Controlled local fixture; submit both new actions through the actual UI.
                            saved=engine.store.load(game.id);site=saved.dungeon_state['instances'][saved.dungeon_state['active']]
                            tactic='disarm' if theme=='light' else 'attune'
                            site['nodes'][site['step']].update(kind='seal',mechanism='fractured' if tactic=='disarm' else 'resonant',variant=0,risk=.1,actor=site['party'][0])
                            expected_damage=max_hp(saved.player)*.1*.4*(0 if tactic=='disarm' else .25)
                            for r in site['roles'].values():
                                r['offer_step']=99
                                if r['state']=='joined':r.update(purpose='seek',resolve=0,trust=100,caution=100)
                            engine.store.save(saved)
                            page.evaluate('async id=>{await loadGame(id);}',game.id)
                            with page.expect_response(lambda r:r.url.endswith('/dungeon-action')) as submitted:
                                page.locator('[data-choice=survey]').click()
                            assert submitted.value.ok,submitted.value.text()
                            page.wait_for_function('k=>!busy && game.dungeons.session.choices.some(c=>c.id===k)',arg=tactic)
                            hp=page.evaluate('game.player.hp')
                            with page.expect_response(lambda r:r.url.endswith('/dungeon-action')) as submitted:
                                page.locator(f'[data-choice={tactic}]').click()
                            assert submitted.value.ok,submitted.value.text()
                            page.wait_for_function('!busy')
                            assert abs(page.evaluate('game.player.hp')-(hp-expected_damage))<.01
                            assert page.locator('.dungeon-log').filter(has_text='消耗').count()>0
                            # Another tab completes a choice; this DOM must recover after one rejected POST.
                            saved=engine.store.load(game.id);site=saved.dungeon_state['instances'][saved.dungeon_state['active']]
                            old_revision=site['revision']
                            engine.dungeon_action(game.id,'choose',dict(dungeon_id=site['id'],revision=old_revision,choice='bypass'))
                            stale_button=page.locator('#dungeon-panel [data-dungeon-action=choose]').filter(has_text='绕开此处')
                            stale_button.click();page.wait_for_function('(rev)=>!busy && game.dungeons.session.revision>rev',arg=old_revision)
                            assert engine.store.load(game.id).dungeon_state['instances'][site['id']]['revision']==old_revision+1
                            assert page.locator('[data-action=rest]').is_disabled()
                            # A join request can be declined before leaving; no busy state may linger.
                            decline=page.locator('#dungeon-panel [data-dungeon-action=choose]').filter(has_text='谢绝同行')
                            if decline.count():decline.click();page.wait_for_function('!busy')
                            page.locator('[data-dungeon-action=exit]').click();page.wait_for_function('!busy && !game.dungeons.active')
                            assert engine.store.load(game.id).player.age==game.player.age
                            if theme=='light' and width==1440:
                                saved=engine.store.load(game.id)
                                npc=next(n for sect in saved.sects.values() if sect.world=='human' for n in sect.npcs if n.alive)
                                npc.location_id=saved.player.location_id;npc.encountered_player=True;npc.affinity=100
                                engine.store.save(saved)
                                page.evaluate('async id=>{await loadGame(id);}',game.id)
                                page.evaluate('window.UtilityPanels.open("dungeon")')
                                page.locator('[data-dungeon-action=discover]').click()
                                page.wait_for_function('!busy && game.dungeons.used===2')
                                page.locator('[aria-label="选择当地同行修士"]').select_option(npc.id)
                                page.get_by_role('button',name='邀请同行',exact=True).click()
                                page.wait_for_function('!busy && game.dungeons.unread>0')
                                assert page.locator('.mailbox-dot:not([hidden])').count()>=2
                                page.keyboard.press('Escape')
                                page.locator('[data-action-tab=living]').click()
                                page.locator('#mailbox-main-open').click()
                                page.locator('[data-dungeon-action=read_mail]').click()
                                page.wait_for_function('!busy && game.dungeons.unread===0')
                                assert page.locator('.mailbox-dot:not([hidden])').count()==0
                                assert page.locator('[data-dungeon-action=decline_invite]').count()==0
                                page.screenshot(path=str(output/'mailbox-light-1440.png'),animations='disabled')
                            # One-off random manual: upgrade through the existing visible button.
                            from cultivation_life.models import Technique
                            from cultivation_life.rules import add_item
                            from cultivation_life.universal_manuals import identity
                            saved=engine.store.load(game.id)
                            saved.player.known_techniques.append(Technique(id='browser:one-off',name='归澜孤本',path='dao',grade=1))
                            add_item(saved.player,identity('dao',1),1)
                            engine.store.save(saved)
                            page.keyboard.press('Escape')
                            page.evaluate('async id=>{await loadGame(id);}',game.id)
                            assert not errors,errors
                            assert page.evaluate('game.player.known_techniques.some(t=>t.id==="browser:one-off")'),page.locator('body').inner_text()[-1500:]
                            click_control(page.locator('.hud-identity'))
                            summary=page.locator('details.technique-library > summary')
                            reveal_subpage(page,summary)
                            if not summary.evaluate('n=>n.parentElement.open'):click_control(summary)
                            row=page.locator('#known-technique-list .known-technique').filter(has_text='归澜孤本')
                            assert '万能玉简' in row.inner_text()
                            click_control(row.locator('.technique-upgrade'))
                            page.wait_for_function('!busy && game.player.known_techniques.some(t=>t.id==="browser:one-off"&&t.level===2)')
                            assert row.locator('.technique-upgrade').is_disabled()
                            saved=engine.store.load(game.id);add_item(saved.player,identity('dao',1),2);engine.store.save(saved)
                            page.locator('[data-close-dialog=player-details-dialog]').click()
                            page.evaluate('async id=>{await loadGame(id);}',game.id)
                            navigation_locator(page,'[data-panel-target=inventory]').click()
                            page.locator('[data-pixel-item="universal_manual_dao_1"]').click()
                            click_control(page.locator('[data-item-id="universal_manual_dao_1"] .technique-merge'))
                            page.wait_for_function('!busy&&game.player.inventory.some(i=>i.id==="universal_manual_dao_1_lv2"&&i.quantity===1)')
                            page.keyboard.press('Escape')
                            page.locator('#inventory-card').wait_for(state='hidden')
                            click_control(page.locator('.hud-identity'))
                            summary=page.locator('details.technique-library > summary');reveal_subpage(page,summary)
                            if not summary.evaluate('n=>n.parentElement.open'):click_control(summary)
                            row=page.locator('#known-technique-list .known-technique').filter(has_text='归澜孤本')
                            click_control(row.locator('.technique-upgrade'))
                            page.wait_for_function('!busy&&game.player.known_techniques.some(t=>t.id==="browser:one-off"&&t.level===3)')

                            assert not errors,errors
                            page.close()
                    check_quality_palettes(browser,engine,f'http://127.0.0.1:{httpd.server_port}',output)
                    browser.close()
            finally:httpd.shutdown();httpd.server_close()
    print('Seeded dungeons browser passed: two themes, four quality palettes and contrast, bounded desktop/mobile/landscape workspace, five-action overflow, long logs, tabs, mailbox, subject filters, disarm/attune, real damage, jade merge/upgrades, stale recovery and busy guards')


if __name__=='__main__':main()
