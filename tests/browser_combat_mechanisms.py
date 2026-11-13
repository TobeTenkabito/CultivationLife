"""Real C-layout battle reports: both palettes, domain stages, receipts and lifecycle."""
import copy
import hashlib
import json
import random
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
from cultivation_life.content_registry import TECHNIQUE_CATALOG
from cultivation_life.rules import learn_technique, max_hp, max_mp, QI_SOURCE_NAMES
from cultivation_life.system.duel_techniques import player_reason
from cultivation_life.ui_preferences import write_ui_preferences
from scripts.browser_navigation import navigation_locator, set_theme
from fixtures.visual_additions import prepare_domain_battle


def prepare(engine):
    game = engine.store.load(engine.create_game('回合溯源', 'heavenly', 'dao', 713, preset_id='core')['id'])
    game.pending_event = None
    game.player.realm_index = 5
    game.player.qi_experience = {key: 1e12 for key in QI_SOURCE_NAMES}
    books = [copy.deepcopy(t) for t in TECHNIQUE_CATALOG.values()
             if t.combat_effect and t.combat_effect.get('version') == 3
             and t.combat_effect['resource'] == 'mana' and not player_reason(game.player, t)
             and t.combat_effect['trigger'] == 'paid_preparation'][:7]
    assert len(books) == 7
    for b in books:
        learn_technique(game.player, b)
    engine.store.save(game)
    for b in books:
        engine.equip_known_technique(game.id, b.id, 'combat')
        engine.equip_known_technique(game.id, b.id, 'duel')
    game = engine.store.load(game.id)
    game.player.hp = max_hp(game.player)
    game.player.mp = max_mp(game.player)
    engine._combat(game, dict(target_name='同门剑修', target_power=engine._player_battle_power(game),
        target_realm_index=5, combat_type='cultivator', max_rounds=3, gender='female', path='dao'), False, random.Random(81))
    assert len(game.last_combat_report['rounds'][0]['voisinage']['technique_effects']['player_loadout']) == 7
    engine.store.save(game)
    return game.id


