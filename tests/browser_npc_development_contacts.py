"""Real relationship shortcut and training; --save only ever works on a copy."""
import argparse
import hashlib
import random
import shutil
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
from cultivation_life.engine import GameEngine, encode_rng
from cultivation_life.relationship_records import find_person
from scripts.browser_navigation import navigation_locator, click_control


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--save', type=Path)
    parser.add_argument('--require-art', action='store_true')
    args = parser.parse_args()
    original = args.save.read_bytes() if args.save else None
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as directory:
        engine = GameEngine(ROOT, Path(directory)/'saves')
        if args.save:
            shutil.copy2(args.save, engine.store.directory/args.save.name)
            identity = args.save.stem
        else:
            result = engine.create_game('同门培养', 'supreme_metal', 'dao', 372,
                custom_start=dict(world='spirit', realm_index=8, layer=9, sect='new', body_training=100, divine_sense_rank=100))
            identity = result['id']
            game = engine.store.load(identity)
            person = engine._recruit_sect_npc(game.sects[game.player.faction_id], game.player.age, random.Random(1))
            # Reproduce an already-saved annual recruit from the affected release.
            person.location_id = person.faction_id = None
            person.body_training = 0
            person.realm_index, person.layer = 2, 1
            person.race, person.gender = 'human', 'female'
            game.player.opportunity = 100000
            game.rng_state = encode_rng(random.Random(1))
            engine.store.save(game)
        class Handler(server.Handler):
            def log_message(self, *_args): pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(directory)):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    page = browser.new_page(viewport=dict(width=1440, height=960))
                    errors = []
                    page.on('pageerror', lambda e: errors.append(str(e)))
                    base = f'http://127.0.0.1:{http.server_port}'
                    page.goto(base)
                    page.wait_for_function('!!configData&&!busy')
                    page.evaluate('id=>loadGame(id)', identity)
                    if not args.save:
                        candidate = page.evaluate('id=>game.faction.roster.find(n=>n.id===id)', person.id)
                        assert candidate and candidate.get('can_accept_disciple'), candidate
                        navigation_locator(page, '[data-panel-target=faction]').click()
                        row = page.locator('#faction-roster-list .roster-row').filter(has_text=person.name)
                        with page.expect_response(lambda r: r.url.endswith('/faction-relationship')) as response:
                            click_control(row.locator('button').filter(has_text='收徒'))
                        assert response.value.ok, response.value.text()
                        page.wait_for_function('!busy')
                    response = page.request.get(base+f'/api/games/{identity}/npc-development')
                    assert response.ok, response.text()
                    targets = response.json()['targets']
                    alive = [r for r in targets if r['kind'] == 'npc' and not r['reason']]
                    assert alive, targets
                    assert all(r['name'] != '暂不可接触的人物' for r in alive)
                    if args.require_art:
                        assert page.evaluate('''()=>{
                          for(const race of ['magnetfolk','frostfolk'])for(const gender of ['male','female'])
                          for(const path of ['dao','demonic','monster','ghost','confucian','buddhist']){
                            const n={id:'race-test',name:'同门',race,gender,path,age:30,realm_index:5};
                            if(NpcArt.select(n)!==`race.${race}.${gender}`)return false;
                            for(const change of [{identity_known:false},{age:15},{age:17},{race:'unknown'},
                              {gender:undefined},{path:'unknown'},{host_body:{id:'host'}},{possession:{}},
                              {transformed:true},{ghost_host_body:{id:'host'}},{lineage_race:'human'}])
                              if(NpcArt.select({...n,...change})!==null)return false;
                          }return true;
                        }''')
                        navigation_locator(page, '[data-panel-target=faction]').click()
                        for target in alive:
                            row = page.locator('#faction-roster-list .roster-row').filter(has_text=target['name'])
                            click_control(row.locator('.npc-art-avatar'))
                            page.wait_for_function('document.querySelector("#npc-art-dialog img")?.naturalWidth>0')
                            assert page.locator('#npc-art-title').inner_text() == target['name']
                            page.keyboard.press('Escape')
                    for width, height in [(1440, 960), (390, 844)]:
                        page.set_viewport_size(dict(width=width, height=height))
                        page.evaluate('''async id=>{await loadGame(id);
                            await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));}''', identity)
                        if not page.locator('#relationship-card').is_visible():
                            navigation_locator(page, '[data-panel-target=relationship]').click()
                        target = alive[0]
                        row = page.locator('#relationship-list .relationship-row').filter(has_text=target['name'])
                        if args.require_art:
                            assert row.locator('.npc-art-avatar img').count() == 1
                        with page.expect_response(lambda r: r.url.endswith('/npc-development')) as response:
                            click_control(row.locator('.npc-development-open'))
                        assert response.value.ok
                        page.wait_for_selector('#npc-development-submit')
                        assert page.locator('.npc-development-profile h3').inner_text() == target['name']
                        for target in alive:
                            page.locator(f'.npc-development-person[data-target-id="{target["id"]}"]').click()
                            assert page.locator('.npc-development-profile h3').inner_text() == target['name']
                            assert page.locator('#npc-development-submit').count() == 1
                            if page.locator('.npc-development-art img').count():
                                page.wait_for_function('document.querySelector(".npc-development-art img")?.naturalWidth>0')
                            else:
                                assert '暂无适用形象' in page.locator('.npc-development-art').inner_text()
                                if not args.save or args.require_art: raise AssertionError('Expected recruit illustration missing')
                        prefix = 'npc-race-art' if args.require_art else 'npc-contact-fix'
                        page.screenshot(path=str(ROOT/'build'/f'{prefix}-{width}.png'))
                        page.locator('#npc-development-dialog > header button').click()
                    # Execute an affordable real quote against the same authoritative NPC.
                    target = next((r for r in alive if any(q.get('can_train') and q['axis']=='body' and q['method']=='infuse' and q['batches']==1 for q in r['quotes'])), None)
                    assert target, 'Fixture needs an affordable body quote'
                    navigation_locator(page, '[data-panel-target=npc-development]').click()
                    page.wait_for_selector('.npc-development-person')
                    page.locator(f'.npc-development-person[data-target-id="{target["id"]}"]').click()
                    page.get_by_label('培养方向', exact=True).select_option('body')
                    page.get_by_label('培养方式', exact=True).select_option('infuse')
                    before = engine.store.load(identity)
                    old = find_person(before, target['id'])
                    with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/npc-development')) as response:
                        page.locator('#npc-development-submit').click()
                    assert response.value.ok, response.value.text()
                    page.wait_for_function('!busy')
                    after = engine.store.load(identity)
                    new = find_person(after, target['id'])
                    assert new.body_training > old.body_training
                    assert new.location_id == old.location_id and new.faction_id == old.faction_id
                    assert after.player.opportunity < before.player.opportunity
                    assert after.player.location_id == before.player.location_id
                    assert after.player.age == before.player.age and after.rng_state == before.rng_state
                    page.locator('#npc-development-dialog > header button').click()
                    page.evaluate('id=>loadGame(id)', identity)
                    assert not errors, errors
                    browser.close()
            finally:
                http.shutdown()
                http.server_close()
    if args.save:
        assert hashlib.sha256(args.save.read_bytes()).digest() == hashlib.sha256(original).digest()
    print('Contact training passed: actual recruitment/relationship shortcut, desktop/mobile portraits, original NPC settlement and reload; original save unchanged.')


if __name__ == '__main__': main()
