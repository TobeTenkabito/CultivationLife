"""Actual independent dialog, clicks, persistence and stale HTTP submissions."""
import sys,tempfile,threading,json,copy
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.models import SectNpc
from cultivation_life.rules import add_item
from cultivation_life.content_registry import TECHNIQUE_CATALOG
from scripts.browser_navigation import navigation_locator


def main():
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        g=engine.store.load(engine.create_game('培养窗口验收','supreme_metal','dao',354)['id'])
        g.pending_event=None;p=g.player;p.realm_index=4;p.layer=8;p.body_training=60;p.divine_sense_rank=45;p.opportunity=100000
        n=SectNpc('development-test','林清','弟子',2,1,30,300,world=p.world,location_id=p.location_id,
                  spirit_root='supreme_metal',body_training=10,divine_sense_rank=17,gender='female')
        g.world_npcs[n.id]=n;p.disciples=[g.link_relationship({'id':n.id})]
        for axis in ('body','sense','cultivation'):add_item(p,'npc_training_dao_'+axis+'_1',10)
        add_item(p,'spirit_stone',100)
        p.known_techniques=[copy.deepcopy(TECHNIQUE_CATALOG['TECH_BASIC_QI'])]
        engine.store.save(g)
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                base=f'http://127.0.0.1:{http.server_port}'
                with sync_playwright() as pw:
                    browser=pw.chromium.launch();page=browser.new_page(viewport=dict(width=1440,height=960))
                    errors=[];posts=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.on('request',lambda r:posts.append(r.url) if r.method=='POST' and '/api/games/' in r.url else None)
                    page.goto(base);page.wait_for_function('!!configData&&!busy')
                    page.evaluate('id=>loadGame(id)',g.id);page.wait_for_function('!busy&&!!game')
                    stocked=engine.store.load(g.id)
                    offer=next(o for o in stocked.market_offers if o.get('content_id')=='npc_training_dao_body_1' and not o.get('sold'))
                    bought=page.request.post(base+f'/api/games/{g.id}/market-buy',data={'offer_id':offer['id']})
                    assert bought.ok,bought.text()
                    assert sum(i.quantity for i in engine.store.load(g.id).player.inventory if i.id=='npc_training_dao_body_1')==11
                    replay=page.request.post(base+f'/api/games/{g.id}/market-buy',data={'offer_id':offer['id']})
                    assert replay.status==400
                    page.evaluate('id=>loadGame(id)',g.id);page.wait_for_function('!busy')
                    for width,height in ((1440,960),(390,844),(844,390)):
                        page.set_viewport_size(dict(width=width,height=height));before=engine.store.load(g.id).to_dict();count=len(posts)
                        navigation_locator(page,'[data-panel-target=npc-development]').click()
                        page.wait_for_selector('#npc-development-submit')
                        page.wait_for_function('document.querySelector("#npc-development-dialog .npc-development-art img")?.naturalWidth>0')
                        assert page.locator('#npc-development-dialog').evaluate('n=>{const r=n.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth+1&&r.top>=0&&r.bottom<=innerHeight+1&&n.scrollWidth<=n.clientWidth+1}')
                        page.screenshot(path=str(ROOT/'build'/f'npc-development-{width}x{height}.png'))
                        page.get_by_role('button',name='查看林清完整立绘').click()
                        page.wait_for_selector('#npc-art-dialog[open]');page.keyboard.press('Escape')
                        assert page.locator('#npc-development-dialog').evaluate('n=>n.open')
                        page.locator('#npc-development-dialog select[aria-label=培养方向]').select_option('body')
                        page.locator('#npc-development-dialog select[aria-label=培养轮数]').select_option('5')
                        assert len(posts)==count and engine.store.load(g.id).to_dict()==before
                        page.locator('#npc-development-dialog>header button').click()
                    navigation_locator(page,'[data-panel-target=npc-development]').click();page.wait_for_selector('#npc-development-submit')
                    revision=page.request.get(base+f'/api/games/{g.id}/npc-development').json()['revision']
                    before=engine.store.load(g.id)
                    page.locator('#npc-development-submit').click();page.wait_for_function('!busy')
                    page.wait_for_function('document.querySelector("#npc-development-dialog .npc-development-quote")?.textContent.includes("已达") || document.querySelector("#npc-development-dialog .npc-development-quote")?.textContent.includes("界面")')
                    after=engine.store.load(g.id)
                    assert after.world_npcs[n.id].body_training==60
                    assert after.player.opportunity==before.player.opportunity and after.player.age==before.player.age
                    payload=dict(action='train',kind='npc',target_id=n.id,axis='body',method='material',batches=1,revision=revision)
                    response=page.request.post(base+f'/api/games/{g.id}/npc-development',data=payload)
                    assert response.status==400 and '过期' in response.text()
                    assert engine.store.load(g.id).to_dict()==after.to_dict()
                    page.locator('#npc-development-dialog select[aria-label=培养方向]').select_option('technique')
                    page.get_by_role('button',name='传授所选功法').click();page.wait_for_function('!busy')
                    page.wait_for_function('document.querySelector("#npc-development-dialog select[aria-label=传授功法]")?.options.length===0')
                    taught=engine.store.load(g.id)
                    assert taught.world_npcs[n.id].technique_levels['TECH_BASIC_QI']==1
                    assert taught.player.opportunity==after.player.opportunity
                    page.locator('#npc-development-dialog>header button').click()
                    page.evaluate('id=>loadGame(id)',g.id);page.wait_for_function('!busy')
                    navigation_locator(page,'[data-panel-target=npc-development]').click();page.wait_for_selector('.npc-development-profile')
                    assert '60' in page.locator('.npc-development-profile').inner_text()
                    verify_upper(page,engine,base)
                    verify_supply_replay(page,engine)
                    assert not errors,errors
                    browser.close()
            finally:http.shutdown();http.server_close()
    print('NPC development: desktop/mobile/landscape, original art, read-only selection, actual training, stale rejection and reload passed.')


