"""Real reading and saved-book clicks, reusable against source and compiled HTTP."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from scripts.browser_navigation import navigation_locator, click_control
from fixtures.technique_names_release import BOOK, inspect_technique_names

TERMS = (
    ('界面导览','interface-guide'), ('通用功法','common-techniques'),
    ('肉身、神魂','body-soul'), ('第二元婴：','second-nascent'),
    ('夺舍与转道','possession-path'), ('诸天见闻','heavens-intelligence'),
    ('授权、派驻','heavens-outposts'), ('连续扩张','heavens-development'),
    ('军令、会战','heavens-conquest'), ('故人笺：','contacts-promises'),
    ('宗门差事','sect-task-board'), ('岁月与远行','regional-time'),
    ('战报、回放','combat-review'), ('功业录与衣橱','achievements-wardrobe'),
)


def verify_revision(page, engine, identity, output, label):
    """Caller prepares an isolated old-display fixture before loading its page."""
    click_control(page.locator('.hud-identity'))
    if not page.locator('.technique-library').evaluate('e=>e.open'):
        click_control(page.locator('.technique-library > summary'))
    text = page.locator('#known-technique-list').inner_text()
    assert '抱朴养真经' in text and '晦烛含魄篇' in text
    assert '长夜抱朴归真经' not in text and '松窗抱朴归真经' not in text
    row = page.locator('#known-technique-list .known-technique').filter(has_text='抱朴养真经')
    with page.expect_response(lambda r:r.url.endswith('/technique-upgrade')) as response:
        click_control(row.locator('.technique-upgrade'))
    assert response.value.status == 200
    page.wait_for_function('id=>!busy&&game.player.known_techniques.some(t=>t.id===id&&t.level===6)',arg=BOOK)
    inspect_technique_names(engine, identity, upgraded=True)
    click_control(page.locator('[data-close-dialog=player-details-dialog]'))
    before = engine.store._path(identity).read_bytes()
    navigation_locator(page,'[data-panel-target=settings]').click()
    click_control(page.locator('.handbook-categories button',has_text='全部'))
    for term, chapter in TERMS:
        page.locator('#handbook-search').fill(term)
        article = page.locator(f'[data-chapter="{chapter}"]')
        assert article.is_visible() and article.evaluate('e=>e.open'),chapter
        assert article.evaluate('e=>e.scrollWidth<=e.clientWidth+2'),chapter
    loaded = page.evaluate("configData.extensions.some(e=>e.id==='official.authored-techniques'&&e.status==='loaded')")
    assert page.locator('[data-chapter=dlc-authored]').count() == int(loaded)
    if loaded:
        page.locator('#handbook-search').fill('著经立道：创法')
        assert page.locator('[data-chapter=dlc-authored]').is_visible()
    page.locator('#handbook-search').fill('跨界开拓：')
    page.locator('[data-chapter=heavens-outposts] summary').scroll_into_view_if_needed()
    page.screenshot(path=str(output/f'handbook-{label}.png'))
    assert page.locator('#settings-card').evaluate('e=>e.scrollWidth<=e.clientWidth+2')
    assert engine.store._path(identity).read_bytes() == before,'Reading changed a save'
    click_control(page.locator('#settings-toggle'))

