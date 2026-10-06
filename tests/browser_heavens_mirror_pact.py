"""Real HTTP mirror agreement, persistent commitment and explicit local release."""
import json
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
from cultivation_life.rules import max_hp, max_mp
from cultivation_life.system.heavens import mirror


def main():
    output = ROOT/'build/heavens-pact-browser'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        engine = GameEngine(ROOT, root/'saves')
        key = engine.create_game('守镜人', 'supreme_metal', 'dao', 4242, preset_id='core')['id']
        game = engine.store.load(key)
        p = game.player
        p.world, p.location_id, p.realm_index = 'human', 'muling_desert', 4
        p.lifespan, p.next_tribulation_age = None, 999999
        p.hp, p.mp = max_hp(p), max_mp(p)
        p.formation_materials.append(dict(id='browser-repair', material_id='human_quiet_soul_mirror', name='寂识镜片', acquired_tier=4))
        game.settings['silent_events'] = True
        engine.store.save(game)
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', root):
            httpd = ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
            threading.Thread(target=httpd.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    page = browser.new_page(viewport={'width':1440,'height':1050})
                    errors=[]
                    page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('window.GameThemes && configData')
                    page.evaluate('async id=>{await loadGame(id)}',key)
                    page.locator('[data-panel-target=heavens]').click()
                    page.get_by_role('tab',name='异象',exact=True).click()
                    page.get_by_role('button',name='查看镜律场域',exact=True).click()
                    def propose(label):
                        before = engine.store._path(key).read_bytes()
                        page.get_by_role('button',name=label,exact=True).click()
                        page.locator('#game-confirm-backdrop:not(.hidden)').wait_for()
                        assert engine.store._path(key).read_bytes()==before
                    def commit():
                        expected = engine.store.load(key).heavens_state['command_seq']+2
                        page.locator('#game-confirm-accept').click()
                        page.wait_for_function('seq=>!busy && game.heavens.next_command_seq===seq',arg=expected)
                    propose('进入镜律场域');commit()
                    propose('低耗试探');commit()
                    page.get_by_role('tab',name='守约',exact=True).click()
                    assert page.get_by_role('button',name='低耗破解',exact=True).count()==0
                    assert page.get_by_label('修补镜阵所用阵材',exact=True).input_value()=='browser-repair'
                    propose('修补并立约')
                    assert '3 年' in page.locator('#game-confirm-body').inner_text()
                    page.locator('#game-confirm-cancel').click()
                    propose('修补并立约')
                    def lose_response(route):
                        route.fetch();route.abort()
                    page.route('**/heavens-command',lose_response,times=1)
                    page.locator('#game-confirm-accept').click()
                    retry=page.get_by_role('button',name='重试上次提交（不会重复扣费）',exact=True)
                    retry.wait_for()
                    saved=engine.store.load(key)
                    assert mirror.get(saved)['pact']['status']=='kept' and saved.player.formation_materials==[]
                    retry.click()
                    page.wait_for_function('!busy && game.heavens.next_command_seq===4')
                    assert engine.store.load(key).player.age==saved.player.age
                    assert mirror.get(engine.store.load(key))==mirror.get(saved)
                    page.locator('[data-mirror-pact=kept]').wait_for()
                    page.get_by_role('tab',name='机关',exact=True).click()
                    page.locator('#heavens-chamber-0').click()
                    assert page.get_by_role('button',name='低耗破解',exact=True).count()==0
                    assert page.get_by_role('button',name='强攻机关',exact=True).count()==0
                    page.get_by_role('button',name='查看守约',exact=True).click()
                    page.locator('[data-mirror-pact=kept]').wait_for()
                    disk=engine.store._path(key).read_bytes()
                    for theme in 'abcdef':
                        page.locator('#theme-open').click()
                        page.locator(f'[data-theme-picker=dialog] [data-theme-choice={theme}]').click()
                        page.locator('[data-close-dialog=theme-dialog]').click()
                        for width in (1440,393):
                            page.set_viewport_size({'width':width,'height':1050 if width==1440 else 852})
                            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                            assert page.locator('#heavens-content').evaluate('(el)=>el.scrollWidth<=el.clientWidth+1')
                            assert page.locator('#heavens-content .heavens-actions').count()==1
                            page.screenshot(path=str(output/f'{theme}-{width}-kept.png'))
                    assert engine.store._path(key).read_bytes()==disk
                    propose('沿原路退出');commit()
                    page.get_by_role('tab',name='守约',exact=True).click()
                    assert page.locator('[data-mirror-pact=kept]').is_visible()
                    assert page.get_by_role('button',name='解除守约',exact=True).count()==0
                    page.get_by_role('tab',name='入口',exact=True).click()
                    propose('进入镜律场域');commit()
                    page.reload()
                    page.wait_for_function('window.GameThemes && configData')
                    page.evaluate('async id=>{await loadGame(id)}',key)
                    if not page.locator('#heavens-card').is_visible(): page.locator('[data-panel-target=heavens]').click()
                    page.get_by_role('tab',name='守约',exact=True).click()
                    propose('解除守约')
                    assert '永久关闭' in page.locator('#game-confirm-body').inner_text()
                    page.locator('#game-confirm-cancel').click()
                    assert mirror.get(engine.store.load(key))['pact']['status']=='kept'
                    propose('解除守约');commit()
                    page.locator('[data-mirror-pact=released]').wait_for()
                    page.get_by_role('tab',name='机关',exact=True).click()
                    page.locator('#heavens-chamber-0').click()
                    assert page.get_by_role('button',name='低耗破解',exact=True).is_disabled()
                    assert page.get_by_role('button',name='材料隔断',exact=True).is_disabled()
                    assert page.get_by_role('button',name='强攻机关',exact=True).is_enabled()
                    assert mirror.get(engine.store.load(key))['record_acquired']
                    assert not errors,errors
                    (output/'report.json').write_text(json.dumps(dict(themes=list('abcdef'),widths=[1440,393],
                        retry_once=True,read_only_preview=True,shared_record=True,reload=True,local_release=True,errors=errors),indent=2),encoding='utf-8')
                    browser.close()
            finally:
                httpd.shutdown();httpd.server_close()
    print('Mirror repair pact browser checks passed')


if __name__=='__main__': main()