def verify_upper(page,engine,base):
    game=engine.store.load(engine.create_game('上境培养验收','supreme_metal','dao',355,
        custom_start=dict(world='celestial',realm_index=9,layer=1))['id'])
    game.pending_event=None;p=game.player
    n=SectNpc('upper-student','上境弟子','弟子',9,8,300,None,world=p.world,location_id=p.location_id,
        spirit_root='supreme_metal',body_training=100,immortal_body_level=0,divine_sense_rank=101)
    game.world_npcs[n.id]=n;p.disciples=[game.link_relationship({'id':n.id})]
    p.puppets=[dict(id='upper-puppet',name='玄甲守卫',type='mechanical',realm_index=9,layer=1,
        body_training=100,immortal_body_level=0,divine_sense_rank=101,combat_power=10000,durability=100,alive=True)]
    for material in ('npc_training_dao_cultivation_3','npc_training_dao_conversion_3',
                     'npc_training_puppet_body_3','npc_training_puppet_energy_3','npc_training_puppet_energy_rank_7','npc_training_dao_domain_3'):add_item(p,material,10)
    for gender in ('male','female'):
        p.puppets.append(dict(id='corpse-'+gender,name='尸卫'+gender,type='corpse',gender=gender,
            realm_index=8,layer=1,body_training=100,divine_sense_rank=90,combat_power=500,alive=True))
    captive=SectNpc('art-captive','受禁修士','修士',9,1,300,None,world=p.world,location_id=p.location_id,
        gender='female',path='dao',race='human',body_training=100,divine_sense_rank=101)
    game.world_npcs[captive.id]=captive
    p.prisoners.append(game.detain_person({'id':captive.id,'combat_power':500}))
    engine.store.save(game)
    page.evaluate('id=>loadGame(id)',game.id);page.wait_for_function('!busy&&game.player.world==="celestial"')
    page.set_viewport_size(dict(width=390,height=844))
    navigation_locator(page,'[data-panel-target=npc-development]').click()
    page.wait_for_selector('[data-target-id=upper-student]');page.locator('[data-target-id=upper-student]').click()
    page.get_by_label('培养方向',exact=True).select_option('cultivation')
    page.get_by_label('培养方式',exact=True).select_option('material')
    page.get_by_label('培养轮数',exact=True).select_option('5')
    page.locator('#npc-development-submit').click()
    page.wait_for_function('!busy&&document.querySelector(".npc-development-profile")?.textContent.includes("金仙")')
    grown=engine.store.load(game.id).world_npcs[n.id]
    assert (grown.realm_index,grown.layer)==(10,4)
    page.get_by_label('培养方向',exact=True).select_option('conversion')
    page.locator('#npc-development-submit').click()
    page.wait_for_function('!busy&&document.querySelector(".npc-development-profile")?.textContent.includes("100%")')
    grown=engine.store.load(game.id).world_npcs[n.id]
    assert grown.transcendence['conversion']==1 and grown.transcendence['current']==0
    page.get_by_label('培养方向',exact=True).select_option('domain')
    page.locator('#npc-development-submit').click()
    page.wait_for_function('!busy&&document.querySelector(".npc-development-quote")?.textContent.includes("5阶")')
    grown=engine.store.load(game.id).world_npcs[n.id]
    assert max(x['level'] for x in grown.transcendence['doctrine']['progress'].values())==5
    assert grown.transcendence['current']==0
    for identity in ('upper-puppet','corpse-male','corpse-female','art-captive'):
        page.locator(f'[data-target-id={identity}]').click()
        page.wait_for_function('document.querySelector(".npc-development-art img")?.naturalWidth>0')
        page.locator('.npc-development-art button').click()
        page.wait_for_selector('#npc-art-dialog[open] .npc-art-figure')
        page.keyboard.press('Escape')
        if identity=='art-captive':assert page.locator('.npc-development-art img').get_attribute('class').find('restrained')>=0
    page.locator('[data-target-id=upper-puppet]').click()
    page.wait_for_selector('#npc-development-charge')
    revision=page.request.get(base+f'/api/games/{game.id}/npc-development').json()['revision']
    page.locator('#npc-development-charge').click()
    page.wait_for_function('!busy&&document.querySelector(".npc-development-profile")?.textContent.includes("能源耐久 100")')
    assert page.locator('#npc-development-charge').is_disabled()
    stale=page.request.post(base+f'/api/games/{game.id}/npc-development',data=dict(action='charge',
        kind='puppet',target_id='upper-puppet',revision=revision))
    assert stale.status==400
    assert sum(i.quantity for i in engine.store.load(game.id).player.inventory if i.id=='npc_training_puppet_energy_3')==9
    page.get_by_label('培养方向',exact=True).select_option('body')
    page.get_by_label('培养轮数',exact=True).select_option('1')
    page.locator('#npc-development-submit').click()
    page.wait_for_function('!busy&&document.querySelector(".npc-development-profile")?.textContent.includes("高阶肉身 2")')
    asset=engine.store.load(game.id).player.puppets[0]
    assert asset['immortal_body_level']==2 and asset['operating_energy']==100
    page.get_by_label('更换能源',exact=True).select_option('bag:npc_training_puppet_energy_rank_7')
    page.locator('#npc-development-charge').click()
    page.wait_for_function('!busy&&document.querySelector(".npc-development-profile")?.textContent.includes("凡级能源")')
    asset=engine.store.load(game.id).player.puppets[0]
    assert asset['energy_source_id']=='npc_training_puppet_energy_rank_7'
    spare=asset['energy_spares'][0]
    assert spare['source_id']=='npc_training_puppet_energy_3' and spare['durability']==100
    page.get_by_label('更换能源',exact=True).select_option('spare:'+spare['id'])
    page.locator('#npc-development-charge').click()
    page.wait_for_function('!busy&&document.querySelector(".npc-development-profile")?.textContent.includes("仙级能源")')
    assert sum(i.quantity for i in engine.store.load(game.id).player.inventory if i.id=='npc_training_puppet_energy_3')==9
    page.screenshot(path=str(ROOT/'build'/'npc-development-upper-mobile.png'))
    page.locator('#npc-development-dialog>header button').click()
    navigation_locator(page,'[data-panel-target=settings]').click()
    page.get_by_label('开启傀儡供能',exact=True).uncheck()
    page.wait_for_function('!busy&&game.settings.puppet_supply===false')
    assert not engine.store.load(game.id).player.combat_plan['puppet_supply']
    invalid=page.request.post(base+f'/api/games/{game.id}/settings',data={'setting':'puppet_supply','enabled':'false'})
    assert invalid.status==400
    page.locator('#settings-toggle').click()
    page.evaluate('id=>loadGame(id)',game.id);page.wait_for_function('!busy')
    navigation_locator(page,'[data-panel-target=settings]').click()
    assert not page.get_by_label('开启傀儡供能',exact=True).is_checked()
    assert page.get_by_label('战斗预案模式').input_value()=='auto'
    page.get_by_label('开启傀儡供能',exact=True).check()
    page.wait_for_function('!busy&&game.settings.puppet_supply===true')
    assert engine.store.load(game.id).player.combat_plan['puppet_supply']
    print('Upper NPC growth/conversion and puppet charging/body: actual mobile clicks passed.',flush=True)


