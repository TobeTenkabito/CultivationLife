"""Actual game loading/clicks for all 71 shipped monster static forms."""
import copy
import hashlib
import json
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from cultivation_life import server, content_registry as registry
from cultivation_life.engine import GameEngine
from cultivation_life.monster_visuals import monster_appearance
from cultivation_life.models import Player


def cases():
    found = {}
    for species in ['fox', 'serpent', 'avian', 'ape']:
        for node, n in registry.MONSTER_EVOLUTIONS.items():
            if n['species'] != species:
                continue
            for gender in ['female', 'male']:
                p = Player(name='头像核验', spirit_root='heavenly', path='monster', gender=gender,
                           monster_species_id=species, monster_evolution_id=node, monster_evolution_history=[node])
                appearance = monster_appearance(p)
                if appearance:
                    found.setdefault(appearance['static'], dict(species=species,node=node,gender=gender))
    assert len(found) == 71, len(found)
    return found


def main():
    out = ROOT/'build/monster-static-visuals'; out.mkdir(parents=True, exist_ok=True)
    forms = cases(); result = dict(forms=[], widths=[], errors=[])
    with tempfile.TemporaryDirectory() as folder:
        engine = GameEngine(ROOT, Path(folder)/'saves')
        bases = {}
        for species in ['fox','serpent','avian','ape']:
            made = engine.create_game('头像验收', 'supreme_water', 'monster', seed=4240,
                                      monster_species_id=species, start_world='monster_realm')
            bases[species] = engine.store.load(made['id'])
            bases[species].pending_event = None
            bases[species].settings.update(silent_events=True)
        class Handler(server.Handler):
            def log_message(self, *args):
                pass
        with patch.object(server,'ENGINE',engine), patch.object(server,'PERSISTENCE_ROOT',Path(folder)):
            http = ThreadingHTTPServer(('127.0.0.1',0),Handler)
            threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    page = browser.new_page(viewport=dict(width=1440,height=960),reduced_motion='reduce')
                    page.on('pageerror',lambda e:result['errors'].append(str(e)))
                    requests = []
                    page.on('request',lambda r:requests.append(r.url))
                    url = f'http://127.0.0.1:{http.server_port}'
                    page.goto(url);page.wait_for_function('!!configData && !!window.VisualAssets')
                    page.evaluate('GameThemes.ready')
                    page.locator('#theme-open').click()
                    page.locator('#theme-dialog [data-pixel-setting]').set_checked(True)
                    page.evaluate('GameThemes.saved')
                    page.locator('[data-close-dialog=theme-dialog]').click()
                    for identity, row in forms.items():
                        g = copy.deepcopy(bases[row['species']]);p = g.player
                        p.monster_evolution_id = row['node'];p.monster_evolution_history = [row['node']]
                        p.gender = row['gender'];p.realm_index = registry.MONSTER_EVOLUTIONS[row['node']]['realm_index'];p.layer = 1
                        engine.store.save(g)
                        page.evaluate('id=>loadGame(id)',g.id)
                        page.wait_for_function('id=>game?.player?.visual_actor===id',arg=identity)
                        file = identity.removeprefix('actor.monster.')+'-portrait.png'
                        page.wait_for_function('''file=>{const i=document.querySelector('.pixel-portrait');
                            return !i.hidden&&i.complete&&i.naturalWidth===128&&i.src.endsWith(file)}''',arg=file)
                        saved = engine.store._path(g.id).read_bytes()
                        page.locator('.hud-identity').click()
                        page.wait_for_function('id=>document.querySelector(".pixel-details-art canvas").dataset.actor===id',arg=identity)
                        # Verify the displayed pixels are the catalog's new standalone figure.
                        assert page.evaluate('''async id=>{const image=await VisualAssets.load(id+'.figure');
                            const expected=document.createElement('canvas');expected.width=256;expected.height=288;
                            expected.getContext('2d').drawImage(image,0,0);
                            return expected.toDataURL()===document.querySelector('.pixel-details-art canvas').toDataURL();}''',identity)
                        if row['species'] in ['avian','ape'] and registry.MONSTER_EVOLUTIONS[row['node']]['realm_index'] in [1,4,7]:
                            page.screenshot(path=str(out/(identity.removeprefix('actor.monster.')+'-details.png')))
                        page.keyboard.press('Escape')
                        assert engine.store._path(g.id).read_bytes() == saved
                        result['forms'].append(identity)
                    for width in [768,390,320]:
                        page.set_viewport_size(dict(width=width,height=900))
                        page.locator('.hud-identity').click()
                        assert page.locator('.pixel-details-art canvas').is_visible()
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                        page.screenshot(path=str(out/f'details-{width}.png'))
                        page.keyboard.press('Escape');result['widths'].append(width)
                    # Turn off the optional visuals through the real preference control.
                    page.set_viewport_size(dict(width=1440,height=960))
                    page.locator('#theme-open').click()
                    page.locator('#theme-dialog [data-pixel-setting]').set_checked(False)
                    page.evaluate('GameThemes.saved')
                    page.locator('[data-close-dialog=theme-dialog]').click()
                    assert page.locator('.pixel-portrait').is_hidden()
                    page.locator('.hud-identity').click()
                    assert page.locator('.pixel-details-art').is_hidden()
                    page.keyboard.press('Escape')
                    page.locator('#theme-open').click()
                    page.locator('#theme-dialog [data-pixel-setting]').set_checked(True)
                    page.evaluate('GameThemes.saved')
                    page.locator('[data-close-dialog=theme-dialog]').click()
                    active = [r for r in server.EXTENSION_REPORT if r.get('id')!='official.monster-bloodlines']
                    with patch.object(server,'EXTENSION_REPORT',active), patch.object(registry,'EXTENSION_REPORT',active):
                        for species in ['avian','ape']:
                            sample = next(i for i in forms if i.startswith('actor.monster.'+species+'-'))
                            asset = f'/extension-assets/official.monster-bloodlines/visual/{species}/{sample.removeprefix("actor.monster.")}-portrait.png'
                            assert page.request.get(url+asset).status == 404
                        page.reload();page.wait_for_function('!!configData && !!window.VisualAssets')
                        page.evaluate('GameThemes.ready');requests.clear()
                        page.evaluate('id=>loadGame(id)',g.id)
                        page.wait_for_function('game?.player && game.player.visual_actor===null')
                        assert page.locator('.pixel-portrait').is_hidden()
                        assert not any('/extension-assets/official.monster-bloodlines/' in u for u in requests)
                    assert not result['errors'], result['errors']
                    result.update(status='passed',pixel_equality=True,browsing_unchanged=True,disabled_dlc=True,
                                  optional_visuals_off=True,forms_count=len(forms))
                    browser.close()
            finally:
                http.shutdown();http.server_close()
    result['catalog_sha256'] = hashlib.sha256((ROOT/'content/visual_assets.json').read_bytes()).hexdigest()
    (out/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('71 forms: real HUD portraits, details pixel equality, mobile widths, no save writes and DLC off passed')


if __name__ == '__main__':
    main()
