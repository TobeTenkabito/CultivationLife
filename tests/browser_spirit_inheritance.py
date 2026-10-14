"""One page at a time: actual inheritance and branch-specific post-load controls."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
import browser_other_systems_audit_fixes as harness
from test_spirit_inheritance import prepared
from scripts.browser_navigation import navigation_locator, click_control


def verify(page, engine, width):
    # A stale enabled button must reject once, reload once and become unavailable.
    game, _ = prepared(engine, source_world='asura')
    page.evaluate('async id=>loadGame(id)', game.id)
    click_control(navigation_locator(page, '[data-panel-target=immortal-aperture]'))
    click_control(page.locator('#immortal-aperture-content > details > summary'))
    stale = page.locator('[data-inheritance-action]').first
    assert stale.is_enabled()
    changed = engine._load(game.id)
    changed.player.immortal_traces = 0
    engine.store.save(changed)
    frozen = engine.store._path(game.id).read_bytes()
    harness.click_post(page, 'aperture-action', stale, status=400)
    assert engine.store._path(game.id).read_bytes() == frozen
    click_control(page.locator('#immortal-aperture-content > details > summary'))
    assert page.locator('[data-inheritance-action]').first.is_disabled()
    click_control(page.locator('#immortal-aperture-toggle'))
    for world,path in [('celestial','dao'),('asura','dao'),('nether','dao'),('reincarnation','dao'),
                       ('asura','demonic'),('nether','monster'),('reincarnation','ghost')]:
        game, book = prepared(engine, world, path, source_world='asura')
        p = game.player
        if path == 'demonic':
            p.asura_cultivation.update(route='yaksha', conversion=5, souls=10000, level=4, domain_rank=3, domain_power=2, domain_name='本命')
        if path == 'monster':
            from cultivation_life.system import monster_true_form as form
            p.monster_evolution_id = 'SERPENT_NETHER_TRUE_1'
            form.configure(p, 'true_form_confirm', form.public(p)['choices'][0])
        if path == 'ghost':
            from cultivation_life.system import ghost_soul_form as form
            cause, route = next(iter(form.catalog()['forms'])).split('.')
            form.confirm(game, cause, route)
        engine.store.save(game)
        page.evaluate('async id=>loadGame(id)', game.id)
        click_control(navigation_locator(page, '[data-panel-target=immortal-aperture]'))
        click_control(page.locator('#immortal-aperture-content > details > summary'))
        entry=page.locator('[data-inheritance-manual]').filter(has=page.locator('[data-inheritance-action]')).first
        button=entry.locator('[data-inheritance-action]')
        assert button.is_enabled(), entry.inner_text()
        harness.click_post(page, 'aperture-action', button)
        assert not page.evaluate('busy')
        entry=page.locator('[data-inheritance-manual]').first
        # Rerender collapses this disclosure; reopen and inspect the authoritative denial.
        click_control(page.locator('#immortal-aperture-content > details > summary'))
        assert entry.locator('[data-inheritance-action]').is_disabled()
        assert '已经完成' in entry.inner_text()
        click_control(page.locator('#immortal-aperture-toggle'))
        print(f'Inheritance UI {width}px: {world}/{path}', flush=True)


if __name__ == '__main__':
    harness.verify=verify
    harness.main()
