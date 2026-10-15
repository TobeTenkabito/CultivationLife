"""Real page clicks for prison records and stale formation writes; serial pages."""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
import browser_other_systems_audit_fixes as harness
from test_custody_formation_fixes import detached_prisoner, prepare_operation, OPERATIONS
from test_ownership_prison_fixes import organization_game
from test_crafting_field_audit_fixes import blocking_state
from test_other_systems_audit_fixes import snapshot
from scripts.browser_navigation import navigation_locator, click_control, reveal_subpage


def verify(page, engine, width):
    def act(identity, operation, **payload):
        return page.evaluate('''async ({identity,operation,payload})=>
            api(`/api/games/${identity}/${operation}`,{method:'POST',body:JSON.stringify(payload)})''',
            dict(identity=identity, operation=operation, payload=payload))

    def refused_once(endpoint, target, identity):
        frozen = snapshot(engine, identity)
        requests = []
        observe = lambda request: requests.append((request.method, request.url))
        page.on('request', observe)
        try:
            harness.click_post(page, endpoint, target, status=400)
            assert engine.store._path(identity).read_bytes()==frozen
            assert sum(method=='POST' and url.endswith('/'+endpoint) for method,url in requests)==1
            assert sum(method=='GET' and url.endswith('/'+identity) for method,url in requests)==1
        finally:
            page.remove_listener('request', observe)
        page.wait_for_function('!busy && !document.body.classList.contains("busy")')

    for kind in ['sect','family']:
        game, identity = detached_prisoner(engine, act, kind)
        page.evaluate('async id=>loadGame(id)',game.id)
        click_control(navigation_locator(page,'[data-panel-target=intrigue]'))
        details = page.locator(f'.intrigue-{kind} .intrigue-detached-prisoners')
        click_control(details.locator('summary'))
        harness.click_post(page,'intrigue-personnel',details.get_by_role('button',name='释放',exact=True))
        assert not engine._intrigue_is_imprisoned(engine._load(game.id),identity)
        assert details.count()==0
        click_control(page.locator('#intrigue-toggle'))

    game, identity = detached_prisoner(engine, act)
    page.evaluate('async id=>loadGame(id)',game.id)
    click_control(navigation_locator(page,'[data-panel-target=intrigue]'))
    details = page.locator('.intrigue-sect .intrigue-detached-prisoners')
    click_control(details.locator('summary'))
    act(game.id,'intrigue-personnel',kind='sect',action='release',npc_id=identity)
    refused_once('intrigue-personnel',details.get_by_role('button',name='释放',exact=True),game.id)
    assert details.count()==0
    click_control(page.locator('#intrigue-toggle'))

    game, identity = organization_game(engine)
    act(game.id,'intrigue-personnel',kind='sect',action='imprison',npc_id=identity,years=10)
    page.evaluate('async id=>loadGame(id)',game.id)
    click_control(navigation_locator(page,'[data-panel-target=intrigue]'))
    members = page.locator('.intrigue-sect .intrigue-details').first
    click_control(members.locator('summary'))
    page.evaluate('renderButtons()')
    assert members.get_by_role('button',name='逐出',exact=True).is_disabled()
    assert members.get_by_role('button',name='释放',exact=True).is_enabled()
    click_control(page.locator('#intrigue-toggle'))

    for operation in OPERATIONS:
        game, payload, identities = prepare_operation(engine,act,operation)
        page.evaluate('async id=>loadGame(id)',game.id)
        click_control(navigation_locator(page,'[data-panel-target=formation]'))
        if operation=='formation-deactivate': target=page.locator('#formation-deactivate')
        elif operation=='formation-delete':
            target=page.locator('#formation-card').get_by_role('button',name='删除',exact=True,include_hidden=True)
        elif operation=='formation-ground-withdraw':
            target=page.locator('#formation-card').get_by_role('button',name='撤阵归库',exact=True,include_hidden=True)
        else: target=page.locator('#formation-card').get_by_role('button',name='修阵',exact=True,include_hidden=True)
        reveal_subpage(page,target)
        if not operation.endswith('repair'): click_control(target)
        changed=blocking_state(engine,engine._load(game.id),followup=True)
        reward=copy.deepcopy(changed.pending_event['_followup_event'])
        refused_once(operation,target if operation.endswith('repair') else page.locator('#game-confirm-accept'),game.id)
        page.evaluate('renderButtons()')
        assert target.is_disabled()
        click_control(page.locator('#formation-toggle'))
        harness.click_post(page,'choice',harness.choice_button(page,engine,game.id,'acknowledge'))
        assert engine._load(game.id).pending_event['runtime']==reward['runtime']
        harness.click_post(page,'choice',harness.choice_button(page,engine,game.id,'pill'))
        click_control(navigation_locator(page,'[data-panel-target=formation]'))
        reveal_subpage(page,target)
        assert target.is_enabled()
        if operation.endswith('repair'):
            harness.click_post(page,operation,target)
        else:
            click_control(target)
            harness.click_post(page,operation,page.locator('#game-confirm-accept'))
        saved=engine._load(game.id)
        if operation.endswith('repair'):
            assert saved.player.formation_repair_supplies[payload['supply_id']]==1
            assert saved.player.formation_ground_arrays[0]['durability']>20
        else:
            assert len([r for r in saved.player.formation_materials if r['id'] in identities])==3
        click_control(page.locator('#formation-toggle'))
    print(f'Custody/formation UI passed: {width}px; detached release, stale recovery, disabled expel, four formation writes, earned rewards.',flush=True)


if __name__=='__main__':
    harness.verify=verify
    harness.main()
