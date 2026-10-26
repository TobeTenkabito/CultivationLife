"""Real HTTP loading, NPC interaction, event submission and optional social art."""
import json
import random
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.models import SectNpc
from scripts.browser_navigation import navigation_locator, reveal_subpage


def main():
    output = ROOT / 'build/npc-art'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        engine = GameEngine(ROOT, root / 'saves')
        identity = engine.create_game('人物立绘验收', 'heavenly', 'dao', 137, preset_id='core')['id']
        game = engine.store.load(identity)
        game.player.faction_id = 'tianjian'
        npc = SectNpc(id='art-generic', name='游历女修', title='散修', realm_index=1, layer=1,
                      age=26, lifespan=150, gender='female', path='demonic', race='human', world='human', affinity=10)
        game.notable_npcs[npc.id] = npc
        game.pending_event = engine._instantiate_event(engine.events_by_id['EVT_XIANG_NODE_001'], game, random.Random(1))
        engine.store.save(game)

        class Handler(server.Handler):
            def log_message(self, *args):
                pass

        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', root):
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    page = browser.new_page(viewport={'width':1440, 'height':960}, reduced_motion='reduce')
                    errors, requests, submits = [], [], []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.on('request', lambda req: requests.append(req.url))
                    page.on('request', lambda req: submits.append(req.post_data_json) if req.method == 'POST' and req.url.endswith('/choice') else None)
                    url = f'http://127.0.0.1:{httpd.server_port}'
                    page.goto(url)
                    page.wait_for_function('configData && window.GameThemes && window.NpcArt')
                    page.evaluate('GameThemes.ready')
                    page.evaluate('async id => loadGame(id)', identity)
                    assert page.locator('.roster-identity .npc-art-avatar').count() > 0

                    def toggle(value):
                        # Close utility panels through their real navigation before opening appearance.
                        for panel in page.locator('.utility-panel.panel-open').all():
                            if panel.is_visible():
                                page.locator('#' + panel.get_attribute('id').removesuffix('-card') + '-toggle').click()
                        page.locator('#theme-open').click()
                        page.locator('#theme-dialog [data-pixel-setting]').set_checked(value)
                        page.evaluate('GameThemes.saved')
                        page.locator('[data-close-dialog=theme-dialog]').click()

                    toggle(True)
                    page.locator('#npc-event-art img').wait_for(state='visible')
                    before = page.evaluate('JSON.stringify(game)')
                    saved = engine.store._path(identity).read_bytes()
                    assert page.locator('#npc-event-art img').get_attribute('data-art') == 'fixed-xiang_zhili'
                    assert page.locator('#event-choices>button').count() == 1
                    assert page.locator('#event-choices .npc-art-figure').count() == 0
                    page.locator('#npc-event-art .npc-event-person').click()
                    page.locator('#npc-art-dialog img').wait_for(state='visible')
                    assert page.locator('#npc-art-title').inner_text() == '顾长庚'
                    page.screenshot(path=str(output / 'profile-1440.png'))
                    page.keyboard.press('Escape')
                    page.screenshot(path=str(output / 'event-1440.png'))
                    # Identity matching: all fixed records, all four generic pools, changed identity, pending redraw.
                    assert page.evaluate('''() => {
                      const c=NpcArtCatalog;
                      for(const [id,key] of Object.entries(c.fixed)) {
                        const a=c.actors[key],n={id,name:'公开姓名',race:a.race,path:a.path,gender:a.gender};
                        if(NpcArt.select(n)!==key || NpcArt.select({...n,identity_known:false})!==null)return false;
                      }
                      for(const path of ['dao','demonic'])for(const gender of ['male','female']) {
                        const n={id:'stable-person',name:'甲',race:'human',path,gender,age:22},key=NpcArt.select(n);
                        if(!c.pools[`human.${path}.${gender}`].includes(key))return false;
                        if(NpcArt.select({...n,name:'乙',world:'spirit',age:300})!==key)return false;
                        for(const invalid of [{age:12},{race:'monster'},{gender:undefined},{path:'unknown'},{ghost_host_body:{id:'host'}},{transformed:true},{identity_known:false},{lineage_race:'monster'}])
                          if(NpcArt.select({...n,...invalid})!==null)return false;
                      }
                      return NpcArt.select({id:'rank_xingmu',name:'望舒',race:'human',gender:'female',path:'dao',age:99})===null;
                    }''')
                    # Runtime participant UI fixture: uses already-public rows; buttons must never submit.
                    page.evaluate("NpcArt.event({id:'visual-participants-fixture',runtime:{members:[{npc_id:'xiang_zhili'},{npc_id:'art-generic'},{npc_id:'unpublished'}]}})")
                    assert page.locator('.npc-event-participants button').count() == 2
                    page.locator('.npc-event-participants button').nth(1).click()
                    page.locator('#npc-event-art .npc-art-figure').wait_for(state='visible')
                    generic_key = page.locator('#npc-event-art .npc-art-figure').get_attribute('data-art')
                    assert generic_key.startswith('generic-') and not submits
                    page.evaluate("NpcArt.event({id:'unpublished-fixture',runtime:{npc_id:'rank_lingxi'}})")
                    assert page.locator('#npc-event-art').is_hidden()
                    page.evaluate('renderEvent()')

                    navigation_locator(page, '[data-panel-target=relationship]').click()
                    search = page.locator('#npc-contacts input[type=search]')
                    reveal_subpage(page, search)
                    search.fill('顾长庚')
                    page.locator('.contact-person').click()
                    page.locator('.contact-detail .npc-art-figure').wait_for(state='visible')
                    assert page.locator('.contact-person img').get_attribute('data-art') == 'fixed-xiang_zhili'
                    assert page.locator('.contact-seal').is_hidden()
                    assert all(b.is_disabled() for b in page.locator('.contact-action').all())
                    for width, height in [(1440,960),(390,844),(320,740)]:
                        page.set_viewport_size({'width':width,'height':height})
                        page.wait_for_timeout(200)
                        if not page.locator('#relationship-card').is_visible():
                            navigation_locator(page, '[data-panel-target=relationship]').click()
                        reveal_subpage(page, search)
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                        page.locator('.npc-art-contact-figure').click()
                        page.locator('#npc-art-dialog img').wait_for(state='visible')
                        assert page.locator('#npc-art-dialog').evaluate('d=>d.scrollWidth<=d.clientWidth+1')
                        page.screenshot(path=str(output / f'profile-{width}.png'))
                        page.keyboard.press('Escape')
                        page.wait_for_timeout(200)
                        assert page.locator('#relationship-card').is_visible()
                        page.screenshot(path=str(output / f'contacts-{width}.png'))
                    search.fill('游历女修')
                    page.locator('.contact-person').click()
                    page.locator('.contact-detail .npc-art-figure').wait_for(state='visible')
                    assert page.locator('.contact-person img').get_attribute('data-art') == generic_key
                    assert page.evaluate('JSON.stringify(game)') == before
                    assert engine.store._path(identity).read_bytes() == saved

                    toggle(False)
                    # Sect portraits are available in the original interface too.
                    assert page.locator('.roster-identity .npc-art-avatar').count() > 0
                    assert page.locator('.npc-art-contact-figure').count() == 0
                    assert page.locator('#npc-event-art').is_hidden()
                    toggle(True)
                    page.locator('#npc-event-art .npc-art-figure').wait_for(state='visible')
                    page.screenshot(path=str(output / 'event-320.png'))
                    # Real choice endpoint and original follow-through.
                    page.locator('#event-choices>button').click()
                    page.wait_for_function('!busy && !game.pending_event')
                    assert submits == [{'choice_id':'exchange','event_id':'EVT_XIANG_NODE_001'}], submits
                    result = engine.store.load(identity)
                    assert 'xiang_node_shared' in result.player.story_flags
                    assert any(i.id == 'spirit_node_info' for i in result.player.inventory)
                    assert page.locator('#npc-event-art').is_hidden()
                    navigation_locator(page, '[data-panel-target=relationship]').click()
                    reveal_subpage(page, search)
                    search.fill('游历女修')
                    page.locator('.contact-person').click()
                    old_affinity = result.notable_npcs[npc.id].affinity
                    page.locator('[data-contact-action=improve]').click()
                    page.wait_for_function('!busy && document.querySelector("[data-contact-action=improve]").disabled')
                    assert engine.store.load(identity).notable_npcs[npc.id].affinity > old_affinity
                    page.evaluate('async id => loadGame(id)', identity)
                    reveal_subpage(page, search)
                    search.fill('游历女修')
                    assert page.locator('.contact-person[data-npc-id="art-generic"] img').get_attribute('data-art') == generic_key
                    # The sect roster and social directory must present the same public person.
                    navigation_locator(page, '[data-panel-target=faction]').click()
                    roster = page.locator('#faction-roster-list')
                    reveal_subpage(page, roster)
                    member = page.evaluate('game.faction.roster.find(n=>!n.is_player && NpcArt.select(n))')
                    assert member
                    avatar = roster.get_by_role('button', name=f'查看{member["name"]}的人物卡', exact=True)
                    avatar.locator('img').wait_for(state='visible')
                    member_key = avatar.locator('img').get_attribute('data-art')
                    own_avatar = roster.get_by_role('button', name='查看自己的人物详情', exact=True)
                    own_avatar.locator('img').wait_for(state='visible')
                    assert own_avatar.locator('img').get_attribute('src') == page.locator('.pixel-portrait').get_attribute('src')
                    assert own_avatar.locator('img').get_attribute('data-art') == 'actor.human.dao.male'
                    before = page.evaluate('JSON.stringify(game)')
                    saved = engine.store._path(identity).read_bytes()
                    controls = roster.locator('.relationship-actions').evaluate_all('(rows)=>rows.map(r=>r.innerHTML)')
                    for width, height in [(1440,960),(390,844),(320,740)]:
                        page.set_viewport_size({'width':width,'height':height})
                        avatar.click()
                        page.locator('#npc-art-dialog img').wait_for(state='visible')
                        assert page.locator('#npc-art-dialog img').get_attribute('data-art') == member_key
                        page.keyboard.press('Escape')
                        assert page.locator('#faction-card').is_visible()
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                        page.screenshot(path=str(output / f'sect-roster-{width}.png'))
                        # The unchanged self-row intentionally extends 8px beyond the list.
                        assert roster.locator('.roster-row:not(.self)').evaluate_all('(rows)=>rows.every(r=>r.scrollWidth<=r.clientWidth+1)'), width
                        own_avatar.click()
                        page.locator('#player-details-dialog .pixel-details-art').wait_for(state='visible')
                        assert page.locator('.pixel-details-art canvas').get_attribute('data-actor') == 'actor.human.dao.male'
                        assert page.locator('#npc-art-dialog').is_hidden()
                        assert page.locator('#player-details-dialog').evaluate('d=>d.scrollWidth<=d.clientWidth+1')
                        page.screenshot(path=str(output / f'sect-self-{width}.png'))
                        page.keyboard.press('Escape')
                        assert page.locator('#faction-card').is_visible()
                    assert controls == roster.locator('.relationship-actions').evaluate_all('(rows)=>rows.map(r=>r.innerHTML)')
                    assert page.evaluate('JSON.stringify(game)') == before
                    assert engine.store._path(identity).read_bytes() == saved
                    toggle(False)
                    assert roster.locator('.npc-art-avatar').count() > 0
                    toggle(True)
                    navigation_locator(page, '[data-panel-target=relationship]').click()
                    reveal_subpage(page, search)
                    search.fill(member['name'])
                    assert page.locator(f'.contact-person[data-npc-id="{member["id"]}"] img').get_attribute('data-art') == member_key
                    # Failed image requests keep real text and actions accessible.
                    failure = browser.new_page(viewport={'width':390,'height':844})
                    failure.on('pageerror', lambda error: errors.append(str(error)))
                    failure.route('**/assets/pixel/social/*.png', lambda route: route.abort())
                    failure.goto(url)
                    failure.wait_for_function('configData && window.GameThemes')
                    failure.evaluate('GameThemes.ready')
                    failure.evaluate('async id => loadGame(id)', identity)
                    navigation_locator(failure, '[data-panel-target=relationship]').click()
                    fsearch = failure.locator('#npc-contacts input[type=search]')
                    reveal_subpage(failure, fsearch)
                    fsearch.fill('顾长庚')
                    failure.locator('.contact-person').click()
                    failure.wait_for_function('!document.querySelector(".npc-art-contact-figure")')
                    assert failure.locator('.contact-seal').is_visible()
                    assert failure.locator('.contact-detail h3').inner_text() == '顾长庚'
                    assert failure.locator('.contact-action').count() == 10
                    assert not errors, errors
                    browser.close()
            finally:
                httpd.shutdown()
    report = dict(status='passed',fixed=43,generic=16,viewports=[1440,390,320],real_event_submission=True,
                  real_contact_action=True,sect_roster=True,sect_self=True,viewing_preserves_save=True,hidden_identity_fallback=True,missing_images_fallback=True)
    (output / 'checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
