"""Isolated clone fixture; real existing UI, paid actions and stale rejection."""
import sys,tempfile,threading,copy,json,random
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item,combat_power,max_hp,max_mp
from cultivation_life.content_registry import TECHNIQUE_CATALOG
from scripts.browser_navigation import navigation_locator,click_control,reveal_subpage,set_theme
from test_clone_support import clone


def main():
    output=ROOT/'build'/'clone-browser';output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        g=engine.store.load(engine.create_game('分身窗口验收','supreme_metal','dao',354)['id'])
        g.pending_event=None;p=g.player;p.realm_index=4;p.layer=8;p.body_training=60;p.divine_sense_rank=45;p.opportunity=100000
        asset=clone();asset['operating_energy']=35;p.puppets=[asset]
        p.known_techniques=[copy.deepcopy(TECHNIQUE_CATALOG['TECH_BASIC_QI'])]
        for identity in ('npc_training_puppet_body_1','npc_training_puppet_energy_rank_2'):add_item(p,identity,10)
        engine.store.save(g)
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                url=f'http://127.0.0.1:{http.server_port}'
                with sync_playwright() as pw:
                    browser=pw.chromium.launch();page=browser.new_page(reduced_motion='reduce');errors=[]
                    page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto(url);page.wait_for_function('!!configData&&!busy')
                    page.evaluate('id=>loadGame(id)',g.id);page.wait_for_function('!busy&&!!game')
                    for theme in ('light','dark'):
                        click_control(page.locator('#theme-open'))
                        page.locator(f'#theme-dialog [data-pixel-theme-choice={theme}]').click()
                        page.evaluate('GameThemes.saved');page.locator('[data-close-dialog=theme-dialog]').click()
                        for width,height in ((1440,960),(390,844),(844,390)):
                            page.set_viewport_size(dict(width=width,height=height));before=engine.store.load(g.id).to_dict()
                            navigation_locator(page,'[data-panel-target=npc-development]').click()
                            click_control(page.locator('[data-target-id=clone_test]'))
                            page.wait_for_function('document.querySelector(".npc-development-art img")?.naturalWidth>0')
                            assert_clone_art(page.locator('.npc-development-art img'))
                            assert '分身' in page.locator('.npc-development-profile').inner_text()
                            assert page.locator('#npc-development-dialog').evaluate('n=>{const r=n.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth+1&&r.top>=0&&r.bottom<=innerHeight+1&&n.scrollWidth<=n.clientWidth+1}')
                            page.screenshot(path=str(output/f'{theme}-{width}.png'))
                            page.get_by_role('button',name='查看分身验收完整立绘').click()
                            assert_clone_art(page.locator('#npc-art-dialog .npc-art-figure'))
                            page.screenshot(path=str(output/f'figure-{theme}-{width}.png'))
                            page.keyboard.press('Escape')
                            assert engine.store.load(g.id).to_dict()==before
                            page.locator('#npc-development-dialog>header button').click()
                            navigation_locator(page,'[data-panel-target=captive]').click()
                            row=page.locator('#puppet-list .puppet-row').filter(has_text='分身验收')
                            reveal_subpage(page,row);row.wait_for(state='visible')
                            assert '自身战力 500' in row.inner_text()
                            assert '不计入本体与组队战力；不占队友名额' in row.inner_text()
                            assert page.evaluate('game.demonic_system.puppets[0].battle_contribution')==0
                            assert_clone_art(row.locator('.npc-art-portrait'))
                            assert row.evaluate('n=>n.scrollWidth<=n.clientWidth+1')
                            page.screenshot(path=str(output/f'power-{theme}-{width}.png'))
                            click_control(page.locator('#captive-toggle'))
                    navigation_locator(page,'[data-panel-target=npc-development]').click()
                    click_control(page.locator('[data-target-id=clone_test]'))
                    page.get_by_label('培养方向',exact=True).select_option('body')
                    page.get_by_label('培养方式',exact=True).select_option('material')
                    revision=page.request.get(url+f'/api/games/{g.id}/npc-development').json()['revision']
                    with page.expect_response(lambda r:r.url.endswith('/npc-development') and r.request.method=='POST') as response:
                        click_control(page.locator('#npc-development-submit'))
                    assert response.value.status==200;page.wait_for_function('!busy')
                    trained=engine.store.load(g.id);a=trained.player.puppets[0]
                    assert a['body_training']>10 and a['operating_energy']==35 and a['durability']==80
                    stale=page.request.post(url+f'/api/games/{g.id}/npc-development',data=dict(action='train',kind='puppet',target_id='clone_test',axis='body',method='material',batches=1,revision=revision))
                    assert stale.status==400 and engine.store.load(g.id).to_dict()==trained.to_dict()
                    with page.expect_response(lambda r:r.url.endswith('/npc-development') and r.request.method=='POST') as response:
                        click_control(page.locator('#npc-development-charge'))
                    assert response.value.status==200;page.wait_for_function('!busy')
                    charged=engine.store.load(g.id).player.puppets[0]
                    assert charged['operating_energy']==100 and charged['energy_spares'][0]['durability']==35
                    page.get_by_label('培养方向',exact=True).select_option('technique')
                    with page.expect_response(lambda r:r.url.endswith('/npc-development') and r.request.method=='POST') as response:
                        click_control(page.get_by_role('button',name='传授所选功法'))
                    assert response.value.status==200;page.wait_for_function('!busy')
                    assert engine.store.load(g.id).player.puppets[0]['main_technique_id']=='TECH_BASIC_QI'
                    assert not engine.store.load(g.id).player.party and not errors,errors
                    page.locator('#npc-development-dialog>header button').click()
                    verify_combat(page,engine,g.id,output)
                    assert not errors,errors
                    browser.close()
            finally:http.shutdown();http.server_close()
    (output/'result.json').write_text(json.dumps(dict(passed=True,themes=2,layouts=3,checks=['readonly','training','stale','energy','teaching','party']),indent=2),encoding='utf-8')
    print('Clone UI: both themes, three layouts, original paid training/energy/teaching and stale rejection passed.')


