"""Shared browser/EXE checks over a settled domain battle in an isolated save."""
from scripts.browser_navigation import navigation_locator


def verify(page, identity, output, label='domain'):
    page.evaluate('async id=>loadGame(id)',identity)
    navigation_locator(page,'#battle-report-open').click()
    page.wait_for_function('CombatReplay.diagnostics().active&&!document.querySelector("[data-combat-replay]").disabled')
    before=page.evaluate('JSON.stringify(game)')
    state=page.evaluate('CombatReplay.diagnostics()')
    assert state['domainStages'], state
    assert page.evaluate('''async()=>{
      const A=await(await fetch('/assets/pixel/combat/manifest.json')).json();
      const p=CombatReplay.build(game.last_combat_report,A),s=CombatReplay.sample(p,p.duration);
      return Math.abs(s.health.hero-game.last_combat_report.player_combat_state)<.01&&Math.abs(s.health.npc-game.last_combat_report.enemy_combat_state)<.01;
    }''')
    calls=[]
    def request(r):
        if '/api/' in r.url:calls.append(r.url)
    page.on('request',request)
    for width,height in [(1440,960),(390,844),(320,740)]:
        page.set_viewport_size(dict(width=width,height=height))
        for phase in state['domainStages']:
            page.evaluate('t=>CombatReplay.seek(t)',(phase['start']+phase['end'])/2)
            d=page.evaluate('CombatReplay.diagnostics()')
            assert d['domain']['phase']==phase['phase']
            assert page.locator('#battle-report-card').evaluate('n=>n.scrollWidth<=n.clientWidth+1')
        control=next((r for r in state['domainStages'] if r['phase']=='control'),state['domainStages'][0])
        page.evaluate('t=>CombatReplay.seek(t)',(control['start']+control['end'])/2)
        page.locator('#battle-animation canvas').screenshot(path=str(output/f'{label}-{width}.png'))
    page.locator('[data-combat-replay]').click()
    page.wait_for_timeout(150)
    page.keyboard.press('Escape')
    assert page.evaluate('!CombatReplay.diagnostics().active&&!CombatReplay.diagnostics().raf&&CombatReplay.diagnostics().cache===0')
    assert page.evaluate('JSON.stringify(game)')==before and not calls
    page.remove_listener('request',request)
