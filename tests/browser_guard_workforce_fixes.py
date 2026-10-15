"""Sequential real desktop/mobile defense clicks after headquarters relocation."""
import copy
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
import browser_other_systems_audit_fixes as harness
from test_guard_workforce_fixes import ready_org, deploy_guard, defense_event


def verify(page, engine, width):
    def act(identity, operation, **payload):
        return page.evaluate('''async ({identity,operation,payload})=>
            api(`/api/games/${identity}/${operation}`,{method:'POST',body:JSON.stringify(payload)})''',
            dict(identity=identity,operation=operation,payload=payload))

    game, _ = ready_org(engine)
    game = deploy_guard(engine,act,game)
    original = copy.deepcopy(game.player.formation_ground_arrays[0])
    event = defense_event(engine,game,followup=True)
    reward = copy.deepcopy(event['_followup_event'])
    page.evaluate('async id=>loadGame(id)',game.id)
    stale = harness.choice_button(page,engine,game.id,'formation')
    assert stale.is_enabled()
    # An old visible event page survives another legal command session's move.
    game = engine._load(game.id)
    game.pending_event = None
    engine.store.save(game)
    plan = next(r for r in engine.get_game(game.id)['map']['organization_relocation'] if r['kind']=='sect')
    destination = plan['destinations'][0]['id']
    act(game.id,'organization-action',kind='sect',owner_id='audit_org',action='relocate',location_id=destination)
    act(game.id,'map-travel',destination=destination)
    game = engine._load(game.id)
    game.pending_event = copy.deepcopy(event)
    engine.store.save(game)
    harness.click_post(page,'choice',stale)
    saved = engine._load(game.id)
    assert saved.sects['audit_org'].pressure==1
    assert saved.player.formation_ground_arrays==[original]
    assert saved.pending_event['runtime']==reward['runtime']
    assert not page.evaluate('game.formation_system.operation_available')
    harness.click_post(page,'choice',harness.choice_button(page,engine,game.id,'pill'))
    page.wait_for_function('!busy && !game.pending_event && !document.body.classList.contains("busy")')
    assert page.evaluate('game.formation_system.operation_available')
    # New, actually deployed materials restore defense, without moving the old array.
    saved = deploy_guard(engine,act,engine._load(game.id))
    defense_event(engine,saved)
    page.evaluate('async id=>loadGame(id)',game.id)
    harness.click_post(page,'choice',harness.choice_button(page,engine,game.id,'formation'))
    page.wait_for_function('!busy && !game.pending_event')
    saved = engine._load(game.id)
    assert saved.sects['audit_org'].pressure==1
    assert saved.player.formation_ground_arrays[0]==original
    assert saved.player.formation_ground_arrays[-1]['battles']==1
    assert saved.player.formation_ground_arrays[-1]['location_id']==destination
    print(f'Guard location UI passed: {width}px, stale page, original materials unchanged, followup reward, busy reset, rebuilt local defense',flush=True)


if __name__=='__main__':
    harness.verify=verify
    harness.main()
