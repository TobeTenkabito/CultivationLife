"""Full addresses and consistent training commands across world boundaries."""
import copy
import random
from pathlib import Path

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.models import SectNpc, GameState
from cultivation_life.content_registry import TECHNIQUE_CATALOG
from cultivation_life.npc_custody import release_person
from cultivation_life.relationship_records import find_person
from cultivation_life.rules import add_item
from cultivation_life.spatial_people import instance_of
from cultivation_life.system import spatial
from cultivation_life.system.npc_development import service, presentation
from cultivation_life.engine.actions.exploration import enter_scene
from test_other_systems_audit_fixes import snapshot

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def setup(tmp_path):
    e=GameEngine(ROOT,tmp_path)
    g=e.store.load(e.create_game('跨界培养','supreme_metal','dao',771,
        custom_start=dict(world='human',realm_index=5,layer=3))['id'])
    g.pending_event=None;g.player.body_training=60;g.player.opportunity=100000
    return e,g


def person(g,identity='student',realm=2):
    n=SectNpc(identity,identity,'',realm,1,80,10000,spirit_root='supreme_metal',
        gender='female',body_training=10,world=g.player.world,location_id=g.player.location_id)
    g.world_npcs[n.id]=n
    return n


def spatial_students(e,g,kind='lost'):
    scene=spatial.create_instance(g,random.Random(7),kind)
    if kind=='lost':scene['power_ceiling']=8
    enter_scene(e._exploration_dependencies(),g,scene,random.Random(7))
    # Movement inside a space changes scene.location_id, not player.location_id.
    spatial.local_action(g,'move',scene['locations'][1]['id'])
    for identity in ('new-student','old-student'):
        n=person(g,identity);n.location_id=scene['location_id']
        scene.setdefault('npc_ids',[]).append(n.id)
        g.player.disciples.append(g.link_relationship({'id':n.id}))
    g.player.known_techniques=[copy.deepcopy(TECHNIQUE_CATALOG['TECH_BASIC_QI'])]
    add_item(g.player,'npc_training_dao_body_1',5)
    e.store.save(g)
    return scene


def test_ascension_updates_only_surviving_entourage_addresses(setup):
    e,g=setup
    companion=person(g,'companion',5);companion.layer=3
    friend=person(g,'friend',5);friend.layer=3
    home=person(g,'home')
    g.player.dao_companion=g.link_relationship({'id':companion.id})
    g.player.dao_friends=[g.link_relationship({'id':friend.id})]
    g.player.disciples=[g.link_relationship({'id':home.id})]
    g.player.joint_spirit_crossing={'id':companion.id}
    g.player.joint_friend_crossing=[{'id':friend.id}];g.player.party=[{'id':friend.id}]
    g.player.offspring=[copy.deepcopy(friend.to_dict())]
    old_home=copy.deepcopy(home.to_dict())
    manifest=e._resolve_selected_ascension_entourage(g,'spirit',random.Random(1))
    assert manifest.companion_kept and friend.id in manifest.survivor_ids
    before=copy.deepcopy(g.to_dict())
    plan=e._plan_world_transition(g,'spirit')
    assert g.to_dict()==before
    e._apply_world_transition(g,plan,entourage=manifest)
    assert companion.world==friend.world==g.player.world=='spirit'
    assert companion.location_id==friend.location_id==plan.arrival_location
    assert g.player.dao_companion.person is companion
    assert home.to_dict()==old_home and not g.player.disciples
    assert g.player.offspring[0]['location_id']==plan.arrival_location
    service.apply(g,'npc',companion.id,'body')
    loaded=GameState.from_dict(g.to_dict())
    assert loaded.player.dao_companion.person.location_id==plan.arrival_location
    assert loaded.player.dao_companion.person.body_training==20


def test_held_crossing_and_personal_release_follow_actual_location(setup):
    e,g=setup;n=person(g)
    g.player.dao_companion=g.link_relationship({'id':n.id})
    g.player.prisoners=[g.detain_person({'id':n.id})]
    # Rifts are temporary movement and carry the original controlled person.
    scene=spatial.create_instance(g,random.Random(7),'lost');scene['power_ceiling']=8
    enter_scene(e._exploration_dependencies(),g,scene,random.Random(7))
    assert n.location_id==scene['location_id'] and n.world=='lost'
    assert instance_of(g,n.id) is None  # Held people are not free scene residents.
    spatial.local_action(g,'move',scene['locations'][1]['id'])
    e.store.save(g)
    e.captive_action(g.id,n.id,'release')
    loaded=e.store.load(g.id);released=find_person(loaded,n.id)
    assert released.location_id==scene['location_id']
    assert instance_of(loaded,n.id)==scene['id']
    assert loaded.player.dao_companion.person is released
    assert not loaded.player.prisoners
    assert not presentation.public(loaded)['targets'][0]['reason']


def test_remote_release_keeps_remote_address(setup):
    _,g=setup;n=person(g);n.location_id='remote-camp'
    g.player.prisoners=[g.detain_person({'id':n.id})]
    release_person(g,n.id)
    assert n.location_id=='remote-camp'


