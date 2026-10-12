"""Use a visible desktop control or reveal it through the compact categories."""
def navigation_locator(page, selector):
    target=page.locator(selector)
    if target.is_visible():
        return target
    group=target.evaluate('node=>node.dataset.navigationGroup')
    if group:
        if page.locator('#navigation-menu').evaluate('node=>node.open'):
            tab=page.locator(f'[data-navigation-tab="{group}"]')
            if tab.get_attribute('aria-selected')!='true':
                tab.click()
        else:
            page.locator(f'[data-navigation-category="{group}"]').click()
        page.wait_for_function('document.querySelector("#navigation-menu").open')
    return target


def reveal_subpage(page, target):
    """Reveal the actual target by clicking its owning parallel-page tab."""
    for _ in range(8):
        info=target.evaluate('''node=>{let hidden=null;for(let n=node;n;n=n.parentElement)if(n.hasAttribute('data-page-hidden'))hidden=n;if(!hidden)return null;let host=hidden.parentElement;while(host&&!host.querySelector(':scope>.panel-page-tabs'))host=host.parentElement;if(!host)return null;const tab=[...host.querySelector(':scope>.panel-page-tabs').children].find(b=>b.dataset.subpage===hidden.dataset.pageName);if(!tab)return null;document.querySelectorAll('[data-test-reveal-tab]').forEach(n=>n.removeAttribute('data-test-reveal-tab'));tab.setAttribute('data-test-reveal-tab','1');return true;}''')
        if not info:return target
        page.locator('[data-test-reveal-tab]').click()
    raise AssertionError('Subpage nesting did not resolve')


def click_control(target, **kwargs):
    """Old module tests now enter the selected module through its visible tab."""
    reveal_subpage(target.page, target)
    expanded=target.evaluate("n=>n.tagName==='SUMMARY'&&n.parentElement.hasAttribute('data-page-name')&&n.parentElement.open")
    if not expanded:target.click(**kwargs)
