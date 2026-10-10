"""Use the actual category controls before clicking an existing feature button."""
def navigation_locator(page, selector):
    target=page.locator(selector)
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
