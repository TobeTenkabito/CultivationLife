"""Run directly: paired meridian artwork, live panels and state/keyboard boundaries."""
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


def main():
    output = ROOT / 'build' / 'meridian-atlas'
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    checks = 0
    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        engine = GameEngine(ROOT, temp / 'saves')

        class QuietHandler(server.Handler):
            def log_message(self, *_args):
                pass

        httpd = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', temp):
            thread.start()
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    page = browser.new_page(viewport={'width': 1440, 'height': 1100})
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('configData !== null')
                    for kind, preset in [('asura', 'asura_upper'), ('immortal', 'true_immortal')]:
                        made = engine.create_game('图谱验收', 'supreme_metal', 'dao', seed=808, preset_id=preset)
                        page.evaluate('async id => render(await api(`/api/games/${id}`))', made['id'])
                        page.evaluate('name => UtilityPanels.open(name)', f'{kind}-veins')
                        plate = page.locator(f'#{kind}-veins-card .meridian-atlas')
                        assert plate.locator('.atlas-node').count() == 27
                        art = plate.locator('.atlas-anatomy image')
                        assert art.count() == 1
                        assert art.get_attribute('href') == f'/assets/{kind}-anatomy.png'
                        await_image = page.evaluate('''src => new Promise((resolve,reject) => {
                          const image = new Image();
                          image.onload = () => resolve([image.naturalWidth,image.naturalHeight]);
                          image.onerror = () => reject(new Error(`Artwork failed to load: ${src}`));
                          image.src = src;
                        })''', art.get_attribute('href'))
                        assert await_image == [1122, 1402]
                        for width, height in [(1440, 1100), (390, 844), (320, 720), (844, 390)]:
                            page.set_viewport_size({'width': width, 'height': height})
                            for theme in 'abcdef':
                                page.evaluate('theme => document.querySelector(`[data-theme-choice="${theme}"]`).click()', theme)
                                for opened, layer, expected_next in [(0, 1, 1), (3, 1, 0), (3, 2, 1), (26, 9, 1), (27, 9, 0)]:
                                    result = page.evaluate('''({kind, opened, layer}) => {
                                      const names = Array.from({length:27}, (_,i) => `仙脉${i+1}`);
                                      names[26] = '<img src=x onerror="window.atlasInjected=1">';
                                      const veins = {opened, layer, per_layer:3, names,
                                        nodes:Array.from({length:27},(_,i)=>({index:i+1,
                                          status:i<opened?'open':i===opened&&i<layer*3?'next':'locked'}))};
                                      const snapshot = JSON.stringify(veins);
                                      const figure = MeridianAtlas.render(veins,kind);
                                      document.querySelector(`#${kind}-veins-card .meridian-atlas`).replaceWith(figure);
                                      const nodes = [...figure.querySelectorAll('.atlas-node')];
                                      const bounds = figure.getBoundingClientRect();
                                      return {
                                        total:nodes.length,
                                        unique:new Set(nodes.map(n=>n.dataset.vein)).size,
                                        open:nodes.filter(n=>n.dataset.state==='open').length,
                                        next:nodes.filter(n=>n.dataset.state==='next').length,
                                        fits:figure.scrollWidth<=figure.clientWidth+1 && bounds.left>=0 && bounds.right<=innerWidth,
                                        unchanged:JSON.stringify(veins)===snapshot,
                                        images:figure.querySelectorAll('img').length
                                      };
                                    }''', {'kind': kind, 'opened': opened, 'layer': layer})
                                    assert result == dict(total=27, unique=27, open=opened, next=expected_next,
                                                          fits=True, unchanged=True, images=0), (kind, width, theme, opened, result)
                                    checks += 1
                            if width in (1440, 390):
                                plate.screenshot(path=str(output / f'{kind}-{width}.png'))
                        last = plate.locator('[data-vein="27"]')
                        last.focus()
                        last.press('Enter')
                        assert last.get_attribute('aria-pressed') == 'true'
                        assert plate.locator('[aria-pressed="true"]').count() == 1
                        if kind == 'immortal':
                            assert '<img src=x' in plate.locator('.atlas-selected-name').text_content()
                            assert page.evaluate('window.atlasInjected !== 1')
                        plate.locator('[data-vein="1"]').click()
                        assert plate.locator('[data-vein="1"]').get_attribute('aria-pressed') == 'true'
                        assert plate.locator('[aria-pressed="true"]').count() == 1
                        # An Asura node is unavailable if the server says so, even within this layer.
                        if kind == 'asura':
                            assert page.evaluate('''() => {
                              const f = MeridianAtlas.render({opened:0,layer:1,per_layer:3,
                                nodes:[{index:1,status:'locked'}]}, 'asura');
                              return f.querySelectorAll('[data-state="next"]').length;
                            }''') == 0
                        page.evaluate('name => UtilityPanels.close(name)', f'{kind}-veins')
                        page.set_viewport_size({'width': 1440, 'height': 1100})
                    browser.close()
                assert not errors, errors
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=5)
    print(json.dumps({'status': 'passed', 'state_layout_checks': checks, 'themes': 6,
                      'viewports': 4, 'keyboard_and_pointer': 'passed', 'script_errors': errors}))


if __name__ == '__main__':
    main()
