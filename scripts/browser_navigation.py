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
