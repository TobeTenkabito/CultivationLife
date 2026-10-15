"""Real page clicks, stale confirmations and organization votes, serial viewports."""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
import browser_other_systems_audit_fixes as harness
from test_ownership_prison_fixes import organization_game, forged_game
from test_crafting_field_audit_fixes import blocking_state
from test_other_systems_audit_fixes import snapshot
from scripts.browser_navigation import navigation_locator, click_control, reveal_subpage


def verify(page, engine, width):
    def act(identity, operation, **payload):
        return page.evaluate('''async ({identity,operation,payload})=>
            api(`/api/games/${identity}/${operation}`,{method:'POST',body:JSON.stringify(payload)})''',
            dict(identity=identity, operation=operation, payload=payload))

    def refused_once(endpoint, button, identity):
        frozen = snapshot(engine, identity)
        requests = []
        observe = lambda request: requests.append((request.method, request.url))
        page.on('request', observe)
        try:
            harness.click_post(page, endpoint, button, status=400)
            assert engine.store._path(identity).read_bytes() == frozen
            assert sum(method=='POST' and url.endswith('/'+endpoint) for method,url in requests)==1
            assert sum(method=='GET' and url.endswith('/'+identity) for method,url in requests)==1
        finally:
            page.remove_listener('request', observe)
        page.wait_for_function('!busy && !document.body.classList.contains("busy")')

    # A legal member visible before another command is no longer a legal stale target.
    for kind, label in [('sect','宗门'), ('family','家族')]:
        game, identity = organization_game(engine, kind)
        page.evaluate('async id=>loadGame(id)', game.id)
        click_control(navigation_locator(page, '[data-panel-target=intrigue]'))
        form = page.locator(f'.intrigue-{kind} .intrigue-resolution-form')
        reveal_subpage(page, form)
        form.get_by_label(label+'决议类型', exact=True).select_option('imprison_member')
        form.get_by_label(label+'决议目标', exact=True).select_option(identity)
        form.get_by_label(label+'监禁年数', exact=True).fill('7')
        form.get_by_label(label+'监禁事由', exact=True).fill('侵占组织资材')
        submit = form.get_by_role('button', name='提交议事', exact=True)
        if kind == 'sect':
            act(game.id, 'intrigue-personnel', kind=kind, action='imprison', npc_id=identity, years=9)
            refused_once('intrigue-resolution', submit, game.id)
            page.evaluate('renderButtons()')
            form.get_by_label(label+'决议类型', exact=True).select_option('imprison_member')
            assert submit.is_disabled()
            # The existing release control restores eligibility, using the real button.
            details = page.locator(f'.intrigue-{kind} .intrigue-details').first
            click_control(details.locator('summary'))
            harness.click_post(page, 'intrigue-personnel', details.get_by_role('button', name='释放', exact=True))
            form.get_by_label(label+'决议类型', exact=True).select_option('imprison_member')
            form.get_by_label(label+'决议目标', exact=True).select_option(identity)
            form.get_by_label(label+'监禁年数', exact=True).fill('7')
            form.get_by_label(label+'监禁事由', exact=True).fill('侵占组织资材')
        harness.click_post(page, 'intrigue-resolution', submit)
        saved = engine._load(game.id)
        assert engine._intrigue_is_imprisoned(saved, identity)
        record = saved.intrigue_state['factions'][kind+':audit_org']
        assert record['prison'][0]['sentence_remaining']==7
        assert record['prison'][0]['reason']=='侵占组织资材'
        form.get_by_label(label+'决议类型', exact=True).select_option('imprison_member')
        assert submit.is_disabled()
        assert form.get_by_label(label+'决议目标', exact=True).input_value()==''
        click_control(page.locator('#intrigue-toggle'))

    # A confirmation opened before an event cannot mutate a bound item or lose the reward.
    game, identity = forged_game(engine, act)
    page.evaluate('async id=>loadGame(id)', game.id)
    click_control(navigation_locator(page, '[data-panel-target=inventory]'))
    bind = page.locator('#inventory-card').get_by_role('button', name='炼为本命', exact=True, include_hidden=True)
    click_control(bind)
    changed = blocking_state(engine, engine._load(game.id), followup=True)
    reward = copy.deepcopy(changed.pending_event['_followup_event'])
    refused_once('crafted-artifact', page.locator('#game-confirm-accept'), game.id)
    page.evaluate('renderButtons()')
    assert bind.is_disabled()
    click_control(page.locator('#inventory-toggle'))
    harness.click_post(page, 'choice', harness.choice_button(page, engine, game.id, 'acknowledge'))
    assert engine._load(game.id).pending_event['runtime']==reward['runtime']
    harness.click_post(page, 'choice', harness.choice_button(page, engine, game.id, 'pill'))
    click_control(navigation_locator(page, '[data-panel-target=inventory]'))
    reveal_subpage(page, bind)
    assert bind.is_enabled()
    click_control(bind)
    harness.click_post(page, 'crafted-artifact', page.locator('#game-confirm-accept'))
    assert engine._load(game.id).natal_artifact['crafted_artifact_id']==identity
    click_control(page.locator('#inventory-toggle'))

    game, _ = forged_game(engine, act, realm=1)
    page.evaluate('async id=>loadGame(id)', game.id)
    click_control(navigation_locator(page, '[data-panel-target=inventory]'))
    reveal_subpage(page, bind)
    assert bind.is_disabled()
    print(f'Ownership/prison UI passed: {width}px; lawful votes, release, stale recovery, followup reward, realm lock.', flush=True)


if __name__=='__main__':
    harness.verify = verify
    harness.main()