def assert_clone_art(image):
    image.wait_for(state='visible')
    assert image.evaluate('n=>{const s=getComputedStyle(n);return n.classList.contains("npc-art-clone")&&Number(s.opacity)>.4&&Number(s.opacity)<.8&&s.filter.includes("blur(")&&s.filter.includes("hue-rotate(");}')


def verify_combat(page,engine,identity,output):
    # Check actual canvas alpha, tint, soft edges and context restoration.
    assert page.evaluate('''()=>{
      const canvas=document.createElement('canvas');canvas.width=64;canvas.height=64;
      const c=canvas.getContext('2d'),v=ActorVariants.create();
      const paint=x=>{x.fillStyle='#ff0000';x.fillRect(16,16,24,24);};
      v.draw(c,paint,'clone');const center=[...c.getImageData(28,28,1,1).data],edge=c.getImageData(15,28,1,1).data[3];
      const restored=c.globalAlpha===1&&c.filter==='none';c.clearRect(0,0,64,64);v.draw(c,paint,null);
      const normal=[...c.getImageData(28,28,1,1).data];v.dispose();
      return center[3]>100&&center[3]<190&&center[2]>center[0]&&edge>0&&restored&&normal.join(',')==='255,0,0,255';
    }''')
    g=engine.store.load(identity);p=g.player;asset=p.puppets[0]
    asset.update(realm_index=p.realm_index,layer=p.layer,combat_power=combat_power(p)*.6,
        energy_source_id=f'npc_training_puppet_energy_rank_{p.realm_index}',operating_energy=100,durability=100)
    p.hp=max_hp(p);p.mp=max_mp(p);g.settings['combat_popup']=False
    engine._combat(g,dict(target_name='分身演武',target_power=combat_power(p),target_realm_index=p.realm_index,
        target_layer=p.layer,combat_type='cultivator',max_rounds=2),False,random.Random(18))
    engine.store.save(g);page.evaluate('async id=>loadGame(id)',identity);page.wait_for_function('!busy')
    before=engine.store._path(identity).read_bytes()
    for theme in ('light','dark'):
        set_theme(page,theme)
        for width,height in ((1440,960),(390,844),(844,390)):
            page.set_viewport_size(dict(width=width,height=height))
            navigation_locator(page,'#battle-report-open').click()
            page.wait_for_function('CombatReplay.diagnostics().active&&CombatReplay.diagnostics().participants.length===3')
            state=page.evaluate('CombatReplay.diagnostics()')
            assert next(r for r in state['teams']['hero'] if r['unitId']=='clone_test')['visualVariant']=='clone'
            assert not next(r for r in state['teams']['hero'] if r['unitId']=='player').get('visualVariant')
            for action in state['actions']:
                page.evaluate('n=>CombatReplay.seek(n)',(action['start']+action['end'])/2)
            page.evaluate('CombatReplay.seek(0)')
            page.locator('#battle-animation canvas').screenshot(path=str(output/f'combat-{theme}-{width}.png'))
            page.keyboard.press('Escape')
    assert engine.store._path(identity).read_bytes()==before


if __name__=='__main__':main()