def verify_supply_replay(page,engine):
    import random
    from cultivation_life.rules import combat_power,max_hp,max_mp
    page.locator('#settings-toggle').click()
    for kind,form in [('mechanical',f) for f in ('humanoid','deva','dragon','yaksha','flora','serpent','kinnara','bird')]+[('corpse','humanoid'),('living','humanoid')]:
        g=engine.store.load(engine.create_game('供能动作验收','supreme_metal','dao',871,
            custom_start=dict(world='celestial',realm_index=9,layer=1))['id'])
        g.pending_event=None;p=g.player;p.hp=max_hp(p);p.mp=max_mp(p)
        p.combat_plan=dict(manual=False,puppet_supply=False)
        p.puppets=[dict(id='tested-puppet',name='参战守卫',type=kind,form=form,gender='female',realm_index=9,layer=1,
            body_training=100,immortal_body_level=0,divine_sense_rank=101,combat_power=combat_power(p),
            durability=100,corpse_integrity=100,control=100,alive=True,operating_energy=5,
            energy_source_id='npc_training_puppet_energy_3')]
        engine._combat(g,dict(target_name='演武对手',target_power=combat_power(p)*3,target_realm_index=9,
            target_layer=1,combat_type='cultivator',max_rounds=3),False,random.Random(18))
        report=g.last_combat_report
        assert len(report['rounds'])>=2
        assert sum('tested-puppet' in r.get('voisinage',{}).get('ordinary_attacks',{}) for r in report['rounds'])==1
        engine.store.save(g)
        page.evaluate('id=>loadGame(id)',g.id);page.wait_for_function('!busy')
        navigation_locator(page,'#battle-report-open').click()
        page.wait_for_function('CombatReplay.diagnostics().active&&!document.querySelector("[data-combat-replay]").disabled')
        outcome=page.evaluate('''()=>{
          const p=CombatReplay.diagnostics();
          const slot=game.last_combat_report.visual.teams.hero.findIndex(n=>n.id==='tested-puppet');
          const turns=p.actions.filter(r=>r.side==='hero'&&r.actorIndex===slot);
          CombatReplay.seek(turns[0].start+.7);
          return {turns:turns.length,tier:turns[0].forceTier,actors:CombatReplay.diagnostics().participants};
        }''')
        assert outcome['turns']==1 and outcome['tier']==2
        assert any(a['unitId']=='tested-puppet' and a['mode']=='attack' for a in outcome['actors'])
        page.screenshot(path=str(ROOT/'build'/f'puppet-{kind}-{form}-replay.png'))
        page.keyboard.press('Escape')
    print('Mechanical/corpse/living attacks: actual battle, immortal animation and exhausted stop passed.',flush=True)


if __name__=='__main__':main()
