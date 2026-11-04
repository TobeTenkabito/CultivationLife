import copy
from pathlib import Path
import pytest
from cultivation_life.models import Player,GameState,SectNpc
from cultivation_life.rules import add_item
from cultivation_life.npc_development_content import definitions,allowed,build,shelf
from cultivation_life.system.npc_development import service,presentation
from cultivation_life.system.npc_development.targets import candidates


@pytest.fixture
def game():
    p=Player('师父','supreme_metal',realm_index=4,layer=8,world='human',location_id='place',
             body_training=60,divine_sense_rank=45,opportunity=100000)
    n=SectNpc('student','弟子','门人',2,1,30,300,world='human',location_id='place',
              spirit_root='supreme_metal',body_training=10,divine_sense_rank=17,gender='female')
    g=GameState('training',17,p,'created','revision',world_npcs={n.id:n})
    p.disciples=[g.link_relationship({'id':n.id})]
    return g


@pytest.mark.parametrize('axis',['cultivation','body','sense'])
@pytest.mark.parametrize('path',['dao','demonic','monster','ghost'])
def test_material_consumption_and_original_authority(game,path,axis):
    n=game.world_npcs['student'];n.path=path
    material=f'npc_training_{path}_{axis}_1';add_item(game.player,material,10)
    before=copy.deepcopy(game.to_dict());plan=service.quote(game,'npc',n.id,axis,'material',5)
    assert plan['can_train'] and plan['opportunity']==plan['mp']==0
    assert game.to_dict()==before
    service.apply(game,'npc',n.id,axis,'material',5)
    assert game.player.disciples[0].person is n
    assert sum(i.quantity for i in game.player.inventory if i.id==material)==10-plan['material_count']
    assert game.player.opportunity==before['player']['opportunity']
    assert game.rng_state==before['rng_state'] and game.player.age==before['player']['age']


@pytest.mark.parametrize('change',[
    lambda g:setattr(g.world_npcs['student'],'location_id','other'),
    lambda g:setattr(g.world_npcs['student'],'location_id',None),
    lambda g:setattr(g.world_npcs['student'],'world','demon'),
    lambda g:setattr(g.world_npcs['student'],'age',15),
    lambda g:setattr(g.world_npcs['student'],'alive',False),
    lambda g:setattr(g.player,'sealed_cultivation',{'active':True}),
    lambda g:setattr(g,'pending_event',{'id':'pending'}),
])
def test_invalid_targets_never_charge(game,change):
    change(game);before=copy.deepcopy(game.to_dict())
    with pytest.raises(ValueError):service.apply(game,'npc','student','body')
    assert game.to_dict()==before


def test_stage_boundary_and_partial_charge(game):
    n=game.world_npcs['student'];n.body_training=57
    add_item(game.player,'npc_training_dao_body_1',10)
    q=service.quote(game,'npc',n.id,'body','material',10)
    assert q['gain']==3 and q['rounds']==q['material_count']==1
    service.apply(game,'npc',n.id,'body','material',10)
    with pytest.raises(ValueError):service.apply(game,'npc',n.id,'body','material',1)
    n.realm_index=4;n.layer=9
    with pytest.raises(ValueError,match='关口'):service.quote(game,'npc',n.id,'cultivation')


def test_material_gate_uses_direction_and_world(game):
    n=game.world_npcs['student'];n.realm_index=8;n.body_training=10
    n.world=game.player.world='spirit'
    add_item(game.player,'npc_training_dao_body_1',1)
    q=service.quote(game,'npc',n.id,'body','material')
    assert q['material_id']=='npc_training_dao_body_1'
    assert not allowed('npc_training_dao_body_2','human')
    assert not allowed('npc_training_dao_body_3','asura')
    assert not allowed('npc_training_dao_body_1','lost')
    assert allowed('npc_training_demonic_body_3','asura')
    assert len(definitions())==81
    assert any(r['tier']==9 and '_cultivation_' in r['content_id'] for r in build()[1])


def test_projection_read_only_and_redacted(game):
    before=copy.deepcopy(game.to_dict());shown=presentation.public(game)
    assert game.to_dict()==before
    assert shown['targets'][0]['portrait']['gender']=='female'
    game.world_npcs['student'].world='demon'
    row=presentation.public(game)['targets'][0]
    assert row['portrait'] is None and not row['quotes'] and 'facts' not in row


def test_duplicate_relationships_resolve_one_person(game):
    game.player.dao_companion=game.link_relationship({'id':'student'})
    rows=candidates(game)
    assert len(rows)==1 and rows[0].relations==('弟子','道侣')