def test_public_passage_release_and_training_survive_reload(setup):
    e,_=setup
    g=e.store.load(e.create_game('受禁随行','supreme_metal','monster',771,
        monster_species_id='fox',custom_start=dict(world='monster_realm',realm_index=5,layer=3))['id'])
    g.pending_event=None;g.player.body_training=60;g.player.opportunity=100000
    n=person(g);old_location=n.location_id
    g.player.disciples=[g.link_relationship({'id':n.id})]
    g.player.prisoners=[g.detain_person({'id':n.id})]
    e.store.save(g)
    e.cross_world(g.id,'phantom_underworld')
    crossed=e.store.load(g.id);held=find_person(crossed,n.id,include_inactive=True)
    assert held.world=='phantom_underworld'
    assert held.location_id==crossed.player.location_id!=old_location
    e.captive_action(g.id,n.id,'release')
    shown=e.npc_development(g.id)
    assert not next(r for r in shown['targets'] if r['id']==n.id)['reason']
    e.npc_development(g.id,dict(action='train',kind='npc',target_id=n.id,
        axis='body',method='infuse',batches=1,revision=shown['revision']))
    saved=e.store.load(g.id);released=find_person(saved,n.id)
    assert saved.player.disciples[0].person is released
    assert released.body_training==20 and released.location_id==saved.player.location_id
    assert not saved.player.prisoners and released.custody is None


def test_invalid_personal_release_is_atomic(setup):
    _,g=setup;n=person(g);g.player.prisoners=[g.detain_person({'id':n.id})]
    n.world='spirit';before=copy.deepcopy(g.to_dict())
    with pytest.raises(ValueError,match='当前界面'):release_person(g,n.id,at_player=True)
    assert g.to_dict()==before


@pytest.mark.parametrize('kind',['lost','secluded'])
def test_new_and_old_spatial_teaching_share_original_facts(setup,kind):
    e,g=setup;scene=spatial_students(e,g,kind)
    shown=e.npc_development(g.id)
    assert all(not r['reason'] for r in shown['targets'])
    assert all(not q['can_train'] for r in shown['targets'] for q in r['quotes'])
    e.npc_development(g.id,dict(action='teach',kind='npc',target_id='new-student',
        content_id='TECH_BASIC_QI',revision=shown['revision']))
    e.gift_disciple(g.id,'old-student','technique','TECH_BASIC_QI')
    saved=e.store.load(g.id)
    for identity in ('new-student','old-student'):
        n=find_person(saved,identity)
        assert n.technique_levels['TECH_BASIC_QI']==1
        assert n.location_id==scene['location_id'] and instance_of(saved,identity)==scene['id']


@pytest.mark.parametrize('change',['other_location','other_instance','sealed','dead','assignment'])
@pytest.mark.parametrize('entry',['new','old'])
def test_spatial_restrictions_match_for_both_teaching_entries(setup,change,entry):
    e,g=setup;scene=spatial_students(e,g)
    n=find_person(g,'new-student')
    if change=='other_location':n.location_id=scene['locations'][0]['id']
    elif change=='other_instance':
        other=spatial.create_instance(g,random.Random(8),'lost')
        scene['npc_ids'].remove(n.id);other.setdefault('npc_ids',[]).append(n.id)
    elif change=='sealed':g.player.cultivation_suppression={'realm_index':8,'layer':1,'lifespan':10000}
    elif change=='dead':n.alive=False
    else:g.wars=[dict(id='war',strategic_war_id='deployment',status='active',
        journeys={'army':[dict(person_id=n.id,phase='outbound',observed=False)]})]
    e.store.save(g);before=snapshot(e,g.id)
    revision=e._load(g.id).updated_at
    with pytest.raises(ValueError):
        if entry=='new':e.npc_development(g.id,dict(action='teach',kind='npc',target_id=n.id,
            content_id='TECH_BASIC_QI',revision=revision))
        else:e.gift_disciple(g.id,n.id,'technique','TECH_BASIC_QI')
    assert e.store._path(g.id).read_bytes()==before


@pytest.mark.parametrize('method',['infuse','material'])
def test_spatial_training_stays_disabled_without_consuming_materials(setup,method):
    e,g=setup;spatial_students(e,g)
    before=snapshot(e,g.id);revision=e._load(g.id).updated_at
    with pytest.raises(ValueError,match='空间'):
        e.npc_development(g.id,dict(action='train',kind='npc',target_id='new-student',
            axis='body',method=method,batches=1,revision=revision))
    assert e.store._path(g.id).read_bytes()==before


def test_temporary_crossing_stamps_carried_person_and_preserves_energy(setup):
    e,g=setup;n=person(g)
    g.player.prisoners=[g.detain_person({'id':n.id})]
    g.player.puppets=[dict(id='mechanical',type='mechanical',realm_index=2,layer=1,
        durability=100,operating_energy=47,energy_source_id='npc_training_puppet_energy_1',
        energy_spares=[dict(id='spare',source_id='npc_training_puppet_energy_rank_2',durability=23)])]
    assets=copy.deepcopy(g.player.puppets)
    scene=spatial.create_instance(g,random.Random(7),'secluded')
    enter_scene(e._exploration_dependencies(),g,scene,random.Random(7))
    assert n.location_id==scene['location_id'] and g.player.puppets==assets
    plan=e._plan_world_transition(g,'human','rift',route_id='rift:rift:human')
    e._apply_world_transition(g,plan)
    assert n.world=='human' and n.location_id==g.player.location_id
    assert g.player.puppets==assets
