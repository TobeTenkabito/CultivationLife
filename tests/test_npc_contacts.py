import copy
import random
from unittest.mock import patch

import pytest
from test_immortal_cultivation import prepared
from cultivation_life.models import SectNpc


def person(g, key='contact', realm=8, cached=False):
    npc = SectNpc(id=key, name='云笺客', title='故人', realm_index=realm, layer=1,
                  age=1000, lifespan=None, world='celestial', affinity=80, gender='female', spirit_root='supreme_metal')
    if cached: g.encounter_npc_cache.append({'id':key,'npc':npc.to_dict(), 'last_seen_age':g.player.age})
    else: g.notable_npcs[key]=npc
    return npc


def test_directory_read_does_not_promote_or_roll_and_affinity_survives_reload(prepared):
    e,g,_=prepared; n=person(g,cached=True);e.store.save(g)
    before=copy.deepcopy(g.encounter_npc_cache);rng=g.rng_state
    row=next(r for r in e.get_game(g.id)['world_npcs'] if r['id']==n.id)
    assert row['contact_source']=='pool' and row['contact_actions']['improve']==''
    assert e._load(g.id).encounter_npc_cache==before and e._load(g.id).rng_state==rng
    e.contact_action(g.id,n.id,'improve'); saved=e._load(g.id)
    assert saved.notable_npcs[n.id].affinity>80
    with pytest.raises(ValueError,match='已与此人交流'):e.contact_action(g.id,n.id,'worsen')
    saved.player.age+=100;e.store.save(saved)
    e.contact_action(g.id,n.id,'worsen')
    assert e._load(g.id).notable_npcs[n.id].affinity<saved.notable_npcs[n.id].affinity


def test_known_master_without_sect_uses_existing_acceptance_and_attempt_limit(prepared):
    e,g,_=prepared;n=person(g,realm=10,cached=True);g.player.master=None;g.player.faction_id=None;e.store.save(g)
    with patch('cultivation_life.engine.actions.relationships.decode_rng',return_value=random.Random(1)):
        e.contact_action(g.id,n.id,'master')
    saved=e._load(g.id)
    assert saved.player.master['source']=='world'
    assert f'master:{n.id}' in saved.player.relationship_attempts
    assert saved.history[-1].result in {'master_accepted','rejected'}
    with pytest.raises(ValueError):e.contact_action(g.id,n.id,'master')


def test_known_disciple_and_existing_friend_service(prepared):
    e,g,_=prepared;n=person(g);e.store.save(g)
    e.contact_action(g.id,n.id,'friend')
    assert any(r['id']==n.id for r in e._load(g.id).player.dao_friends)
    e.contact_action(g.id,n.id,'disciple')
    assert f'disciple:{n.id}' in e._load(g.id).player.relationship_attempts


@pytest.mark.parametrize('blocked',['dead','away','event','trial','prison','unknown'])
def test_stale_or_blocked_contact_rejects_without_save_mutation(prepared,blocked):
    e,g,_=prepared;n=person(g)
    if blocked=='dead':n.alive=False
    if blocked=='away':n.world='spirit'
    if blocked=='event':g.pending_event={'id':'pending'}
    if blocked=='trial':g.active_trial={'kind':'backlash'}
    if blocked=='prison':g.player.imprisonment={'kind':'prison'}
    e.store.save(g);before=e.store.load(g.id).to_dict()
    with patch.object(e,'_load',return_value=g), pytest.raises(ValueError):
        e.contact_action(g.id,'missing' if blocked=='unknown' else n.id,'improve')
    assert e.store.load(g.id).to_dict()==before


def test_capture_and_betrayal_use_real_combat_target_and_exclude_victim(prepared):
    e,g,_=prepared;n=person(g);g.player.path='demonic';e.store.save(g)
    with patch.object(e,'_combat',return_value=('victory_escape','对方脱逃')) as combat:
        e.contact_action(g.id,n.id,'capture')
        target=combat.call_args.args[1]
        assert target['capture'] and target['npc_id']==n.id and not target['kill_karma']
        assert combat.call_args.args[2] is False and n.id in target['exclude_allied_ids']
    g=e._load(g.id);g.player.dao_friends=[dict(id=n.id,name=n.name,world=n.world,alive=True,realm_index=8,layer=1)];e.store.save(g)
    with patch.object(e,'_combat',return_value=('victory_escape','对方脱逃')):
        e.contact_action(g.id,n.id,'slay')
    assert not e._load(g.id).player.dao_friends
    assert e._load(g.id).notable_npcs[n.id].affinity==-100


def test_sect_roster_exposes_same_actions_without_creating_npcs(prepared):
    e,g,_=prepared
    sect=next(s for s in g.sects.values() if s.world=='celestial' and not s.extinct and s.npcs)
    g.player.faction_id=sect.id;e.store.save(g)
    shown=e.get_game(g.id)
    rows=[r for r in shown['faction']['roster'] if not r['is_player']]
    assert rows and all('contact_actions' in r for r in rows)
    npc_id=rows[0]['id'];before=e._find_npc(e._load(g.id),npc_id).affinity or 0
    e.contact_action(g.id,npc_id,'improve')
    assert e._find_npc(e._load(g.id),npc_id).affinity>before


def test_every_contact_action_rechecks_world_after_target_leaves(prepared):
    e,g,_=prepared;n=person(g);n.world='spirit';n.departed_age=g.player.age;e.store.save(g)
    shown=e.get_game(g.id)
    row=next(r for r in shown['world_npcs'] if r['id']==n.id)
    assert not row['perceived_alive'] and all(row['contact_actions'].values())
    for action in row['contact_actions']:
        with pytest.raises(ValueError,match='当前界面'):e.contact_action(g.id,n.id,action)


def test_affinity_path_bonus_applies_once(prepared):
    e,g,_=prepared;n=person(g);e.store.save(g)
    with patch.object(e,'_sage_affinity_gain',side_effect=lambda p,delta:delta*2):
        e.contact_action(g.id,n.id,'improve')
    saved=e._load(g.id);delta=saved.history[-1].state_diff['affinity']
    assert 8<=delta<=16 and saved.notable_npcs[n.id].affinity==80+delta