def test_prisoner_writes_person_and_release_preserves_growth(game):
    game.player.prisoners.append(game.detain_person({'id':'student','combat_power':100}))
    assert len(candidates(game))==1
    n=game.inactive_npcs['student']
    service.apply(game,'prisoner',n.id,'body')
    assert n.body_training==20
    from cultivation_life.npc_custody import release_person
    release_person(game,n.id)
    assert game.player.disciples[0].person.body_training==20


def test_child_without_roster_uses_original_growth_record(game):
    child=game.world_npcs.pop('student').to_dict();game.player.disciples=[];game.player.offspring=[child]
    service.apply(game,'npc','student','body')
    assert child['body_training']==20 and not game.world_npcs and not game.relationship_npcs


def test_invalid_and_insufficient_requests_are_atomic(game):
    for count in (0,-1,True,'5',100):
        with pytest.raises(ValueError):service.apply(game,'npc','student','body','infuse',count)
    before=copy.deepcopy(game.to_dict())
    with pytest.raises(ValueError,match='专材不足'):service.apply(game,'npc','student','body','material')
    assert game.to_dict()==before


def test_bodyless_cannot_borrow_original_body(game):
    n=game.world_npcs['student'];n.spirit_state={'mode':'wandering'}
    with pytest.raises(ValueError,match='肉身'):service.apply(game,'npc',n.id,'body')
    assert presentation.public(game)['targets'][0]['portrait'] is None


def test_cost_tracks_trained_axis_not_main_realm(game):
    n=game.world_npcs['student'];game.player.world=n.world='spirit'
    first=service.quote(game,'npc',n.id,'body')
    n.realm_index=8
    second=service.quote(game,'npc',n.id,'body')
    assert first['opportunity']==second['opportunity']<first['reference_units']*.6


@pytest.mark.parametrize('path,world',[('dao','celestial'),('demonic','asura'),('monster','nether'),('ghost','reincarnation')])
def test_upper_materials_only_improve_existing_coordinates(game,path,world):
    n=game.world_npcs['student'];game.player.world=n.world=world;n.path=path
    n.realm_index=9;n.body_training=100;n.immortal_body_level=8;n.divine_sense_rank=102
    for axis in ('body','sense'):
        add_item(game.player,f'npc_training_{path}_{axis}_3',2)
        service.apply(game,'npc',n.id,axis,'material')
    assert n.immortal_body_level==10 and n.divine_sense_rank==110
    assert not n.transcendence and n.realm_index==9
    add_item(game.player,f'npc_training_{path}_cultivation_3',1)
    service.apply(game,'npc',n.id,'cultivation','material')
    assert n.layer==2 and not n.transcendence


def test_living_asset_release_keeps_same_person_and_cost_buff(game):
    from cultivation_life.npc_custody import detain_person,settle_puppet_person
    source=game.world_npcs['student']
    detain_person(game,{'id':source.id},SectNpc,kind='living_puppet')
    asset=dict(id='asset',source_npc_id=source.id,name=source.name,type='living',realm_index=2,layer=1,
               body_training=10,divine_sense_rank=17,combat_power=100,breakthrough_bonus=.2,alive=True)
    game.player.puppets=[asset];add_item(game.player,'npc_training_puppet_body_1',1)
    assert len(candidates(game))==1
    service.apply(game,'puppet','asset','body','material')
    assert asset['breakthrough_bonus']==.2 and source.body_training==10
    from cultivation_life.content_registry import TECHNIQUE_CATALOG
    source.main_technique_level=9
    game.player.known_techniques=[copy.deepcopy(TECHNIQUE_CATALOG['TECH_BASIC_QI'])]
    service.teach(game,'puppet','asset','TECH_BASIC_QI',slot='main')
    settle_puppet_person(game,asset,outcome='released')
    assert source.body_training==20 and source.id=='student'
    assert source.main_technique_id=='TECH_BASIC_QI' and source.main_technique_level==1


def test_corpse_never_restores_source_life(game):
    source=game.world_npcs['student'];source.alive=False
    game.player.puppets=[dict(id='corpse',source_npc_id=source.id,name='炼尸',type='corpse',realm_index=2,layer=1,
                            body_training=10,divine_sense_rank=17,combat_power=100,corpse_integrity=100)]
    service.apply(game,'puppet','corpse','body')
    assert not source.alive and source.body_training==10
    add_item(game.player,'npc_training_dao_body_1',1)
    with pytest.raises(ValueError,match='专材不足'):service.apply(game,'puppet','corpse','body','material')
    add_item(game.player,'npc_training_puppet_body_1',1)
    service.apply(game,'puppet','corpse','body','material')
    assert not source.alive and source.body_training==10


