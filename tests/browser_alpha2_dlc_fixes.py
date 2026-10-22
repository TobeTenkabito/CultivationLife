"""Real item clicks and friend combat; reusable against the compiled EXE."""
import hashlib
import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from scripts.browser_navigation import navigation_locator,click_control,reveal_subpage,set_theme
from scripts.release_evidence import inputs_digest
from fixtures.alpha2_release import prepare_alpha2,inspect_alpha2


def verify(page, engine, identity, output, kind='replica', enabled=None):
    expected=prepare_alpha2(engine,identity,kind,enabled)
    page.evaluate('id=>loadGame(id)',identity)
    navigation_locator(page,'[data-panel-target=inventory]').click()
    row=page.locator('#inventory-list [data-item-id=guixu_canghai_equipment_01]')
    reveal_subpage(page,row)
    assert 'HP上限 +18' in row.inner_text() and 'MP上限 +20' in row.inner_text()
    consumable=page.locator('#inventory-list [data-item-id=guixu_canghai_consumable_01]')
    assert '21.50%' in consumable.inner_text()
    before=page.evaluate('game.player.inventory.find(i=>i.id==="guixu_canghai_consumable_01").quantity')
    click_control(consumable.locator('button.item-use'))
    page.wait_for_function('!busy && game.player.inventory.find(i=>i.id==="guixu_canghai_consumable_01").quantity===1')
    assert before==2
    page.locator('#inventory-toggle').click()
    page.locator('#theme-open').click()
    page.locator('#theme-dialog [data-pixel-setting]').set_checked(True)
    page.evaluate('GameThemes.saved')
    page.locator('[data-close-dialog=theme-dialog]').click()
    navigation_locator(page,'[data-panel-target=relationship]').click()
    search=page.locator('.contact-search')
    reveal_subpage(page,search)
    search.fill('验收持宝道友')
    page.once('dialog',lambda dialog:dialog.accept())
    page.locator('[data-contact-action=slay]').click()
    try:
        page.wait_for_function('!busy && !!game.last_combat_report && CombatReplay.diagnostics().active && !document.querySelector("[data-combat-replay]").disabled')
    except Exception:
        print(page.evaluate('JSON.stringify({toast:document.querySelector("#toast").textContent,busy,pending:game.pending_event,report:game.last_combat_report,diagnostics:CombatReplay.diagnostics(),open:battleReportOpen,pixel:PixelLibrary.active(),card:document.querySelector("#battle-report-card").className,hidden:document.hidden})'),flush=True)
        page.screenshot(path=str(output/'failure.png'))
        raise
    inspect_alpha2(engine,expected)
    page.evaluate('CombatReplay.seek(10000)')
    current=page.evaluate('CombatReplay.diagnostics()')
    assert current['defeat']
    for width,height in ((1440,960),(390,844),(320,740)):
        page.set_viewport_size(dict(width=width,height=height))
        page.wait_for_timeout(90)
        page.evaluate('CombatReplay.seek(10000)')
        assert page.locator('#battle-report-card').evaluate('n=>n.scrollWidth<=n.clientWidth+1')
        page.locator('#battle-animation canvas').screenshot(path=str(output/f'{kind}-{width}.png'))
    saved=engine.store._path(identity).read_bytes()
    page.locator('[data-combat-replay]').click()
    page.wait_for_timeout(120)
    page.keyboard.press('Escape')
    assert page.evaluate('!CombatReplay.diagnostics().active && !CombatReplay.diagnostics().raf && CombatReplay.diagnostics().cache===0')
    assert engine.store._path(identity).read_bytes()==saved
    page.set_viewport_size(dict(width=1440,height=960))
    # Restore the legacy UI before the next actual item-command case.
    page.locator('#theme-open').click()
    page.locator('#theme-dialog [data-pixel-setting]').set_checked(False)
    page.evaluate('GameThemes.saved')
    page.locator('[data-close-dialog=theme-dialog]').click()
    return expected


def main():
    out=ROOT/'build/alpha2-dlc';out.mkdir(parents=True,exist_ok=True)
    before=inputs_digest(ROOT)
    with tempfile.TemporaryDirectory() as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        class Handler(server.Handler):
            def log_message(self,*args):pass
        with patch.object(server,'ENGINE',engine),patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch();page=browser.new_page(viewport=dict(width=1440,height=960),reduced_motion='reduce')
                    page.add_init_script('delete Array.prototype.at; delete Array.prototype.findLast;')
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto(f'http://127.0.0.1:{http.server_port}');page.wait_for_function('!!configData && !!window.CombatReplay');page.evaluate('GameThemes.ready')
                    for index,theme in enumerate('abdf'):
                        set_theme(page,theme)
                        identity=engine.create_game('交锋与宝物验收','heavenly','dao',622+index,preset_id='core')['id']
                        verify(page,engine,identity,out,'replica' if index%2 else 'true_body')
                    assert not errors,errors
                    browser.close()
            finally:
                http.shutdown();http.server_close()
    assert inputs_digest(ROOT)==before
    (out/'checks.json').write_text(json.dumps(dict(status='passed',inputs_sha256=before,themes=list('abdf'),widths=[1440,390,320]),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Alpha.2 Guixu item clicks, true/replica combat intelligence, replay/disposal and four themes passed')


if __name__=='__main__':main()
