"""One page at a time: rejected stale writes, earned followups and real plant forging."""
import copy
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
import browser_other_systems_audit_fixes as harness
from test_crafting_field_audit_fixes import (new_game, snapshot, field_game, basic_recipe,
                                            blocking_state, helper_game, stacked_recipe)
from scripts.browser_navigation import navigation_locator, click_control, reveal_subpage


def verify(page, engine, width):
    def act(identity, operation, **payload):
        return page.evaluate('''async ({identity,operation,payload}) =>
            api(`/api/games/${identity}/${operation}`, {method:'POST',body:JSON.stringify(payload)})''',
            dict(identity=identity, operation=operation, payload=payload))

    def rejected_once(endpoint, target, identity):
        frozen = snapshot(engine, identity)
        requests = []
        observe = lambda request: requests.append((request.method, request.url))
        page.on('request', observe)
        try:
            harness.click_post(page, endpoint, target, status=400)
            assert engine.store._path(identity).read_bytes() == frozen
            assert sum(method=='POST' and url.endswith('/'+endpoint) for method,url in requests)==1
            assert sum(method=='GET' and url.endswith('/'+identity) for method,url in requests)==1
        finally:
            page.remove_listener('request', observe)
        page.wait_for_function('!busy && !document.body.classList.contains("busy")')

    # An NPC who was eligible on the old page may be imprisoned before commit.
    game, identity, payload = helper_game(engine, act)
    page.evaluate('async id=>loadGame(id)',game.id)
    click_control(navigation_locator(page,'[data-panel-target=talisman]'))
    tier = page.get_by_label('符箓阶数',exact=True)
    tier.select_option('1')
    page.get_by_label('制符法',exact=True).select_option(payload['method_id'])
    page.get_by_label('材料一',exact=True).select_option(payload['material1'])
    page.get_by_label('材料二',exact=True).select_option(payload['material2'])
    page.get_by_label('法术灵力',exact=True).select_option('water')
    page.get_by_label('注灵修士',exact=True).select_option(identity)
    act(game.id,'intrigue-personnel',kind='sect',action='imprison',npc_id=identity,years=100)
    rejected_once('talisman-action',page.get_by_role('button',name='炼制符箓',exact=True),game.id)
    assert identity not in page.get_by_label('注灵修士',exact=True).locator('option').evaluate_all('(rows)=>rows.map(r=>r.value)')
    act(game.id,'intrigue-personnel',kind='sect',action='release',npc_id=identity)
    page.evaluate('async id=>loadGame(id)',game.id)
    page.get_by_label('符箓阶数',exact=True).select_option('1')
    page.get_by_label('制符法',exact=True).select_option(payload['method_id'])
    page.get_by_label('材料一',exact=True).select_option(payload['material1'])
    page.get_by_label('材料二',exact=True).select_option(payload['material2'])
    page.get_by_label('法术灵力',exact=True).select_option('water')
    page.get_by_label('注灵修士',exact=True).select_option(identity)
    harness.click_post(page,'talisman-action',page.get_by_role('button',name='炼制符箓',exact=True))
    assert len(engine._load(game.id).player.talismans)==1
    click_control(page.locator('#talisman-toggle'))

    game = field_game(engine,act)
    page.evaluate('async id=>loadGame(id)',game.id)
    click_control(navigation_locator(page,'[data-panel-target=spirit-field]'))
    harvest = page.locator('#spirit-field-card').get_by_role('button',name='采收',exact=True,include_hidden=True)
    reveal_subpage(page,harvest)
    assert harvest.is_enabled()
    changed = blocking_state(engine,engine._load(game.id),followup=True)
    reward = copy.deepcopy(changed.pending_event['_followup_event'])
    rejected_once('spirit-field-harvest',harvest,game.id)
    page.evaluate('renderButtons()')
    assert harvest.is_disabled()
    click_control(page.locator('#spirit-field-toggle'))
    harness.click_post(page,'choice',harness.choice_button(page,engine,game.id,'acknowledge'))
    assert engine._load(game.id).pending_event['runtime']==reward['runtime']
    harness.click_post(page,'choice',harness.choice_button(page,engine,game.id,'pill'))
    click_control(navigation_locator(page,'[data-panel-target=spirit-field]'))
    reveal_subpage(page,harvest)
    assert harvest.is_enabled()
    harness.click_post(page,'spirit-field-harvest',harvest)
    assert not engine._load(game.id).player.spirit_field['plots']
    click_control(page.locator('#spirit-field-toggle'))

    game = new_game(engine,realm=4)
    payload = basic_recipe(engine,game)
    engine.store.save(game)
    engine.forge_crafted_artifact(game.id,payload)
    game = engine._load(game.id)
    identity = game.player.crafted_artifacts[-1]['id']
    page.evaluate('async id=>loadGame(id)',game.id)
    click_control(navigation_locator(page,'[data-panel-target=inventory]'))
    sell = page.locator('#inventory-card').get_by_role('button',name=re.compile('坊市出售'),include_hidden=True)
    reveal_subpage(page,sell)
    click_control(sell)
    blocking_state(engine,engine._load(game.id))
    rejected_once('crafted-artifact',page.locator('#game-confirm-accept'),game.id)
    page.evaluate('renderButtons()')
    assert sell.is_disabled()
    click_control(page.locator('#inventory-toggle'))
    harness.click_post(page,'choice',harness.choice_button(page,engine,game.id,'acknowledge'))
    click_control(navigation_locator(page,'[data-panel-target=inventory]'))
    reveal_subpage(page,sell)
    assert sell.is_enabled()
    click_control(sell)
    harness.click_post(page,'crafted-artifact',page.locator('#game-confirm-accept'))
    assert not any(a['id']==identity for a in engine._load(game.id).player.crafted_artifacts)
    click_control(page.locator('#inventory-toggle'))

    game, identity, payload = stacked_recipe(engine,act)
    rows = [r for r in engine.get_game(game.id)['crafting_system']['materials'] if r.get('inventory_item_id')==identity]
    assert len(rows)==2
    payload.update(secondary_a_id=rows[0]['id'],secondary_b_id=rows[1]['id'])
    page.evaluate('async id=>loadGame(id)',game.id)
    click_control(navigation_locator(page,'[data-panel-target=crafting]'))
    page.locator('#crafting-mode').select_option('free')
    page.locator('#crafting-mold').select_option(payload['mold_id'])
    for selector,key in [('primary','primary_id'),('secondary-a','secondary_a_id'),
                         ('secondary-b','secondary_b_id'),('quench','quench_id')]:
        page.locator('#crafting-'+selector).select_option(payload[key])
    page.locator('#crafting-allocations input[data-stat=combat_power]').fill('10')
    harness.click_post(page,'crafting-preview',page.locator('#crafting-preview'))
    click_control(page.locator('#crafting-preview-result').get_by_role('button',name='确认开炉',exact=True))
    harness.click_post(page,'crafting-forge',page.locator('#game-confirm-accept'))
    saved = engine._load(game.id)
    assert not any(i.id==identity for i in saved.player.inventory)
    assert len(saved.player.crafted_artifacts)==1
    page.wait_for_function('!busy && !document.body.classList.contains("busy")')
    print(f'Craft/field repairs {width}px: stale helper/harvest/sale rejected once, followup reward, release recovery, two real stacked plants forged',flush=True)


if __name__=='__main__':
    harness.verify=verify
    harness.main()