def test_hidden_true_state_denied_even_by_direct_submission(game):
    game.world_npcs['student'].concealed_realm_index=1
    game.player.divine_sense_rank=0
    with pytest.raises(ValueError,match='探明'):service.apply(game,'npc','student','body')
    assert not presentation.public(game)['targets'][0]['quotes']
    game.player.divine_sense_rank=45
    assert presentation.public(game)['targets'][0]['quotes']


def test_task_and_wrong_identity_are_denied(game):
    game.map_journey={'progress':0}
    with pytest.raises(ValueError,match='行旅'):service.apply(game,'npc','student','body')
    game.map_journey=None
    for kind in ([],{},None,'other'):
        with pytest.raises(ValueError):service.apply(game,kind,'student','body')


def test_treasure_material_pool_obeys_destination_world():
    from cultivation_life.system.economy.treasure import reward_pool_for_scene
    from cultivation_life.system.map_system import MapCatalog
    from cultivation_life.content_registry import CONTENT_DOCUMENTS
    from types import SimpleNamespace
    maps=MapCatalog(CONTENT_DOCUMENTS['maps.json'])
    for world in ('human','spirit','celestial','asura','nether','reincarnation'):
        pool=reward_pool_for_scene(SimpleNamespace(maps=maps),world,maps.default_location(world),12,'pill')
        materials=[r for r in pool if r['content_id'] in definitions()]
        assert materials
        assert all(allowed(r['content_id'],world) for r in materials)


def test_sense_uses_existing_coordinates_and_stops_at_tier_boundary(game):
    from cultivation_life.npc_development_content import SENSE_LIMITS
    from cultivation_life.cultivation_coordinates import STARTS,END_RANK
    assert SENSE_LIMITS==(STARTS[6]-1,STARTS[9]-1,END_RANK-1)
    n=game.world_npcs['student'];n.divine_sense_rank=63
    add_item(game.player,'npc_training_dao_sense_1',10)
    q=service.quote(game,'npc',n.id,'sense','material',10)
    assert q['rounds']==q['gain']==1 and q['result']['divine_sense_rank']==64


def test_human_spirit_cannot_train_past_actual_departure_gate(game):
    n=game.world_npcs['student'];n.realm_index=5;n.layer=2
    with pytest.raises(ValueError):service.quote(game,'npc',n.id,'cultivation')
    game.player.realm_index=5;game.player.layer=8
    q=service.quote(game,'npc',n.id,'cultivation','infuse',10)
    assert q['rounds']==q['gain']==1 and q['result']['layer']==3
    service.apply(game,'npc',n.id,'cultivation')
    with pytest.raises(ValueError,match='飞升'):service.apply(game,'npc',n.id,'cultivation')
    assert n.world==game.player.world=='human'


@pytest.mark.parametrize('method',['material','infuse'])
def test_batch_cannot_create_high_body_qualification(game,method):
    n=game.world_npcs['student'];game.player.world=n.world='spirit';n.body_training=95
    game.player.body_training=100;game.player.immortal_body['level']=30;game.player.asura_cultivation['body_level']=20
    add_item(game.player,'npc_training_dao_body_2',10)
    q=service.quote(game,'npc',n.id,'body',method,10)
    assert q['result']['body_training']==100 and q['result']['immortal_body_level']==0 and q['rounds']==1


def test_material_batch_cannot_cross_recipe_or_upper_route(game):
    n=game.world_npcs['student'];game.player.world=n.world='celestial'
    n.realm_index=4;n.layer=8
    add_item(game.player,'npc_training_dao_cultivation_1',10)
    add_item(game.player,'npc_training_dao_cultivation_2',10)
    first=service.quote(game,'npc',n.id,'cultivation','material',10)
    assert (first['result']['realm_index'],first['result']['layer'])==(4,9)
    service.apply(game,'npc',n.id,'cultivation','material',10)
    next_plan=service.quote(game,'npc',n.id,'cultivation','material')
    assert next_plan['material_id']=='npc_training_dao_cultivation_2' and next_plan['result']['realm_index']==5
    n.realm_index=8;n.layer=8
    final=service.quote(game,'npc',n.id,'cultivation','material',10)
    assert (final['result']['realm_index'],final['result']['layer'])==(8,9)
