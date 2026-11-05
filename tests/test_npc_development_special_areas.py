"""NPC training through real dungeon sessions and public rift commands."""
import copy
import random
from pathlib import Path

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.content_registry import GUIXU_TIDE_CONTENT, TECHNIQUE_CATALOG
from cultivation_life.runtime import encode_rng
from cultivation_life.rules import add_item
from cultivation_life.relationship_records import find_person
from cultivation_life.system import spatial, trial_sites
from test_npc_transition_training import person
from test_trial_sites import enter, complete_events, act

ROOT=Path(__file__).resolve().parents[1]


def make_game(e):
    g=e.store.load(e.create_game('副本培养审计','supreme_metal','dao',771,
        custom_start=dict(world='human',realm_index=4,layer=1))['id'])
    g.pending_event=None;g.player.body_training=60;g.player.opportunity=100000
    n=person(g,'outside-student');g.player.disciples=[g.link_relationship({'id':n.id})]
    n=person(g,'held');g.player.prisoners=[g.detain_person({'id':n.id})]
    g.player.known_techniques=[copy.deepcopy(TECHNIQUE_CATALOG['TECH_BASIC_QI'])]
    g.player.puppets=[dict(id='machine',name='机关',type='mechanical',realm_index=2,
        layer=1,body_training=10,durability=100,operating_energy=47,
        energy_source_id='npc_training_puppet_energy_1',
        energy_spares=[dict(id='saved-energy',source_id='npc_training_puppet_energy_rank_2',durability=23)])]
    for material in ('npc_training_dao_body_1','npc_training_puppet_energy_1'):
        add_item(g.player,material,5)
    e.store.save(g)
    return g


def enter_guixu(e,g):
    dungeon=next(d for d in GUIXU_TIDE_CONTENT['dungeons'] if d['world']=='human')
    e._open_guixu_cycle(g,dungeon,g.guixu_state['cycles'][dungeon['id']],random.Random(771))
    g.pending_event=None
    g.player.realm_index=3;g.player.location_id=dungeon['entry_location_id']
    find_person(g,'outside-student').location_id=g.player.location_id
    e.store.save(g)
    e.guixu_action(g.id,'enter',{'dungeon_id':dungeon['id']})
    g=e.store.load(g.id)
    if g.guixu_state['player_session'].get('pending_team_offer'):
        e.guixu_action(g.id,'team_decline',{})
    return e.store.load(g.id)


def enter_rift(e,g,kind):
    rift=spatial.new_rift(g,random.Random(7),e.maps,controlled=True)
    rift['destination']='lost' if kind=='lost' else 'human'
    wanted='passage' if kind=='lost' else 'secluded'
    weights=spatial.outcome_weights(rift)
    # Select a deterministic fixture RNG; use the real entry and settlement.
    seed=next(seed for seed in range(1000) if random.Random(seed).choices(
        list(weights),weights=list(weights.values()))[0]==wanted)
    g.rng_state=encode_rng(random.Random(seed));e.store.save(g)
    e.spatial_action(g.id,'enter',{'target_id':rift['id']})
    g=e.store.load(g.id)
    assert spatial.current(g)['kind']==kind
    return g


def stable(e,gid):
    e.get_game(gid)
    return e.store._path(gid).read_bytes()


def new_action(e,gid,payload):
    return e.npc_development(gid,dict(revision=e.store.load(gid).updated_at,**payload))


def blocked_writes(e,gid,*,teaching=True):
    calls=[]
    for kind,identity in [('npc','outside-student'),('prisoner','held'),('puppet','machine')]:
        for method in ('infuse','material'):
            calls.append(lambda kind=kind,identity=identity,method=method:new_action(e,gid,dict(
                action='train',kind=kind,target_id=identity,axis='body',method=method,batches=1)))
        calls.append(lambda kind=kind,identity=identity:e.train_owned(gid,identity,kind,'body'))
    calls.extend([
        lambda:new_action(e,gid,dict(action='charge',kind='puppet',target_id='machine',
            source='bag:npc_training_puppet_energy_1')),
        lambda:new_action(e,gid,dict(action='charge',kind='puppet',target_id='machine',source='spare:saved-energy')),
        lambda:new_action(e,gid,dict(action='activate_domain',kind='npc',target_id='outside-student',axis='domain:metal')),
        lambda:e.puppet_action(gid,'machine','infuse'),
    ])
    if teaching:
        calls.extend([
            lambda:new_action(e,gid,dict(action='teach',kind='npc',target_id='outside-student',content_id='TECH_BASIC_QI')),
            lambda:new_action(e,gid,dict(action='teach',kind='prisoner',target_id='held',content_id='TECH_BASIC_QI')),
            lambda:e.gift_disciple(gid,'outside-student','technique','TECH_BASIC_QI'),
        ])
    before=stable(e,gid)
    for call in calls:
        with pytest.raises(ValueError):call()
        assert e.store._path(gid).read_bytes()==before


