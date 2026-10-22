"""Real settings clicks, preference persistence and preview-only encounter colors."""
import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.ui_preferences import load_ui_preferences


def main():
    output=ROOT/'build/voisinage-editor';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);engine=GameEngine(ROOT,root/'saves')
        game_id=engine.create_game('邻域外观验收','heavenly','dao',137,preset_id='core')['id']
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',root):
            httpd=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=httpd.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch();page=browser.new_page(viewport={'width':1280,'height':1000},reduced_motion='reduce')
                    errors,mutations=[],[]
                    page.on('pageerror',lambda e:errors.append(str(e)))
                    page.on('request',lambda r:mutations.append(r.url) if r.method=='POST' and '/api/games/' in r.url else None)
                    page.goto(f'http://127.0.0.1:{httpd.server_port}/')
                    page.wait_for_function('window.VoisinageEditor && configData')
                    page.evaluate('async id=>loadGame(id)',game_id)
                    before=engine.store._path(game_id).read_bytes()
                    state=page.evaluate('JSON.stringify(game)')
                    page.locator('.settings-dock [data-panel-target="settings"]').click()
                    page.locator('[data-voisinage-editor]').click()
                    page.wait_for_function('VoisinageEditor.status().ready')
                    assert page.evaluate('VoisinageEditor.status().paused')
                    first=page.evaluate('VoisinageEditor.status().npc')
                    for key,value in [('outline','frost'),('pattern','lotus'),('control','talismans')]:
                        page.locator('#ve-'+key).select_option(value)
                    # Native picker and HEX input synchronize; full RGB survives rendering.
                    pictures=[]
                    for color in ['#ff0000','#330000','#0000ff','#000000','#ffffff']:
                        page.locator('#ve-palette').fill(color)
                        assert page.locator('#ve-color-hex').input_value()==color.upper()
                        assert page.evaluate('DomainFields.compose(VoisinageEditor.status().draft).color')==[int(color[i:i+2],16) for i in (1,3,5)]
                        pictures.append(page.locator('#ve-canvas').evaluate('c=>c.toDataURL()'))
                    assert len(set(pictures))==5
                    page.locator('#ve-color-hex').fill('#12')
                    assert page.locator('#ve-save').is_disabled()
                    assert page.evaluate('VoisinageEditor.status().draft.palette')=='#ffffff'
                    page.locator('#ve-color-hex').fill('#89aBCd')
                    assert page.locator('#ve-palette').input_value()=='#89abcd'
                    assert page.locator('#ve-save').is_enabled()
                    page.locator('#ve-density').fill('72');page.locator('#ve-density').dispatch_event('input')
                    assert page.evaluate('VoisinageEditor.status().npc')==first
                    page.locator('#ve-save').click();page.wait_for_function('!VoisinageEditor.status().busy')
                    saved=dict(outline='frost',pattern='lotus',palette='#89abcd',control='talismans',density=72)
                    assert load_ui_preferences(root)['voisinage_appearance']==saved
                    page.locator('#ve-pattern').select_option('sword');page.locator('#ve-cancel').click()
                    frames=page.evaluate('VoisinageEditor.status().frames');page.wait_for_timeout(200)
                    assert page.evaluate('VoisinageEditor.status().frames')==frames
                    page.locator('[data-voisinage-editor]').click();page.wait_for_function('VoisinageEditor.status().ready')
                    assert page.evaluate('VoisinageEditor.status().draft')==saved
                    # Controlled entropy verifies per-encounter sampling without probabilistic assertions.
                    assert page.evaluate('''()=>{const native=crypto.getRandomValues;try{
                        crypto.getRandomValues=a=>{a[0]=0;return a;};const a=VoisinageAppearance.createEncounter([{}]);
                        crypto.getRandomValues=b=>{b[0]=11;return b;};const b=VoisinageAppearance.createEncounter([{}]);
                        return a[0].palette==='rose' && b[0].palette==='pink' && Object.isFrozen(a[0]) && a[0].palette==='rose';
                    }finally{crypto.getRandomValues=native;}}''')
                    page.locator('#ve-scene').select_option('control')
                    page.locator('#ve-next').click()
                    current=page.evaluate('VoisinageEditor.status().npc')
                    page.locator('#ve-motion').click();page.wait_for_timeout(400);page.locator('#ve-motion').click()
                    assert page.evaluate('VoisinageEditor.status().npc')==current
                    theme_names=page.evaluate('DomainFields.catalog.map(row=>row.id)')
                    assert len(theme_names)==13
                    # Outline geometry must remain independent of the chosen inner motif.
                    assert page.evaluate('''()=>{const g={cx:385,cy:286,rx:354,ry:183};
                        for(const outline of DomainFields.catalog){let expected;
                            for(const pattern of DomainFields.catalog){const style=DomainFields.compose({...VoisinageEditor.status().draft,outline:outline.id,pattern:pattern.id});
                                const values=[0,1,2,3].map(i=>DomainFields.distance(g,200+i*140,160+i*65,3.3,style));
                                if(!values.every(Number.isFinite))return false;
                                {
                                    const key=JSON.stringify(values);if(expected&&expected!==key)return false;expected=key;
                                }
                            }
                        }return true;}''')
                    new_themes=['water','mountain','wood','thunder','moon','void','time']
                    previews=set()
                    for theme in theme_names:
                        page.locator('#ve-outline').select_option(theme);page.locator('#ve-pattern').select_option(theme)
                        page.locator('#ve-canvas').screenshot(path=str(output/f'preview-{theme}.png'))
                        if theme in new_themes:
                            for scene in ['single','overlap','control']:
                                page.locator('#ve-scene').select_option(scene)
                                previews.add(page.locator('#ve-canvas').evaluate('c=>c.toDataURL()'))
                            page.locator('#ve-save').click();page.wait_for_function('!VoisinageEditor.status().busy')
                            saved=saved|{'outline':theme,'pattern':theme}
                            assert load_ui_preferences(root)['voisinage_appearance']==saved
                            page.locator('#ve-cancel').click();page.locator('[data-voisinage-editor]').click()
                            page.wait_for_function('VoisinageEditor.status().ready')
                            assert page.evaluate('VoisinageEditor.status().draft')==saved
                    assert len(previews)==21
                    page.locator('#ve-pattern').select_option('wood')
                    for width,height in [(1280,1000),(768,1024),(390,844),(320,740)]:
                        page.set_viewport_size({'width':width,'height':height})
                        assert page.locator('#voisinage-editor').evaluate('d=>d.scrollWidth<=d.clientWidth+1')
                        page.screenshot(path=str(output/f'editor-{width}.png'))
                    # Failed persistence must keep the draft and the previous server settings.
                    page.route('**/api/ui-preferences',lambda route:route.fulfill(status=500,body='{}') if route.request.method=='POST' else route.continue_())
                    page.locator('#ve-save').click();page.wait_for_function('!VoisinageEditor.status().busy')
                    assert '保存失败' in page.locator('#ve-status').inner_text()
                    assert load_ui_preferences(root)['voisinage_appearance']==saved
                    page.unroute('**/api/ui-preferences')
                    page.locator('#ve-cancel').click();page.set_viewport_size({'width':1280,'height':1000});page.reload()
                    page.wait_for_function('window.VoisinageEditor && configData')
                    page.evaluate('async id=>loadGame(id)',game_id)
                    page.locator('.settings-dock [data-panel-target="settings"]').click()
                    page.locator('[data-voisinage-editor]').click();page.wait_for_function('VoisinageEditor.status().ready')
                    assert page.evaluate('VoisinageEditor.status().draft')==saved
                    assert engine.store._path(game_id).read_bytes()==before
                    assert page.evaluate('JSON.stringify(game)')==state
                    assert not mutations,mutations
                    assert not errors,errors
                    browser.close()
            finally:httpd.shutdown();httpd.server_close()
    result=dict(status='passed',themes=13,new_theme_scenes=21,new_theme_persistence=True,custom_color_picker=True,hex_validation=True,full_rgb_render=True,persist_reload=True,cancel_preserved=True,failed_save_preserved=True,
                no_game_writes=True,npc_palette_per_encounter=True,preview_frames_stop_on_close=True,viewports=[1280,768,390,320])
    (output/'checks.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))

if __name__=='__main__':main()
