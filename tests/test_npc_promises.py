"""Real contact commands, shared NPC combat, stale requests and original identities."""
import copy
from contextlib import nullcontext
from pathlib import Path

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.models import SectNpc
from cultivation_life.system.npc_contacts import availability
from cultivation_life.system.npc_promises import projection


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def original(tmp_path_factory):
    engine=GameEngine(ROOT,tmp_path_factory.mktemp('promise-base'))
    return engine._load(engine.create_game('貂蝉','supreme_metal','dao',329,preset_id='core')['id'])


@pytest.fixture
def ready(tmp_path,original):
    e=GameEngine(ROOT,tmp_path)
    g=copy.deepcopy(original);g.pending_event=g.active_trial=None
    p=g.player;p.gender='female';p.lifespan=10000
    actor=SectNpc('promise-lover','吕奉先','故人',3,1,80,10000,world=p.world,
                  location_id=p.location_id,affinity=80,spirit_root='supreme_metal')
    owner=SectNpc('promise-owner','董仲颖','正主',1,1,50,10000,world=p.world,
                  location_id=p.location_id,affinity=0,spirit_root='supreme_metal')
    g.notable_npcs.update({actor.id:actor,owner.id:owner})
    p.dao_companion={'id':actor.id,'since_age':p.age}
    e._set_concubine_status(g,dict(owner_id=owner.id,owner_name=owner.name,owner_realm_index=1,
        owner_layer=1,owner_realm_name='练气',owner_world=p.world),forced=True)
    e.store.save(g)
    return e,g,actor,owner


def test_actual_promised_battle_kills_owner_unlocks_once_and_keeps_original_people(ready):
    e,g,actor,owner=ready
    before=e._load(g.id)
    assert not availability(before,before.notable_npcs[actor.id])['promise']
    result=e.contact_action(g.id,actor.id,'promise',owner.id,g.diplomacy_unit)
    assert '凤仪亭' in {r['name'] for r in result['new_achievements']}
    saved=e.store.load(g.id)
    assert not saved.notable_npcs[owner.id].alive
    assert saved.notable_npcs[actor.id].alive
    assert saved.player.concubine_status is None
    assert saved.player.dao_companion['id']==actor.id
    assert saved.player.age==g.player.age and saved.player.world==g.player.world
    record=next(r for r in reversed(saved.history) if r.event_id=='SYS_NPC_PROMISE_BATTLE')
    assert record.state_diff['killed']==[owner.id] and record.state_diff['rounds']
    assert '凤仪亭' not in {r['name'] for r in e.get_game(g.id)['new_achievements']}
    with pytest.raises(ValueError):e.contact_action(g.id,actor.id,'promise',owner.id,g.diplomacy_unit)


@pytest.mark.parametrize('invalid',['no_status','not_companion','other_owner'])
def test_kill_does_not_infer_fengyi_from_names_or_old_relations(ready,invalid):
    e,g,actor,owner=ready
    if invalid=='no_status':g.player.concubine_status=None
    elif invalid=='not_companion':g.player.dao_companion=None
    else:g.player.concubine_status['owner_id']='someone-else'
    e.store.save(g)
    result=e.contact_action(g.id,actor.id,'promise',owner.id,g.diplomacy_unit)
    assert not e.store.load(g.id).notable_npcs[owner.id].alive
    assert '凤仪亭' not in {r['name'] for r in result['new_achievements']}


@pytest.mark.parametrize('blocked',['dead_actor','dead_target','away_actor','away_target','held_actor',
    'held_target','prison_actor','prison_target','event','trial','imprisoned_player','low_affinity',
    'self','missing_target','stale','wrong_location','unknown_location','soul_crisis','other_instance','assignment'])
def test_stale_or_illegal_promise_does_not_save_roll_or_consume_quota(ready,blocked):
    e,g,actor,owner=ready;target_id=owner.id;unit=g.diplomacy_unit
    if blocked=='dead_actor':actor.alive=False
    elif blocked=='dead_target':owner.alive=False
    elif blocked=='away_actor':actor.world='spirit'
    elif blocked=='away_target':owner.world='spirit'
    elif blocked=='held_actor':actor.roster_state='held'
    elif blocked=='held_target':owner.roster_state='held'
    elif blocked=='prison_actor':g.intrigue_state['npc_prisons']={actor.id:'prison'}
    elif blocked=='prison_target':g.intrigue_state['npc_prisons']={owner.id:'prison'}
    elif blocked=='event':g.pending_event={'id':'pending'}
    elif blocked=='trial':g.active_trial={'kind':'pending'}
    elif blocked=='imprisoned_player':g.player.imprisonment={'kind':'prison'}
    elif blocked=='low_affinity':actor.affinity=-10
    elif blocked=='self':target_id=actor.id
    elif blocked=='missing_target':target_id='missing'
    elif blocked=='stale':unit-=1
    elif blocked=='wrong_location':owner.location_id='another-place'
    elif blocked=='unknown_location':actor.location_id=None
    elif blocked=='soul_crisis':g.player.nascent_state['crisis']='possession'
    elif blocked=='other_instance':
        g.player.world=actor.world=owner.world='lost'
        g.spatial_state={'current':'first','instances':{
            'first':{'kind':'lost','npc_ids':[actor.id]},'second':{'kind':'lost','npc_ids':[owner.id]}}}
    # Use the working state directly so invalid fixture-only custody/events do not
    # invoke unrelated load normalization before the command's actual guards.
    before=copy.deepcopy(g.to_dict())
    from unittest.mock import patch
    assignment=patch('cultivation_life.system.npc_promises.research_assignment',
        side_effect=lambda game,key:dict(phase='studying') if key==actor.id else None) if blocked=='assignment' else nullcontext()
    with patch.object(e,'_load',return_value=g),assignment,pytest.raises(ValueError):
        e.contact_action(g.id,actor.id,'promise',target_id,unit)
    assert g.to_dict()==before


