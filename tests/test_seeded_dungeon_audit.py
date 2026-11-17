"""Adversarial saved-state scenarios exercised through the real command boundary."""
import pytest
from test_seeded_dungeons import local, discover, act
from cultivation_life.system.dungeons.people import materialize


@pytest.mark.parametrize('action',['learn','study'])
def test_empty_manual_request_is_a_domain_error_without_mutation(local,action):
    engine,game=local
    engine.get_game(game.id)  # Settle ordinary first-load preparation before testing command atomicity.
    before=engine.store.load(game.id).to_dict()
    with pytest.raises(ValueError,match='传承'):
        engine.dungeon_action(game.id,action,{'manual_id':'missing'})
    assert engine.store.load(game.id).to_dict()==before


def test_missing_first_invitee_does_not_hide_later_invitation(local):
    engine,game=local;discover(engine,game)
    saved=engine.store.load(game.id);site=next(iter(saved.dungeon_state['instances'].values()))
    first,second=list(site['roles'].values())[:2]
    materialize(saved,site,first).alive=False
    for role in (first,second):role.update(state='invited',known=True)
    engine.store.save(saved)
    shown=act(engine,game,'enter')
    saved=engine.store.load(game.id);site=saved.dungeon_state['instances'][site['id']]
    assert site['roles'][first['id']]['state']=='missing'
    assert site['pending'] and site['pending']['actor']==second['id']
    assert any('没有按约出现' in row['text'] for row in shown['dungeons']['session']['logs'])
    act(engine,game,'choose',choice='accept')
    assert engine.get_game(game.id)['dungeons']['session']['party_count']==2


def test_captive_former_guard_cannot_block_a_later_node(local):
    engine,game=local;discover(engine,game);act(engine,game,'enter')
    saved=engine.store.load(game.id);site=saved.dungeon_state['instances'][saved.dungeon_state['active']]
    site['step']=len(site['nodes'])-1
    node=site['nodes'][site['step']];role=site['roles'][node['actor']]
    npc=materialize(saved,site,role)
    saved.detain_person(npc.to_dict(),kind='prisoner')
    role.update(state='left',known=True)
    engine.store.save(saved)
    shown=act(engine,game,'choose',choice='seize')
    saved=engine.store.load(game.id);site=saved.dungeon_state['instances'][site['id']]
    assert site['pending'] is None
    assert node['reward']['id'] in site['claims']
    assert not any(choice['id']=='fight' for choice in shown['dungeons']['session']['choices'])
    act(engine,game,'exit')


def test_saved_guardian_prompt_recovers_when_original_person_is_detained(local):
    engine,game=local;discover(engine,game);act(engine,game,'enter')
    saved=engine.store.load(game.id);site=saved.dungeon_state['instances'][saved.dungeon_state['active']]
    role=next(iter(site['roles'].values()));npc=materialize(saved,site,role)
    role.update(state='hostile',known=True)
    site['pending']=dict(kind='guardian',actor=role['id'])
    saved.detain_person(npc.to_dict(),kind='prisoner');engine.store.save(saved)
    shown=act(engine,game,'choose',choice='fight')
    assert not engine.store.load(game.id).dungeon_state['instances'][site['id']]['pending']
    assert any('重新查看' in row['text'] for row in shown['dungeons']['session']['logs'])
    assert not engine.store.load(game.id).last_combat_report
    act(engine,game,'exit')
