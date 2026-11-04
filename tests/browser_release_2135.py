import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT/'tests/fixtures')]
import browser_other_systems_audit_fixes as harness
from audit_fixes_release import prepare_audit_fixes,inspect_audit_fixes
from scripts.browser_navigation import navigation_locator,click_control,reveal_subpage
from cultivation_life.system.upper_institutions import account

def create(engine,case):
    world,realm=('nether',9) if case=='work' else ('spirit',8)
    game=engine.create_game('版本修复验收','supreme_metal','dao',8712,custom_start=dict(world=world,realm_index=realm,layer=1))
    prepare_audit_fixes(engine,game['id'],case)
    return game['id']

def verify(page,engine,width):
    def open_panel(name):
        if not page.locator(f'#{name}-card').evaluate("node=>node.classList.contains('panel-open')"):
            click_control(navigation_locator(page,f'[data-panel-target={name}]'))
    identity=create(engine,'return')
    engine.manage_secret_art(identity,'suppress','activate',1,1)
    page.evaluate('async id=>loadGame(id)',identity)
    harness.click_post(page,'cross-world',page.locator('#cross-world-action'))
    assert engine._load(identity).player.sealed_cultivation['visit_only']
    open_panel('secret-art')
    click_control(page.locator('[data-secret-art=suppress]'))
    assert page.locator('#secret-suppress-cancel').is_disabled()
    click_control(page.locator('#secret-art-toggle'))
    harness.click_post(page,'cross-world',page.locator('#cross-world-action'))
    open_panel('secret-art')
    if not page.locator('#secret-suppress-cancel').is_visible():
        click_control(page.locator('[data-secret-art=suppress]'))
    harness.click_post(page,'secret-art',page.locator('#secret-suppress-cancel'))
    inspect_audit_fixes(engine,identity,'return')
    click_control(page.locator('#secret-art-toggle'))
    identity=create(engine,'training')
    page.evaluate('async id=>loadGame(id)',identity)
    open_panel('captive')
    click_control(page.locator('#captive-list .npc-development-open').first)
    page.wait_for_selector('#npc-development-submit')
    page.get_by_label('培养方向',exact=True).select_option('cultivation')
    page.get_by_label('培养方式',exact=True).select_option('infuse')
    button=page.locator('#npc-development-submit')
    assert button.is_enabled(), page.evaluate('({opportunity:game.player.opportunity,mp:game.player.mp,prisoner:game.demonic_system.prisoners[0],sealed:game.player.sealed_cultivation,trial:game.trial})')
    harness.click_post(page,'npc-development',button)
    page.locator('#npc-development-dialog>header button').click()
    harness.click_post(page,'captive-action',page.locator('#captive-list').get_by_role('button',name='释放',exact=True,include_hidden=True))
    inspect_audit_fixes(engine,identity,'training')
    click_control(page.locator('#captive-toggle'))
    identity=create(engine,'work')
    page.evaluate('async id=>loadGame(id)',identity)
    start=engine._load(identity).player.age
    open_panel('upper-institution')
    click_control(page.locator('#upper-institution-card [data-section=jobs] summary'))
    button=page.locator('#upper-institution-card').get_by_role('button',name='继续履约',exact=True,include_hidden=True)
    harness.click_post(page,'upper-institution',button)
    assert engine._load(identity).player.age-start==60
    assert account(engine._load(identity))['job']['progress']==100
    print(f'Release 2135 UI passed: {width}px, real descent/return/cancel, training/release and remaining work',flush=True)

if __name__=='__main__':
    harness.verify=verify;harness.main()
