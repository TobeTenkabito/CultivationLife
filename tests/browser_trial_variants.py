"""Nine real ascension choices, visual-only random picks, replay and reload stability."""
import hashlib,json,sys,tempfile,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.rules import max_hp,max_mp,opportunity_required
from cultivation_life.ui_preferences import write_ui_preferences


def main():
    out=ROOT/'build/domain-refinements';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);engine=GameEngine(ROOT,root/'saves')
        write_ui_preferences(root,{'pixel_art':True,'reduced_motion':True})
        identity=engine.create_game('天劫演绎','otherworld','dao',912,preset_id='mahayana')['id']
        game=engine.store.load(identity);p=game.player;p.realm_index=8;p.layer=9;p.opportunity=opportunity_required(p)
        p.karma=p.heart_demon=0;p.faction_combat_bonus=100_000_000;p.hp=max_hp(p);p.mp=max_mp(p)
        game.settings.update(silent_events=True,combat_popup=False);engine.store.save(game)
        engine.begin_celestial_ascension(identity)
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',root):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    b=pw.chromium.launch();page=b.new_page(viewport=dict(width=1440,height=1000),reduced_motion='reduce')
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    # Controlled OS-entropy port covers all choices without probabilistic tests.
                    page.add_init_script('window.__visualPick=0;crypto.getRandomValues=a=>{a[0]=window.__visualPick;return a;}')
                    page.goto(f'http://127.0.0.1:{http.server_port}');page.wait_for_function('!!configData');page.evaluate('GameThemes.ready')
                    page.evaluate('id=>loadGame(id)',identity)
                    try:page.wait_for_selector('#event-cinematic canvas',state='visible',timeout=8000)
                    except Exception:
                        print(errors);print(page.evaluate('({visual:document.documentElement.dataset.visual,body:document.body.className,scene:EventScenes.inspect(),event:game.pending_event?.id,trial:game.trial,toast:document.querySelector("#toast")?.textContent})'));raise
                    names=['cloud-stairs','lotus-sky','forked-storm','heaven-gate','cloud-stairs','violet-net','lotus-sky','heaven-gate','gold-lances']
                    picks=[0,1,0,2,0,1,1,2,2];seen=set()
                    for i,name in enumerate(names):
                        if i<8:page.evaluate('n=>window.__visualPick=n',picks[i+1])
                        page.locator('#event-choices button').first.click();page.wait_for_function('!busy')
                        page.wait_for_function('n=>EventScenes.inspect().variant===n',arg=name)
                        assert '已结算' in page.locator('.event-cinematic-caption').inner_text(),page.locator('.event-cinematic-caption').inner_text()
                        before=engine.store._path(identity).read_bytes()
                        page.locator('#event-cinematic button').filter(has_text='重播').click();page.wait_for_timeout(1680)
                        page.locator('#event-cinematic button').filter(has_text='暂停').click()
                        assert page.evaluate('EventScenes.inspect().variant')==name
                        page.locator('#event-cinematic canvas').screenshot(path=str(out/f'event-{name}.png'))
                        assert engine.store._path(identity).read_bytes()==before
                        seen.add(name)
                    final=engine.store.load(identity)
                    assert final.player.realm_index==9 and final.player.world=='celestial' and not final.active_trial
                    assert len(seen)==6 and not errors,errors
                    page.locator('#event-cinematic button').filter(has_text='收起动画').click()
                    assert not page.evaluate('EventScenes.inspect().frame')
                    b.close()
            finally:http.shutdown();http.server_close()
    result=dict(status='passed',real_choices=9,variants=sorted(seen),readonly_replay=True)
    result['source_sha256']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['web/tribulation-effects.js','web/event-scenes.js']}
    (out/'trial-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(result)


if __name__=='__main__':main()