def test_projection_is_read_only_and_hides_remote_location(ready):
    e,g,actor,owner=ready
    before=copy.deepcopy(g.to_dict())
    assert projection(g,actor)['contact_location_id']==g.player.location_id
    assert g.to_dict()==before
    owner.world='spirit'
    assert projection(g,owner)['contact_location_id'] is None


def test_destroyed_body_with_escaping_nascent_soul_is_not_a_kill(ready):
    e,g,actor,owner=ready
    actor.realm_index=8;owner.realm_index=4
    e.store.save(g)
    result=e.contact_action(g.id,actor.id,'promise',owner.id,g.diplomacy_unit)
    saved=e.store.load(g.id)
    assert saved.notable_npcs[owner.id].alive
    assert saved.notable_npcs[owner.id].spirit_state.get('mode')=='wandering'
    assert '凤仪亭' not in {r['name'] for r in result['new_achievements']}
    assert saved.player.concubine_status


def test_promised_actor_can_be_killed_by_stronger_target(ready):
    e,g,actor,owner=ready
    actor.realm_index=1;owner.realm_index=3
    e.store.save(g)
    result=e.contact_action(g.id,actor.id,'promise',owner.id,g.diplomacy_unit)
    saved=e.store.load(g.id)
    assert not saved.notable_npcs[actor.id].alive and saved.notable_npcs[owner.id].alive
    assert '凤仪亭' not in {r['name'] for r in result['new_achievements']}


def test_high_tier_ward_is_resolved_by_shared_npc_combat(ready):
    from cultivation_life.content_registry import WORLD_SYSTEMS
    from cultivation_life.system.combat.npc_lifecycle import initialize_native
    from cultivation_life.system.npc_promises import resolve
    import random
    e,g,actor,owner=ready
    g.player.world=actor.world=owner.world='celestial'
    g.player.location_id=actor.location_id=owner.location_id=e.maps.default_location('celestial')
    owner.realm_index=9;owner.immortal_body_level=30
    initialize_native(owner,WORLD_SYSTEMS['transcendent_combat'],now=g.player.age)
    outcome=resolve(g,actor,owner,random.Random(1),e._npc_power)
    assert owner.alive and owner.id not in outcome.killed
    assert not g.player.milestones.get('fengyi_pavilion')
    assert any('voisinage' in r for r in outcome.rounds)


def test_cached_actor_is_registered_once_only_after_valid_submission(ready):
    e,g,actor,owner=ready
    g.player.dao_companion=None
    g.notable_npcs.pop(actor.id)
    g.encounter_npc_cache.append(dict(id=actor.id,npc=actor.to_dict(),last_seen_age=g.player.age))
    e.store.save(g)
    e.contact_action(g.id,actor.id,'promise',owner.id,g.diplomacy_unit)
    saved=e.store.load(g.id)
    assert saved.notable_npcs[actor.id].alive
    assert sum(n.id==actor.id for n in [*saved.world_npcs.values(),*saved.notable_npcs.values(),
        *saved.relationship_npcs.values(),*(n for s in saved.sects.values() for n in s.npcs)])==1


def test_stale_cached_copy_cannot_resurrect_held_original(ready):
    from unittest.mock import patch
    e,g,actor,owner=ready
    g.encounter_npc_cache.append(dict(id=owner.id,npc=owner.to_dict()))
    g.notable_npcs.pop(owner.id)
    owner.roster_state='held';g.inactive_npcs[owner.id]=owner
    before=copy.deepcopy(g.to_dict())
    with patch.object(e,'_load',return_value=g),pytest.raises(ValueError):
        e.contact_action(g.id,actor.id,'promise',owner.id,g.diplomacy_unit)
    assert g.to_dict()==before
