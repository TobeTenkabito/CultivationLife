"""Exercise real Asura actions and responsive shared-theme rendering."""
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from cultivation_life import server
from cultivation_life.engine import GameEngine
from cultivation_life.rules import max_mp


class Quiet(server.Handler):
    def log_message(self, *args):
        pass


def main():
    with tempfile.TemporaryDirectory() as directory:
        server.PERSISTENCE_ROOT = Path(directory)
        engine = server.ENGINE = GameEngine(ROOT, Path(directory) / 'saves')
        game = engine.store.load(engine.create_game('八部验收', 'supreme_metal', 'demonic', 720,
                                                   preset_id='asura_upper')['id'])
        game.player.asura_cultivation.update(conversion=5, body_level=20, souls=10000,
            route='garuda', level=9, domain_rank=8, domain_name='验收翼域')
        game.player.foreign_souls = [dict(id='ui-soul', name='旧魂', refined=True, realm_index=9, strength=1)]
        game.player.asura_cultivation['vein_pity']={'9:1':100}
        game.player.puppets=[dict(id='train-ui',name='验收傀儡',type='mechanical',realm_index=2,layer=1,
                                 body_training=10,immortal_body_level=0,divine_sense_rank=10,combat_power=100,alive=True)]
        game.player.mp=max_mp(game.player)
        game.pending_event=None
        engine.store.save(game)
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        errors = []
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                page = browser.new_page(viewport={'width':1440,'height':1000})
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{httpd.server_port}')
                page.wait_for_function('configData !== null')
                assert page.locator('[aria-label$="种属"]').count() >= 1
                novice=engine.create_game('人界魔修', 'supreme_metal', 'demonic', 1562)
                page.evaluate('(id)=>loadGame(id)', novice['id'])
                assert page.locator('[data-panel-target^="asura-"]:visible').count()==0
                assert page.locator('[data-chapter="dlc-asura"]').count()==0
                assert page.locator('[data-chapter="immortal-trials"]').count()==0
                page.evaluate('(id)=>loadGame(id)', game.id)
                # Open whichever shared utility panel owns the soul list.
                page.evaluate("UtilityPanels.open('captive')")
                page.get_by_role('button', name='提纯为精魂', exact=True).click()
                page.wait_for_function('game.asura.souls === 10090')
                training=page.locator('.owned-training').first
                training.locator('summary').click()
                training.get_by_label('培养方向').select_option('body')
                training.get_by_label('培养轮数').select_option('5')
                training.get_by_role('button',name='培养炼体 · 5轮',exact=True).click()
                page.wait_for_function('game.demonic_system.puppets[0].body_training === 60')
                page.evaluate("UtilityPanels.open('asura-veins')")
                assert page.locator('.asura-vein-node').count()==27
                page.get_by_role('button',name='尝试开辟下一条魔脉',exact=True).click()
                page.wait_for_function('game.asura.opened === 1')
                assert '贯通成功' in page.locator('#asura-veins-content').inner_text()
                page.evaluate("UtilityPanels.open('asura-powers')")
                page.locator('#asura-powers-content').get_by_role('button', name='获取随机神通（100精魂）').click()
                page.wait_for_function('game.asura.powers?.length === 1')
                assert '当' in page.locator('#asura-powers-content').inner_text()
                for total in (2,3):
                    page.locator('[data-asura-action=learn_power]').click()
                    page.wait_for_function('(n)=>!busy&&game.asura.powers.length===n', arg=total)
                old=page.evaluate('JSON.parse(JSON.stringify(game.asura.powers))')
                page.locator('[data-asura-action=lock_power]').first.click()
                page.wait_for_function('!busy&&game.asura.power_reroll.locked_ids.length===1')
                before=page.evaluate('game.asura.souls')
                assert page.locator('[data-asura-action=reroll_power]').count()==1
                page.locator('[data-asura-action=reroll_power]').click()
                page.wait_for_function('(n)=>!busy&&game.asura.souls===n-200', arg=before)
                after=page.evaluate('game.asura.powers')
                assert old[0]==after[0] and all(a!=b for a,b in zip(old[1:],after[1:]))
                page.evaluate('(id)=>loadGame(id)',game.id)
                page.evaluate("UtilityPanels.open('asura-powers')")
                assert page.locator('[data-asura-action=lock_power]').first.get_attribute('aria-pressed')=='true'
                assert '无尽' in page.locator('#opportunity-text').inner_text()

                for theme in 'abcdef':
                    page.evaluate('(t)=>document.querySelector(`[data-theme-picker=dialog] [data-theme-choice=${t}]`).click()', theme)
                    for width in (1440, 412, 932):
                        print(f'Asura theme {theme}, width {width}',flush=True)
                        page.set_viewport_size({'width':width,'height':430 if width==932 else 915 if width==412 else 1000})
                        page.evaluate("UtilityPanels.open('asura-veins')")
                        for title in ['conversion','body','veins','route','domain','powers']:
                            page.locator(f'[data-panel-target=asura-{title}]').click()
                            assert page.locator(f'#asura-{title}-content').evaluate('e=>e.scrollWidth <= e.clientWidth + 1'), (theme,width,title)
                        assert '煞元' in page.locator('#hud-mp').inner_text()
                        assert '精魂' in page.locator('#hud-power').inner_text()
                        assert '仙痕' not in page.locator('#hud-power').inner_text()
                        assert page.locator('#hud-mp').get_attribute('data-energy-kind')=='asura'
                        page.evaluate("UtilityPanels.open('captive')")
                        page.locator('.owned-training summary').first.click()
                        assert page.locator('.owned-training').first.evaluate('e=>e.scrollWidth <= e.clientWidth + 1')
                        if width==1440:
                            page.evaluate("UtilityPanels.open('asura-veins')")
                            assert page.locator('.asura-meridian-figure .atlas-anatomy image').count()==1
                            assert page.locator('.asura-meridian-figure .atlas-anatomy image').get_attribute('href')=='/assets/asura-anatomy.png'
                            page.wait_for_function("document.querySelector('#asura-veins-card').getBoundingClientRect().width > 100 && getComputedStyle(document.querySelector('#asura-veins-card')).visibility === 'visible'")
                            page.wait_for_timeout(400)
                            page.locator('#asura-veins-card').evaluate('e=>e.scrollTop=0')
                            page.screenshot(path=str(ROOT/'build'/f'asura-1560-{theme}.png'))
                page.evaluate("UtilityPanels.open('asura-veins')")
                page.evaluate("UtilityPanels.open('asura-route')")
                page.locator('.asura-help').click()
                assert page.locator('[data-chapter=dlc-asura]').evaluate('e=>e.open')
                page.wait_for_function("document.querySelector('[data-chapter=dlc-asura]').innerText.includes('阿修罗')")
                page.evaluate('(id)=>loadGame(id)',novice['id'])
                assert page.locator('[data-panel-target^="asura-"]:visible').count()==0
                assert page.locator('[data-chapter="dlc-asura"]').count()==0
                assert page.locator('[id^="asura-"][id$="-card"].panel-open').count()==0
                assert not errors, errors
                browser.close()
        finally:
            httpd.shutdown()
    print('Asura UI passed: purification, random power, six themes and mobile widths.')


if __name__ == '__main__':
    main()