@pytest.mark.parametrize('trapped',[False,True])
def test_guixu_blocks_all_growth_teaching_and_energy_without_spending(tmp_path,trapped):
    e=GameEngine(ROOT,tmp_path);g=enter_guixu(e,make_game(e))
    if trapped:
        g.guixu_state['player_session']['remaining_days']=1;e.store.save(g)
        e.guixu_action(g.id,'rest',{})
        assert e.store.load(g.id).guixu_state['player_session']['trapped']
    before=stable(e,g.id);shown=e.npc_development(g.id)
    assert all(row['reason'] and not row['quotes'] for row in shown['targets'])
    assert e.store._path(g.id).read_bytes()==before
    blocked_writes(e,g.id)
    if not trapped:
        e.guixu_action(g.id,'return',{})
        assert not e.store.load(g.id).guixu_state.get('player_session')
        shown=e.npc_development(g.id)
        assert not next(r for r in shown['targets'] if r['id']=='outside-student')['reason']
        new_action(e,g.id,dict(action='train',kind='npc',target_id='outside-student',
            axis='body',method='infuse',batches=1))
        assert find_person(e.store.load(g.id),'outside-student').body_training==20


@pytest.mark.parametrize('kind',['lost','secluded'])
def test_real_rift_entry_isolates_outside_person_and_keeps_held_training_rules(tmp_path,kind):
    e=GameEngine(ROOT,tmp_path);original=make_game(e)
    address=find_person(original,'outside-student').location_id
    assets=copy.deepcopy(original.player.puppets)
    g=enter_rift(e,original,kind)
    assert g.player.puppets==assets
    shown=e.npc_development(g.id)
    assert next(r for r in shown['targets'] if r['id']=='outside-student')['reason']
    assert find_person(g,'outside-student').location_id==address
    blocked_writes(e,g.id,teaching=False)
    # Only physically carried prisoners may be taught; free outsiders remain inaccessible.
    before=stable(e,g.id)
    with pytest.raises(ValueError):e.gift_disciple(g.id,'outside-student','technique','TECH_BASIC_QI')
    assert e.store._path(g.id).read_bytes()==before
    new_action(e,g.id,dict(action='teach',kind='prisoner',target_id='held',content_id='TECH_BASIC_QI'))
    saved=e.store.load(g.id)
    assert find_person(saved,'held',include_inactive=True).technique_levels['TECH_BASIC_QI']==1
    assert saved.player.puppets==assets


def test_trial_session_blocks_even_between_events_and_restores_after_pause(tmp_path):
    e=GameEngine(ROOT,tmp_path);g=make_game(e)
    g.player.location_id=trial_sites.bound_site(g,e.maps,'human')['location_id']
    find_person(g,'outside-student').location_id=g.player.location_id
    e.store.save(g);enter(e,g)
    complete_events(e,g.id)
    assert e.store.load(g.id).pending_event is None
    before=stable(e,g.id)
    with pytest.raises(ValueError,match='试境'):e.npc_development(g.id)
    assert e.store._path(g.id).read_bytes()==before
    blocked_writes(e,g.id)
    act(e,g.id,'pause')
    assert not e.npc_development(g.id)['targets'][0]['reason']
    e.gift_disciple(g.id,'outside-student','technique','TECH_BASIC_QI')
    assert find_person(e.store.load(g.id),'outside-student').technique_levels['TECH_BASIC_QI']==1