def main():
    output = ROOT / 'build/combat-mechanisms'
    output.mkdir(parents=True, exist_ok=True)
    checks = []
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        engine = GameEngine(ROOT, root / 'saves')
        write_ui_preferences(root, dict(pixel_art=True, reduced_motion=True))
        ordinary = prepare(engine)
        ids = [('ordinary', ordinary)]
        for kind in ['control', 'mixed', 'group']:
            identity = engine.create_game('邻域溯源', 'heavenly', 'dao', 151, preset_id='core')['id']
            prepare_domain_battle(engine, identity, kind)
            ids.append((kind, identity))
        class Quiet(server.Handler):
            def log_message(self, *args): pass
        with patch.object(server, 'ENGINE', engine), patch.object(server, 'PERSISTENCE_ROOT', root), patch('cultivation_life.runtime.persistence_root', return_value=root):
            http = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    page = browser.new_page(viewport=dict(width=1440, height=1100), reduced_motion='reduce')
                    errors = []
                    page.on('pageerror', lambda e: errors.append(str(e)))
                    page.add_init_script('Array.prototype.at=undefined;Array.prototype.findLast=undefined')
                    page.goto(f'http://127.0.0.1:{http.server_port}')
                    page.wait_for_function('!!configData')
                    page.evaluate('GameThemes.ready')
                    for palette in ['light', 'dark']:
                        set_theme(page, palette)
                        for kind, identity in ids:
                            page.evaluate('async id=>loadGame(id)', identity)
                            navigation_locator(page, '#battle-report-open').click()
                            page.wait_for_function('CombatReplay.diagnostics().active&&!document.querySelector("[data-combat-replay]").disabled')
                            original = page.evaluate('JSON.stringify(game)')
                            saved = copy.deepcopy(engine.store.load(identity).to_dict())
                            calls = []
                            def request(r):
                                if '/api/' in r.url: calls.append(r.url)
                            page.on('request', request)
                            plan = page.evaluate('''()=>{
                                const p=CombatReplay.diagnostics();
                                return {duration:p.duration,frames:p.mechanismFrames,domains:p.domainStages,
                                  paidIndex:game.last_combat_report.rounds.findIndex(r=>(r.voisinage?.technique_effects?.events??[]).some(e=>e.owner==='player'&&e.event==='paid'))};
                            }''')
                            if kind == 'ordinary':
                                assert '普通交锋' in page.locator('#battle-report-summary').inner_text()
                                assert page.locator('.combat-technique[data-book]').count() == 7, page.evaluate('({html:document.querySelector("#battle-mechanisms").outerHTML,keys:game.last_combat_report.rounds.map(r=>Object.keys(r.voisinage?.technique_effects??{}))})')
                                page.evaluate('CombatReplay.seek(0)')
                                assert '等待本轮结算记录' in page.locator('[data-mechanism-timeline]').inner_text()
                                assert '实际支付' not in page.locator('[data-mechanism-timeline]').inner_text()
                                assert plan['paidIndex'] >= 0, 'Fixture must contain an actual paid cast'
                                page.locator('[data-combat-scrub]').fill(f"{min(plan['duration'],plan['frames'][plan['paidIndex']]['settled']+.02):.2f}")
                                assert '实际支付' in page.locator('[data-mechanism-timeline]').inner_text(), page.locator('#battle-mechanisms').inner_text()
                                page.locator('.combat-technique[data-book]').first.click()
                                assert page.locator('.mechanism-lane:not(.observed-lane):not(.domain-lane)').count() == 1
                                page.locator('.combat-technique[data-book]').first.click()
                            for phase in plan['domains']:
                                page.evaluate('t=>CombatReplay.seek(t)', (phase['start'] + phase['end']) / 2)
                                assert phase['label'] in page.locator('[data-mechanism-phase]').inner_text()
                            for width, height in [(1440, 1100), (390, 844), (320, 740)]:
                                page.set_viewport_size(dict(width=width, height=height))
                                page.locator('[aria-label="机制记录轮次"]').select_option('0')
                                assert '轮末确认后显示' not in page.locator('[data-mechanism-timeline]').inner_text()
                                assert page.locator('#battle-report-card').evaluate('n=>n.scrollWidth<=n.clientWidth+1')
                                assert page.locator('.combat-mechanisms').evaluate('n=>n.scrollWidth<=n.clientWidth+1')
                                if kind in ['ordinary', 'group'] and width != 320:
                                    page.locator('[aria-label="机制记录轮次"]').select_option(str(max(0,plan['paidIndex'])))
                                    page.locator('#battle-report-card').evaluate('n=>n.scrollTop=0')
                                    page.locator('#battle-report-card').screenshot(path=str(output / f'{kind}-{palette}-{width}.png'))
                                    page.locator('#battle-report-card').evaluate('''n=>{
                                        const top=n.querySelector('#battle-mechanisms').getBoundingClientRect().top;
                                        n.scrollTop+=top-n.getBoundingClientRect().top-n.querySelector('.section-title').offsetHeight-12;
                                    }''')
                                    page.locator('#battle-report-card').screenshot(path=str(output / f'{kind}-{palette}-{width}-timeline.png'))
                                checks.append([palette, kind, width])
                            page.locator('[data-combat-replay]').click()
                            page.locator('[data-combat-pause]').click()
                            page.keyboard.press('Escape')
                            assert not page.evaluate('CombatReplay.diagnostics().active||CombatReplay.diagnostics().raf')
                            assert original == page.evaluate('JSON.stringify(game)') and not calls
                            assert engine.store.load(identity).to_dict() == saved
                            page.remove_listener('request', request)
                            page.set_viewport_size(dict(width=1440, height=1100))
                    # No-animation and historical reports still use the independent area.
                    page.evaluate('async id=>loadGame(id)', ordinary)
                    navigation_locator(page, '#battle-report-open').click()
                    page.wait_for_function('CombatReplay.diagnostics().active')
                    # Re-rendering the same game/report must not leave all progress
                    # nodes marked complete while the first round is playing.
                    page.evaluate('''()=>{const f=CombatReplay.diagnostics().mechanismFrames[0];
                        CombatReplay.seek(f.start+.01);renderBattleReport(game.last_combat_report);CombatReplay.seek(f.start+.01);}''')
                    assert page.locator('#battle-round-progress>span').first.get_attribute('class') == 'active'
                    # A resumed history starts at its recorded number, not 1.
                    page.evaluate('''()=>{const r=structuredClone(game.last_combat_report);
                        for(const row of r.rounds){row.round+=128;for(const e of row.voisinage.technique_effects.events)e.round+=128;}
                        r.total_rounds=131;renderBattleReport(r);}''')
                    page.wait_for_function('CombatReplay.diagnostics().active&&!document.querySelector("[data-combat-replay]").disabled')
                    page.evaluate('CombatReplay.seek(CombatReplay.diagnostics().mechanismFrames[0].start+.01)')
                    assert page.locator('#battle-round-progress>span').first.get_attribute('data-round') == '129'
                    assert page.locator('#battle-round-progress>span').first.get_attribute('class') == 'active'
                    assert '第 129 轮' in page.locator('#battle-round-progress>span').first.get_attribute('aria-label')
                    # Keyboard dragging can reach the true end despite fractional
                    # timeline durations and the range input's hundredth-second step.
                    page.locator('[data-combat-scrub]').focus()
                    page.keyboard.press('End')
                    assert page.evaluate('CombatReplay.diagnostics().time===CombatReplay.diagnostics().duration')
                    assert page.locator('[data-mechanism-phase]').inner_text() == '回放结束'
                    page.evaluate('''()=>{const r=structuredClone(game.last_combat_report);delete r.visual;renderBattleReport(r);}''')
                    assert page.locator('#battle-animation').is_hidden()
                    assert page.locator('#battle-mechanisms').is_visible()
                    paid = page.evaluate("game.last_combat_report.rounds.findIndex(r=>r.voisinage.technique_effects.events.some(e=>e.owner==='player'&&e.event==='paid'))")
                    page.locator('[aria-label="机制记录轮次"]').select_option(str(paid))
                    assert '实际支付' in page.locator('[data-mechanism-timeline]').inner_text()
                    page.evaluate('''()=>{const r=structuredClone(game.last_combat_report);delete r.visual;
                        for(const row of r.rounds)delete row.voisinage.technique_effects;renderBattleReport(r);}''')
                    assert '未记录七部功法' in page.locator('#battle-mechanisms').inner_text()
                    assert not errors, errors
                    browser.close()
            finally:
                http.shutdown();http.server_close()
    sources = ['web/combat-mechanisms.js', 'web/combat-mechanisms.css', 'web/combat-replay.js',
               'web/combat-renderer.js', 'web/index.html', 'web/app.js', 'cultivation_life/system/combat/technique_presentation.py']
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources}
    (output / 'validation.json').write_text(json.dumps(dict(checks=checks, errors=[], source_sha256=hashes), ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'C-layout acceptance passed: {len(checks)} theme/battle/viewport cases; receipts, domains, no writes, fallback, disposal')


if __name__ == '__main__': main()
