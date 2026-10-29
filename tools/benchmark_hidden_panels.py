"""Compare actual hidden-panel rendering against captured frontend source."""
import argparse
import hashlib
import importlib.util
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import random
import statistics
import sys
import tempfile
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cultivation_life import server
from cultivation_life.engine import GameEngine
from playwright.sync_api import sync_playwright
from scripts.release_evidence import inputs_digest

PANELS = ['inventory', 'map', 'spirit-field', 'relationship', 'faction', 'family',
    'world-npc', 'world-route', 'transformation', 'market', 'auction', 'exchange',
    'ranking', 'race', 'crafting', 'formation', 'natal-artifact', 'tianji', 'heavenly-court',
    'heavens', 'immortal-conversion', 'doctrine', 'immortal-veins', 'immortal-body', 'voisinage',
    'daomen', 'golden-light', 'yaochi', 'intrigue', 'sage', 'sage-inner-outer',
    'asura-conversion', 'asura-body', 'asura-veins', 'asura-route', 'asura-domain', 'asura-powers']
SAMPLES = """async data=>{
  const samples=[];
  for(let i=0;i<11;i++){
    const start=performance.now();render(data);document.documentElement.scrollWidth;
    if(i)samples.push(performance.now()-start);
    await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
  }
  return samples;
}"""
SNAPSHOT = """name=>{
  const root=document.getElementById(name+'-card');
  return {text:root.textContent.replace(/\\s+/g,' ').trim(),
    tabs:[...root.querySelectorAll('[role=tab]')].map(n=>[n.textContent,n.getAttribute('aria-selected')]),
    pages:[...root.querySelectorAll('[data-page-name]')].map(n=>[n.tagName,n.id,n.dataset.pageName,n.hasAttribute('data-page-hidden'),n.open]),
    controls:[...root.querySelectorAll('button,input,select,textarea')].map(n=>({
      tag:n.tagName,id:n.id,type:n.type,text:n.tagName==='SELECT'?[...n.options].map(o=>[o.value,o.textContent,o.disabled]):n.textContent,
      value:n.value,disabled:n.disabled,checked:n.checked,visible:!!n.getClientRects().length,dataset:{...n.dataset}}))};
}"""
PANEL_ELEMENTS = """()=>Object.fromEntries([...document.querySelectorAll('.utility-panel')].map(n=>[
  n.id,{elements:n.querySelectorAll('*').length,hidden:n.classList.contains('hidden')}]))"""


def source_handler(path):
    def serve(route):
        route.fulfill(path=str(path))
    return serve


def measure(page, data, panels):
    timings = page.evaluate(SAMPLES, data)
    row = dict(hidden_render_ms=timings, hidden_render_median_ms=statistics.median(timings),
               initial_dom_elements=page.locator('*').count(), first_open_ms={},
               initial_panel_elements=page.evaluate(PANEL_ELEMENTS))
    row['navigation'] = page.evaluate("""()=>[...document.querySelectorAll('[data-panel-target]')].map(n=>({
        id:n.dataset.panelTarget,hidden:n.classList.contains('hidden'),
        unavailable:n.classList.contains('spatial-unavailable'),notice:n.classList.contains('notice'),
        activity:n.dataset.activityState||'',title:n.title,label:n.querySelector('small')?.textContent}))""")
    snapshots = {}
    for name in panels:
        available = page.locator('#' + name + '-card').evaluate("n=>!n.classList.contains('hidden')")
        if not available:
            continue
        row['first_open_ms'][name] = page.evaluate("""name=>{
            const start=performance.now();UtilityPanels.open(name);document.documentElement.scrollWidth;
            return performance.now()-start;}""", name)
        page.evaluate('async()=>{await PixelLibrary.ensure(true);await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));}')
        snapshots[name] = page.evaluate(SNAPSHOT, name)
        page.evaluate('name=>UtilityPanels.close(name)', name)
    visited = page.evaluate(SAMPLES, data)
    row.update(visited_hidden_render_ms=visited, visited_hidden_render_median_ms=statistics.median(visited),
               visited_dom_elements=page.locator('*').count(), visited_panel_elements=page.evaluate(PANEL_ELEMENTS))
    return row, snapshots


