"""Exercise the visible owner of each Westward feature after the 3.6.1 layout."""
import json
from scripts.browser_navigation import navigation_locator,click_control

def open_westward(page,name):
    if name in ('地仙庙域','仙圃','功德修缮'):
        if not page.locator('#map-card').is_visible():navigation_locator(page,'[data-panel-target=map]').click()
        page.locator('#map-view-tabs [aria-controls=map-atlas]').click()
        page.locator('#map-atlas [aria-label="地图地点"]').select_option(page.evaluate('game.map.current'))
        if name=='地仙庙域':
            identity=page.evaluate("game.yaochi.earth.local?game.yaochi.earth.temple.id:game.yaochi.earth.cities.find(c=>!c.reason)?.id||game.yaochi.earth.cities[0]?.id")
        elif name=='仙圃':identity=page.evaluate("game.yaochi.garden.building_id")
        else:identity=page.evaluate('game.yaochi.relief.offers[0].id')
        target=page.locator('#map-atlas [data-building-affairs='+json.dumps(identity,ensure_ascii=False)+']')
        click_control(target.first)
        page.locator('#building-affairs-card').wait_for()
        return
    owner='immortal-practice' if name in ('专修','仙籍与功德') else 'immortal-estate' if name in ('访古','紫气东来') else 'yaochi'
    if not page.locator('#'+owner+'-card').is_visible():navigation_locator(page,'[data-panel-target='+owner+']').click()
    page.locator('#'+owner+'-content [data-subpage="'+name+'"]').click()
