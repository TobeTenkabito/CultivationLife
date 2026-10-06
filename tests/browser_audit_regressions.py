"""Run directly: imported-save XSS, stale previews and all preset/theme panels."""
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
from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.engine import GameEngine
from cultivation_life.save_transfer import export_snapshot, import_snapshot, preview_snapshot
from cultivation_life.storage import SaveStore


def main():
    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        engine = GameEngine(ROOT, temp / 'saves')

        class QuietHandler(server.Handler):
            def log_message(self, *_args):
                pass

        httpd = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        errors = []
        panel_count = 0
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', temp):
            thread.start()
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(f'http://127.0.0.1:{httpd.server_port}')
                    page.wait_for_function('configData !== null')
                    for preset in WORLD_SYSTEMS['quick_start_presets']:
                        if not preset.get('enabled'):
                            continue
                        made = engine.create_game('面板回归', 'supreme_metal', 'dao', seed=808,
                                                  preset_id=preset['id'], monster_species_id='serpent')
                        page.evaluate('async id => render(await api(`/api/games/${id}`))', made['id'])
                        count = page.evaluate('''() => {
                          let count = 0;
                          for (const theme of 'abdf') {
                            document.querySelector(`[data-theme-choice="${theme}"]`).click();
                            for (const button of document.querySelectorAll('[data-panel-target]')) {
                              if (button.classList.contains('hidden')) continue;
                              const name = button.dataset.panelTarget;
                              UtilityPanels.open(name);
                              if (!document.getElementById(`${name}-card`)?.classList.contains('panel-open')) {
                                throw new Error(`Panel failed to open: ${name}`);
                              }
                              count++;
                              UtilityPanels.close(name);
                            }
                          }
                          return count;
                        }''')
                        panel_count += count

                    made = engine.create_game('存档回归', 'supreme_metal', 'confucian', seed=909)
                    game = engine._load(made['id'])
                    doctrine = game.sage_state['worlds'][game.player.world]['doctrines'][0]['id']
                    engine.sage_doctrine_action(game.id, 'join', {'doctrine_id': doctrine})
                    game = engine._load(game.id)
                    payload = '<img src=x onerror="window.auditStoredXss=1">'
                    game.player.name = payload
                    source = SaveStore(temp / 'export-source')
                    source.save(game)
                    code = export_snapshot(source, game.id)['payload']
                    preview = preview_snapshot(engine.store, code)
                    import_snapshot(engine.store, code, preview['existing_hash'])
                    page.evaluate('async id => render(await api(`/api/games/${id}`))', game.id)
                    page.wait_for_timeout(100)
                    assert page.evaluate('window.auditStoredXss !== 1')
                    assert payload in page.locator('.sage-member-row.player').text_content()
                    assert page.locator('.sage-member-row.player img').count() == 0
                    assert page.locator('#player-name').text_content() == payload

                    result = page.evaluate('''async () => {
                      const originalApi=api, originalPayload=formationPayload, originalRender=renderFormationReading;
                      const waiting=[], rendered=[];
                      try {
                        api=()=>new Promise(resolve=>waiting.push(resolve));
                        formationPayload=()=>({slots:[]});
                        renderFormationReading=value=>rendered.push(value.auditRequest);
                        const first=previewFormation(), second=previewFormation();
                        waiting[1]({auditRequest:'new'}); await second;
                        waiting[0]({auditRequest:'old'}); await first;
                        const newest=formationDraftProfile.auditRequest;
                        const third=previewFormation();
                        scheduleFormationPreview(); // invalidate before debounce fires
                        clearTimeout(formationPreviewTimer);
                        waiting[2]({auditRequest:'before-edit'}); await third;
                        const fourth=previewFormation();
                        invalidateFormationPreview(); // same path as a reload or leaving the game
                        waiting[3]({auditRequest:'before-reload'}); await fourth;
                        return {rendered, newest, final:formationDraftProfile.auditRequest};
                      } finally {api=originalApi;formationPayload=originalPayload;renderFormationReading=originalRender;}
                    }''')
                    assert result == {'rendered': ['new'], 'newest': 'new', 'final': 'new'}
                    browser.close()
                assert not errors, errors
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=5)
    print(json.dumps({'status': 'passed', 'panel_open_checks': panel_count,
                      'imported_save_xss': 'blocked', 'stale_formation_preview': 'ignored'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
