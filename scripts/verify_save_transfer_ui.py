"""Six-theme save UI and Web Crypto roundtrips against an isolated real server."""
import json
import sys
import tempfile
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine


class QuietHandler(server.Handler):
    def log_message(self, *args):
        pass


def main():
    with tempfile.TemporaryDirectory(dir=ROOT/'build') as directory:
        server.PERSISTENCE_ROOT = Path(directory)
        engine = server.ENGINE = GameEngine(ROOT, Path(directory)/'saves')
        made = engine.create_game('照尘·长卷验收', 'supreme_wood', 'buddhist', seed=1450,
            custom_start=dict(world='human',realm_index=4,sect='new',sect_name='长卷验收宗'))
        import importlib.util
        spec=importlib.util.spec_from_file_location('organizations_fixture',ROOT/'tests/fixtures/organizations-290.py')
        fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
        fixture.prepare(engine,made['id'])
        game=engine._load(made['id']);entity=game.sects[game.player.faction_id]
        engine.fleet_action(game.id,dict(action='heritage_learn',owner_id=entity.id,revision=entity.heritage['revision'],technique_id='TECH_HUMAN_HERITAGE_1'))
        engine.teleport_action(game.id,'build',owner_id=entity.id)
        fixture.clan(engine,game.id);game=engine._load(game.id)
        clan=next(s for s in game.sects.values() if s.kind=='family' and s.location_id==game.player.location_id and s.world=='human')
        engine.family_action(game.id,'join',dict(target_id=clan.id))
        game=engine._load(game.id)
        from cultivation_life.system.monster_civilizations import core
        if game.player.world in core.config().get('worlds', {}):
            core.activate(game)
            engine.store.save(game)
        original = json.loads(engine.store._path(game.id).read_bytes())
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        errors = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                context = browser.new_context(viewport={'width':1440,'height':1080}, has_touch=True,
                                              permissions=['clipboard-read','clipboard-write'])
                page = context.new_page(); page.on('pageerror', lambda e: errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{httpd.server_port}')
                page.wait_for_function('configData && window.SaveTransfer && document.querySelector(".save-export")')
                # Verify real random-key encryption and tamper rejection, plus chunks.
                result = page.evaluate('''async id => {
                  const snapshot = await api('/api/save-transfer/export',{method:'POST',body:JSON.stringify({id})});
                  const code = await SaveCode.encode(snapshot.payload);
                  if(await SaveCode.decode(code)!==snapshot.payload) throw Error('crypto roundtrip');
                  if(code===await SaveCode.encode(snapshot.payload)) throw Error('key reuse');
                  let rejected=false;try{await SaveCode.decode(code.slice(0,-9)+'Z'+code.slice(-8));}catch(e){rejected=true}
                  if(!rejected) throw Error('accepted tamper');
                  const parts=await SaveCode.split(code,Math.ceil(code.length/3));
                  const collector=new SaveCode.Collector();
                  if(await collector.add(parts[2])!==null) throw Error('missing pieces');
                  await collector.add(parts[2]);await collector.add(parts[0]);
                  if(await collector.add(parts[1])!==code) throw Error('chunk ordering');
                  const batch=new SaveCode.Collector();if(await batch.add(parts.join('\\n'))!==code) throw Error('batch chunks');
                  window.__transferTestCode=code;return {length:code.length,parts:parts.length};
                }''', game.id)
                assert result['parts'] == 3
                print('Codec probe:',result,flush=True)
                fixtures = ROOT/'build/transfer-fixtures'; fixtures.mkdir(exist_ok=True)
                if '--preserve-fixture' not in sys.argv:
                    (fixtures/'from-windows.txt').write_text(page.evaluate('window.__transferTestCode'), encoding='utf-8')
                    (fixtures/'from-windows.json').write_text(json.dumps(original, ensure_ascii=False), encoding='utf-8')
                for theme in 'abdf':
                    page.evaluate('(theme)=>document.querySelector(`[data-theme-picker="start"] [data-theme-choice="${theme}"]`).click()',theme)
                    page.evaluate('GameThemes.saved')
                    page.locator('.save-library').scroll_into_view_if_needed()
                    for width in (1440, 800, 412):
                        page.set_viewport_size({'width':width, 'height':1080 if width > 800 else 915})
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'), (theme,width)
                        assert page.locator('.save-export').bounding_box()['height'] >= 40
                    page.locator('.save-export').click()
                    page.wait_for_function('!SaveTransfer.isWorking() && document.querySelector("#transfer-code").value.startsWith("FSWD")')
                    page.locator('#transfer-copy').click()
                    page.wait_for_function('document.querySelector("#transfer-status").textContent.includes("已复制")')
                    page.locator('#transfer-close').click()
                    page.locator('.save-library [data-save-import]').click()
                    page.locator('#transfer-code').fill(page.evaluate('window.__transferTestCode'))
                    page.locator('#transfer-preview').click()
                    page.wait_for_function('!SaveTransfer.isWorking() && !document.querySelector("#transfer-confirm").classList.contains("hidden")')
                    assert page.locator('#transfer-import').is_disabled()
                    assert page.evaluate('document.querySelector("#save-transfer-dialog").scrollWidth<=document.querySelector("#save-transfer-dialog").clientWidth+1')
                    page.screenshot(path=str(ROOT/f'build/save-import-{theme}-1450.png'))
                    page.locator('#transfer-replace-check').check()
                    page.locator('#transfer-import').click()
                    page.wait_for_function('!SaveTransfer.isWorking() && document.querySelector("#transfer-status").textContent.includes("已恢复")')
                    assert json.loads(engine.store._path(game.id).read_bytes()) == original
                    page.locator('#transfer-close').click()
                    page.set_viewport_size({'width':1440,'height':1080})
                    page.locator('.save-library').scroll_into_view_if_needed()
                    page.screenshot(path=str(ROOT/f'build/save-library-{theme}-1450.png'))
                    page.evaluate('(id)=>loadGame(id)', game.id)
                    colours = page.evaluate('''()=>{
                      const c=s=>getComputedStyle(document.querySelector(s)).color;
                      return [c('[data-panel-target="buddhist"]'),c('[data-panel-target="buddhist-wish"]'),c('[data-panel-target="map"]')];
                    }''')
                    assert colours[0] == colours[1] and colours[0] != colours[2], (theme,colours)
                    page.evaluate('showStart()'); page.wait_for_function('!busy')
                    # Loading may migrate state. The next export must reflect that new snapshot.
                    original = json.loads(engine.store._path(game.id).read_bytes())
                    page.evaluate('''async id=>{const r=await api('/api/save-transfer/export',{method:'POST',body:JSON.stringify({id})});window.__transferTestCode=await SaveCode.encode(r.payload)}''',game.id)
                assert not errors, errors
                browser.close()
        finally:
            httpd.shutdown()
    print('Six-theme save library, import/export, AES-GCM, chunks, and Buddhist dock colours passed')


if __name__ == '__main__':
    main()
