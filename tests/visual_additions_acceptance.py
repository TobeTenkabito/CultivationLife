"""Shared real-page acceptance for compiled alpha.3 resources and preferences."""
from scripts.browser_navigation import navigation_locator


def verify(page, identity, output):
    page.evaluate('async id=>loadGame(id)', identity)
    page.locator('#theme-open').click()
    page.locator('#theme-dialog [data-pixel-setting]').set_checked(True)
    page.evaluate('GameThemes.saved')
    page.locator('[data-close-dialog=theme-dialog]').click()
    before=page.evaluate('JSON.stringify(game)')
    page.locator('#npc-event-art .npc-art-figure').wait_for(state='visible')
    page.locator('.npc-event-person').click()
    page.locator('#npc-art-dialog img').wait_for(state='visible')
    page.locator('#npc-art-dialog header button').click()
    page.locator('.hud-identity').click()
    page.wait_for_function("document.querySelector('.pixel-details-art canvas')?.dataset.actor==='actor.human.demonic.female'")
    assert page.locator('.pixel-details-art canvas').evaluate("c=>c.width===256&&c.height===288&&c.getContext('2d').getImageData(0,0,c.width,c.height).data.filter((v,i)=>i%4===3&&v>0).length>500")
    page.locator('[data-close-dialog=player-details-dialog]').click()
    navigation_locator(page,'[data-panel-target=settings]').click()
    page.locator('[data-voisinage-editor]').click()
    page.wait_for_function('VoisinageEditor.status().ready')
    assert page.evaluate('VoisinageEditor.status().previewActor')=='demonic-female'
    assert page.locator('#ve-pattern option').count()==13
    page.locator('#ve-outline').select_option('time')
    page.locator('#ve-pattern').select_option('time')
    page.locator('#ve-color-hex').fill('#98baca')
    page.locator('#ve-save').click()
    page.wait_for_function('!VoisinageEditor.status().busy')
    assert '已保存' in page.locator('#ve-status').inner_text()
    for width,height in [(1440,960),(390,844)]:
        page.set_viewport_size(dict(width=width,height=height))
        assert page.locator('#voisinage-editor').evaluate('d=>d.scrollWidth<=d.clientWidth+1')
        page.screenshot(path=str(output/f'alpha3-{width}.png'))
    page.locator('#ve-close').click()
    page.reload();page.wait_for_function('!!configData')
    page.evaluate('async id=>loadGame(id)',identity)
    navigation_locator(page,'[data-panel-target=settings]').click()
    page.locator('[data-voisinage-editor]').click();page.wait_for_function('VoisinageEditor.status().ready')
    assert page.evaluate('VoisinageEditor.status().draft.palette')=='#98baca'
    assert page.evaluate('VoisinageEditor.status().draft.pattern')=='time'
    assert page.evaluate('JSON.stringify(game)')==before