def benchmark(before_web, output, viewports, presets=None):
    for name in ['app.js', 'ui-panels.js']:
        if not (before_web / name).is_file():
            raise ValueError(f'Missing captured baseline source: {before_web / name}')
    output.mkdir(parents=True, exist_ok=True)
    signature = inputs_digest(ROOT)
    rows = []
    snapshots = {}
    dom_differences = {}
    with tempfile.TemporaryDirectory(prefix='hidden-panel-benchmark-') as folder:
        engine = GameEngine(ROOT, Path(folder) / 'saves')
        class Quiet(server.Handler):
            def log_message(self, *args): pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', Path(folder)):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    for preset in presets or ['core', 'true_immortal', 'spirit', 'organization', 'asura_upper', 'confucian_void', 'celestial_developed', 'asura_developed']:
                        options = (dict(spirit_root='otherworld', custom_start=dict(world='spirit', realm_index=8))
                                   if preset == 'spirit' else dict(spirit_root='supreme_earth', custom_start=dict(
                                       world='human', realm_index=4, sect='new', sect_name='验收宗'))
                                   if preset == 'organization' else dict(spirit_root='supreme_earth',
                                       preset_id='true_immortal' if preset == 'celestial_developed' else
                                       'asura_upper' if preset == 'asura_developed' else preset))
                        gid = engine.create_game('面板采样', path='dao', seed=280, **options)['id']
                        if preset == 'organization':
                            spec = importlib.util.spec_from_file_location('organizations_benchmark', ROOT / 'tests/fixtures/organizations-290.py')
                            fixture = importlib.util.module_from_spec(spec)
                            spec.loader.exec_module(fixture)
                            fixture.prepare(engine, gid)
                        if preset == 'celestial_developed':
                            # Isolated fixture: expose field and golden-light panels without changing rules.
                            game = engine.store.load(gid)
                            key = next(k for k in game.doctrine_state['definitions'] if k.startswith('celestial:'))
                            record = game.doctrine_state['player']
                            record['progress'][key] = {'level': 4, 'experience': 0}
                            record['voisinage_training'][key] = {'rank': 1}
                            record['active'] = key
                            game.player.immortal_body['level'] = 20
                            engine.store.save(game)
                        if preset == 'asura_developed':
                            from cultivation_life.system import asura
                            game = engine.store.load(gid)
                            game.player.realm_index = 10
                            game.player.asura_cultivation.update(route='yaksha', level=5, body_level=20,
                                conversion=5, souls=100000, domain_rank=3, domain_power=2, domain_name='按需魔域',
                                powers=[asura.generate_rule(random.Random(280), 'benchmark-power')])
                            engine.store.save(game)
                        engine.get_game(gid)
                        data = engine.get_game(gid)
                        saved = engine.store._path(gid).read_bytes()
                        metadata = engine.achievements.metadata.path.read_bytes()
                        for width, height in viewports:
                            key = f'{preset}-{width}'
                            order = ['before', 'after'] if width == viewports[0][0] else ['after', 'before']
                            for phase in order:
                                page = browser.new_page(viewport=dict(width=width, height=height), reduced_motion='reduce')
                                errors = []
                                page.on('pageerror', lambda error: errors.append(str(error)))
                                if phase == 'before':
                                    for path in before_web.glob('*.js'):
                                        page.route('**/' + path.name + '?*', source_handler(path))
                                        page.route('**/' + path.name, source_handler(path))
                                page.goto(f'http://127.0.0.1:{http.server_port}')
                                page.wait_for_function('!!configData && !!window.GameThemes && !busy')
                                page.evaluate('GameThemes.ready')
                                page.evaluate('id=>loadGame(id)', gid)
                                row, snapshot = measure(page, data, PANELS)
                                assert not errors, errors
                                row.update(phase=phase, preset=preset, viewport=[width, height])
                                snapshots[key, phase] = snapshot
                                rows.append(row)
                                print(json.dumps({k: row[k] for k in ['phase', 'preset', 'viewport',
                                    'hidden_render_median_ms', 'initial_dom_elements', 'visited_hidden_render_median_ms']}), flush=True)
                                assert saved == engine.store._path(gid).read_bytes(), 'Rendering wrote a character save'
                                assert metadata == engine.achievements.metadata.path.read_bytes(), 'Rendering changed achievements'
                                page.close()
                            old = next(r for r in rows if r['phase'] == 'before' and r['preset'] == preset and r['viewport'][0] == width)
                            new = next(r for r in rows if r['phase'] == 'after' and r['preset'] == preset and r['viewport'][0] == width)
                            if snapshots[key, 'before'] != snapshots[key, 'after'] or old['navigation'] != new['navigation']:
                                (output / f'mismatch-{key}.json').write_text(json.dumps(dict(
                                    before=snapshots[key, 'before'], after=snapshots[key, 'after'],
                                    navigation_before=old['navigation'], navigation_after=new['navigation']),
                                    ensure_ascii=False, indent=2), encoding='utf-8')
                                raise AssertionError(f'Opened panel or navigation differs: {key}')
                            differences = {}
                            for identity, before in old['visited_panel_elements'].items():
                                after = new['visited_panel_elements'][identity]
                                if before['elements'] != after['elements']:
                                    assert before['hidden'] and after['hidden'], f'Available panel DOM differs: {key}/{identity}'
                                    differences[identity] = dict(before=before, after=after)
                            assert old['visited_dom_elements'] - new['visited_dom_elements'] == sum(
                                d['before']['elements'] - d['after']['elements'] for d in differences.values()), f'Unexplained outside-panel DOM delta: {key}'
                            dom_differences[key] = differences
                    browser.close()
            finally:
                http.shutdown(); http.server_close()
    assert signature == inputs_digest(ROOT), 'Production changed during comparison'
    report = dict(inputs_sha256=signature, before_files={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in before_web.glob('*.js')}, browser_rows=rows, panels=PANELS,
        navigation_and_opened_panels_equal=True, save_and_metadata_bytes_unchanged=True,
        available_panel_dom_counts_equal=True, visited_dom_differences=dom_differences,
        scope='Same authoritative responses on original and final frontend, isolated full-DLC saves; ten warm render+forced-layout samples, two animation frames apart. Initial and previously opened hidden panels measured separately. First opening cost retained. Desktop Chromium viewport measurements, not Android frame-rate acceptance.')
    (output / 'comparison.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-web', required=True, type=Path)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'build/hidden-panels-performance')
    parser.add_argument('--mobile-only', action='store_true')
    parser.add_argument('--preset', action='append', help='Repeat to limit the compared fixtures.')
    args = parser.parse_args()
    benchmark(args.baseline_web.resolve(), args.output_dir.resolve(),
              [(412, 915)] if args.mobile_only else [(412, 915), (1440, 960)], args.preset)
