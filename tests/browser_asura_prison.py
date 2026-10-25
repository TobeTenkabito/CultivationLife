"""Painted optional domain: real editor, asset failure/retry and layer boundaries."""
import hashlib
import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.ui_preferences import write_ui_preferences
from fixtures.visual_additions import prepare_domain_battle
from domain_replay_acceptance import verify


def main():
    out=ROOT/'build/domain-refinements';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);engine=GameEngine(ROOT,root/'saves')
        write_ui_preferences(root,{'pixel_art':True,'reduced_motion':True})
        identity=engine.create_game('劫狱试景','supreme_metal','demonic',651,preset_id='demonic_core')['id']
        game=engine.store.load(identity);game.pending_event=None;engine.store.save(game)
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',root),patch('cultivation_life.runtime.persistence_root',return_value=root):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch();page=browser.new_page(viewport=dict(width=1440,height=1000),reduced_motion='reduce')
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    image_url='**/visual/domains/asura-prison-outline.png*'
                    page.route(image_url,lambda route:route.fulfill(status=503,body='unavailable'))
                    page.goto(f'http://127.0.0.1:{http.server_port}')
                    page.wait_for_function('!!configData');page.evaluate('GameThemes.ready')
                    page.evaluate('id=>loadGame(id)',identity)
                    before=engine.store._path(identity).read_bytes()
                    page.locator('.settings-dock [data-panel-target="settings"]').click()
                    def open_editor():
                        page.locator('[data-voisinage-editor]').click()
                        page.wait_for_function('VoisinageEditor.status().ready')
                        page.locator('#ve-outline').select_option('asura-prison')
                        page.locator('#ve-pattern').select_option('asura-prison')
                        page.locator('#ve-scene').select_option('single')
                    open_editor()
                    failed=page.locator('#ve-canvas').evaluate('c=>c.toDataURL()')
                    page.locator('#ve-cancel').click();page.unroute(image_url)
                    with page.expect_response(lambda r:'/visual/domains/asura-prison-outline.png' in r.url) as request:
                        open_editor()
                    assert request.value.status==200
                    restored=page.locator('#ve-canvas').evaluate('c=>c.toDataURL()');assert restored!=failed
                    page.locator('#ve-canvas').screenshot(path=str(out/'asura-prison-editor.png'))
                    # Sample only the motif layer: no field colour or actors can mask a missing bitmap.
                    result=page.evaluate('''() => {
                      const canvas=document.createElement('canvas');canvas.width=960;canvas.height=540;
                      const c=canvas.getContext('2d'),g={cx:480,cy:280,rx:340,ry:205};
                      function render(color,time,front=false){
                        c.clearRect(0,0,960,540);
                        const appearance=DomainFields.compose({outline:'asura-prison',pattern:'asura-prison',palette:color,control:'rings',density:75},'check');
                        DomainFields.decorations({c,f:{appearance},g,time,front,opacity:1,stroke:()=>{}});
                        return canvas.toDataURL();
                      }
                      function gate(){return Array.from(c.getImageData(360,140,200,140).data).join(',');}
                      const base=render('#91bfc9',2),gateBefore=gate(),same=render('#91bfc9',2),later=render('#91bfc9',4),gateAfter=gate(),red=render('#d5a0a0',2);
                      const alpha=Array.from(c.getImageData(0,0,960,540).data).filter((v,i)=>i%4===3&&v>0);
                      const transparent=alpha.length/(960*540)<.20&&alpha.every(a=>a<=180);
                      const outside=c.getImageData(0,0,30,30).data.every((v,i)=>i%4!==3||v===0);
                      render('#91bfc9',2,true);
                      const upper=c.getImageData(0,0,960,395).data.every((v,i)=>i%4!==3||v===0);
                      return {deterministic:base===same,animated:base!==later,gateAnimated:gateBefore!==gateAfter,transparent,tint:base!==red,outside,upper};
                    }''')
                    assert all(result.values()),result
                    page.locator('#ve-control').select_option('asura-judgment')
                    page.locator('#ve-scene').select_option('control')
                    for width,height in [(1440,1000),(390,844),(320,740)]:
                        page.set_viewport_size(dict(width=width,height=height))
                        page.locator('#ve-canvas').screenshot(path=str(out/f'asura-prison-control-{width}.png'))
                        assert page.locator('#voisinage-editor').evaluate('n=>n.scrollWidth<=n.clientWidth+1')
                    page.locator('#ve-save').click();page.wait_for_function('!VoisinageEditor.status().busy')
                    assert '已保存' in page.locator('#ve-status').inner_text()
                    page.locator('#ve-cancel').click()
                    assert engine.store._path(identity).read_bytes()==before and not errors,errors
                    report=prepare_domain_battle(engine,identity,'control')
                    assert report['visual']['domains']['player']['pattern']=='asura-prison'
                    before=engine.store._path(identity).read_bytes()
                    verify(page,identity,out,'asura-prison-battle')
                    assert engine.store._path(identity).read_bytes()==before and not errors,errors
                    record=dict(status='passed',checks=result,failed_asset_recovered=True,save_unchanged=True,
                                real_domain_battle=True,
                                renderer_sha256=hashlib.sha256((ROOT/'web/domain-motifs.js').read_bytes()).hexdigest())
                    (out/'asura-prison-validation.json').write_text(json.dumps(record,indent=2),encoding='utf8')
                    browser.close()
            finally:http.shutdown();http.server_close()
    print('Asura painted domain: real editor, failure/retry, tint, motion, clipping, save and mobile passed')


if __name__=='__main__':main()
