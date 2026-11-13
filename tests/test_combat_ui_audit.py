"""Adversarial historical reports in the real DOM and real replay planner.

Small synthetic histories exercise missing metadata and long/terminal rounds;
browser_combat_mechanisms.py separately verifies engine-produced live reports.
"""
import json
import re
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def browser():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    page = browser.new_page()
    html = (ROOT / 'web/index.html').read_text(encoding='utf-8')
    sections = [re.search(r'<section id="' + name + r'"[\s\S]*?</section>', html).group()
                for name in ['battle-animation', 'battle-mechanisms']]
    page.set_content(''.join(sections) + '<div id="battle-round-progress"></div>')
    page.evaluate("""()=>{window.VisualAssets={icon:()=>document.createElement('span')};
        window.PixelLibrary={active:()=>false};window.DomainFields={compose:()=>({})};} """)
    for filename in ['combat-domains.js', 'combat-mechanisms.js', 'combat-replay.js']:
        page.add_script_tag(content=(ROOT / 'web' / filename).read_text(encoding='utf-8'))
    app = (ROOT / 'web/app.js').read_text(encoding='utf-8')
    function = app[app.index('function renderBattleRoundProgress('):app.index('\nfunction renderEvent()')]
    page.add_script_tag(content="let battlePlaybackTimer=null;const $=s=>document.querySelector(s);\n" + function)
    yield page
    page.close()


def event(number, identity, kind='paid', owner='player', **kwargs):
    return dict(round=number, owner=owner, technique=identity, name=identity, event=kind, amount=3., **kwargs)


def report(*events):
    return dict(rounds=[dict(round=i+1, voisinage=dict(technique_effects=dict(events=e))) for i, e in enumerate(events)])


def test_old_refund_does_not_invent_energy_unit(page):
    page.evaluate('r=>CombatMechanisms.sync(r,true)', report([event(1, '旧退款', 'refunded')]))
    text = page.locator('.mechanism-current').inner_text()
    assert '单位未记录' in text and '元力' not in text


def test_unpaid_npc_preparation_is_not_an_observed_cast(page):
    page.evaluate('r=>CombatMechanisms.sync(r,true)', report([
        event(1, '未出手的秘术', 'prepared', 'enemy'), event(1, '真实已出手', owner='enemy', resource='mana')]))
    text = page.locator('.observed-lane').inner_text()
    assert '真实已出手' in text and '未出手的秘术' not in text


def test_legacy_manuals_are_not_revealed_by_future_rounds(page):
    page.evaluate('r=>CombatMechanisms.sync(r,true)', report(
        [event(1, '第一轮功法', resource='mana')], [event(2, '未来功法', resource='mana')]))
    page.locator('[aria-label="机制记录轮次"]').select_option('0')
    assert '未来功法' not in page.locator('#battle-mechanisms').inner_text()
    assert '本场装配' not in page.locator('[data-technique-strip]').inner_text()
    page.locator('[aria-label="机制记录轮次"]').select_option('1')
    assert '未来功法' in page.locator('[data-technique-strip]').inner_text()


def test_released_domain_retains_recorded_name(page):
    value = report([])
    value['rounds'][0]['voisinage'].update(fields=[], animation=dict(fields=[dict(name='已收回的仙域')], effects=[], interventions=[]))
    page.evaluate('r=>CombatMechanisms.sync(r,true)', value)
    assert '已收回的仙域' in page.locator('.domain-lane').inner_text()


def test_sampled_progress_uses_actual_round_numbers_and_includes_last(page):
    value = dict(rounds=[dict(round=n, events=[]) for n in range(129, 201)])
    page.evaluate('r=>renderBattleRoundProgress(r,false)', value)
    points = page.locator('#battle-round-progress>span').evaluate_all('ns=>ns.map(n=>({round:+n.dataset.round,title:n.title}))')
    assert len(points) == 8 and points[0]['round'] == 129 and points[-1]['round'] == 200
    assert all(f"第 {p['round']} 轮" in p['title'] for p in points)


@pytest.mark.parametrize('initiative', ['player', 'enemy'])
@pytest.mark.parametrize('outcome', ['victory', 'defeat'])
def test_terminal_inspection_reaches_authoritative_final_state(page, initiative, outcome):
    assets = json.loads((ROOT / 'web/assets/pixel/combat/manifest.json').read_text(encoding='utf-8'))
    enemy = next(k for k, actor in assets['actors'].items() if actor['role'] == 'npc')
    value = dict(visual=dict(schema_version=1, hero='dao-male', enemy=enemy), outcome=outcome,
                 player_combat_state_max=100, enemy_combat_state_max=100,
                 player_combat_state=61, enemy_combat_state=52, rounds=[dict(round=25, initiative=initiative,
                 ordinary_exchange=dict(opening=[100, 100], before=[100, 100], after=[60, 50]),
                 player_combat_state=61, enemy_combat_state=52)])
    result = page.evaluate('''([r,a])=>{const p=CombatReplay.build(r,a),f=p.mechanismFrames[0];
        return {f,duration:p.duration,health:CombatReplay.sample(p,f.settled).health,defeat:p.defeat};}''', [value, assets])
    assert result['defeat'] is not None
    assert result['f']['settled'] >= result['defeat']['start']
    assert result['f']['settled'] <= result['duration']
    assert result['health'] == dict(hero=61, npc=52)
