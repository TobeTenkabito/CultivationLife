"""Shared actual browser checks for source server and final Windows executable."""
import json
import urllib.request
import runpy
from pathlib import Path
from playwright.sync_api import sync_playwright
from scripts.browser_navigation import click_control,navigation_locator

def verify_upper_social(base,with_dlc,folder):
    def request(path,data=None):
        req=urllib.request.Request(base+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=90) as r:return json.load(r)
    config=request('/api/config')
    assert any(e['id']=='official.authored-techniques' and e['name']=='著经立道：薪火相传' for e in config['extensions'])==with_dlc
    with sync_playwright() as pw:
        browser=pw.chromium.launch();page=browser.new_page(viewport=dict(width=1440,height=960),reduced_motion='reduce')
        page.add_init_script('Object.hasOwn=undefined;')
        errors=[];posts=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda r:posts.append(r.url) if r.method=='POST' and '/api/games/' in r.url else None)
        page.goto(base);page.wait_for_function('!!configData&&!busy')
        # Exercise every actual loaded/off combination and pending restart without altering the server.
        assert page.evaluate('''()=>{
          const ids=['asura-manifestation','monster-bloodlines','ghost-reincarnation','sage-way','buddhist-dharma'];
          for(let mask=0;mask<32;mask++){
            const config={extensions:ids.map((id,i)=>({id:'official.'+id,status:mask&(1<<i)?'loaded':'disabled',next_enabled:!(mask&(1<<i))}))};
            for(const world of Object.keys(TutorialUpper.worlds)){
              const rows=TutorialUpper.build(config,{player:{world,path:'dao'}},world),text=JSON.stringify(rows);
              if(rows.length<6)return false;
              if(world==='asura' && text.includes('第一步：启用修罗显圣的魔修')!==!!(mask&1))return false;
              if(world==='nether' && text.includes('第一步：血脉进化替代普通冲关')!==!!(mask&2))return false;
              if(world==='reincarnation' && text.includes('第一步：魂蚀与修行')!==!!(mask&4))return false;
            }
          }
          return TutorialUpper.build({},null,'unknown').length===0;
        }''')
        cases=[('dao','true_immortal','celestial'),('demonic','asura_upper','asura'),('monster','nether_upper','nether'),('ghost','reincarnation_upper','reincarnation')]
        for path,preset,world in cases:
            identity=request('/api/games',dict(name='上界导览验收',path=path,spirit_root='supreme_metal',preset_id=preset,monster_species_id='serpent',seed=351))['id']
            page.evaluate('id=>loadGame(id)',identity);page.wait_for_function('!busy&&!!game')
            for width,height in [(1440,960),(390,844),(844,390)]:
                page.set_viewport_size(dict(width=width,height=height))
                before=page.evaluate('JSON.stringify(game)');count=len(posts)
                click_control(page.locator('#action-card [data-tutorial-open]'))
                page.locator('#tutorial-upper-world').select_option(world);click_control(page.locator('#tutorial-upper-start'))
                page.wait_for_selector('.tutorial-tour[data-mode=upper]:not([hidden])')
                total=page.evaluate('TutorialUpper.build(configData,game,document.querySelector("#tutorial-upper-world").value).length')
                for index in range(total):
                    page.wait_for_function('(key)=>document.querySelector(".tutorial-tour").dataset.step===key',arg=f'upper_{world}_{index}')
                    assert page.locator('.tutorial-coach').evaluate('n=>{const r=n.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth+1&&r.top>=0&&r.bottom<=innerHeight+1}')
                    if index==1:
                        page.locator('#guide-pause').click();assert not page.locator('.tutorial-tour').is_visible()
                        # Close the inspected panel before reaching the tutorial entry again.
                        page.evaluate('GameNavigation.close({restoreFocus:false});document.querySelectorAll(".utility-panel.panel-open").forEach(n=>UtilityPanels.close(n.id.replace(/-card$/,"")))')
                        click_control(page.locator('#action-card [data-tutorial-open]'));click_control(page.locator('#tutorial-upper-start'))
                        assert page.locator('.tutorial-tour').get_attribute('data-step')==f'upper_{world}_{index}'
                    click_control(page.locator('#guide-next'))
                assert not page.locator('.tutorial-tour').is_visible()
                assert page.evaluate('JSON.stringify(game)')==before and len(posts)==count
                page.evaluate('document.querySelectorAll(".utility-panel.panel-open").forEach(n=>UtilityPanels.close(n.id.replace(/-card$/,"")))')
        from cultivation_life.engine import GameEngine
        root=Path(__file__).resolve().parents[1]
        engine=GameEngine(root,Path(folder)/'data/saves')
        fixture=runpy.run_path(str(root/'tests/fixtures/body_ui_release.py'))
        fixture['prepare_npc_roster'](engine,identity)
        page.evaluate('id=>loadGame(id)',identity)
        navigation_locator(page,'[data-panel-target=faction]').click()
        for gender in ('male','female'):
            target=page.locator(f'.roster-identity img[data-art="actor.path.npc-novice-{gender}-351"]')
            from scripts.browser_navigation import reveal_subpage
            reveal_subpage(page,target.first)
            click_control(target.first)
            page.wait_for_function('document.querySelector("#npc-art-dialog img")?.naturalWidth===128')
            click_control(page.locator('#npc-art-dialog button').first)
        click_control(page.locator('#faction-toggle'))
        # Every new form is reachable, stable, and rejected for hidden/changed identities.
        await_catalog=page.evaluate('PixelLibrary.ensure(true)');assert await_catalog
        assert page.evaluate('''async()=>{
          const assets=[...Object.values(NpcExpansionCatalog).flatMap(a=>[a.figure,a.portrait]),...Object.values(PixelLibrary.catalog.assets).filter(a=>a.file.includes('/social-351/'))];
          return (await Promise.all(assets.map(a=>new Promise(resolve=>{const im=new Image();im.onload=()=>resolve(im.naturalWidth===a.size[0]&&im.naturalHeight===a.size[1]);im.onerror=()=>resolve(false);im.src=a.file;})))).every(Boolean);
        }''')
        assert page.evaluate('''()=>{
          const rows=[...Object.values(NpcExpansionCatalog).map(a=>a.form),...Object.values(PixelLibrary.catalog.assets).flatMap(a=>a.npc_forms||[])];
          for(const form of rows){
            let found=false;
            for(let i=0;i<80;i++){
              const n={id:'recruit-'+i,name:'门人',race:form.race,path:form.path==='novice'?'dao':form.path,gender:form.gender,age:form.min_age,realm_index:5};
              const key=NpcArt.select(n);if(key===form.static){found=true;if(key!==NpcArt.select({...n,world:'asura'})||NpcArt.select({...n,identity_known:false})!==null||NpcArt.select({...n,transformed:true})!==null)return false;break;}
            }
            if(!found)return false;
          }return rows.length==='''+str(14 if with_dlc else 6)+''';}''')
        # Load and click the actual new static resources via the existing public-card renderer.
        page.evaluate('''()=>{const n={id:'young-recruit',name:'新入门弟子',race:'human',path:'dao',gender:'female',age:16,realm_index:0};NpcArt.open(n,true);}''')
        page.wait_for_function('document.querySelector("#npc-art-dialog img")?.naturalWidth===128')
        assert page.locator('#npc-art-dialog img').get_attribute('data-art')=='actor.path.npc-novice-female-351'
        click_control(page.locator('#npc-art-dialog button').first)
        assert not errors,errors
        browser.close()
    print(f'Upper/social verified: four worlds, 32 DLC combinations, desktop/portrait/landscape, read-only pause/resume; DLC={with_dlc}',flush=True)
