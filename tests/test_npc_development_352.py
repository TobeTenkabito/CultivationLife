import copy
import pytest
from test_npc_development import game
from cultivation_life.rules import add_item
from cultivation_life.models import GameState,SectNpc
from cultivation_life.system.npc_development import service,presentation,body,domains
from cultivation_life.system.npc_development.targets import resolve
from cultivation_life.system import divine_lights,wuyun,monster_body,ghost_body
from cultivation_life.system.doctrine.state import ensure


@pytest.mark.parametrize('path,world,module',[('dao','celestial',divine_lights),('demonic','asura',wuyun),('monster','nether',monster_body),('ghost','reincarnation',ghost_body)])
def test_body_refinement_persists_and_projects_without_resource_refill(game,path,world,module):
    n=game.world_npcs['student'];n.path=path;n.world=game.player.world=world;n.realm_index=9
    n.body_training=100;n.immortal_body_level=10
    n.transcendence=dict(conversion=1,capacity=1000,current=17)
    axis=body.options(n.to_dict())[0]['axis'];add_item(game.player,f'npc_training_{path}_body_art_3',10)
    before=copy.deepcopy(game.to_dict());q=service.quote(game,'npc',n.id,axis,'material',10)
    assert game.to_dict()==before and q['rounds']==8
    service.apply(game,'npc',n.id,axis,'material',10)
    assert n.transcendence['current']==17 and game.player.age==before['player']['age']
    if path=='dao':assert module.profile(n)[1]['kun']==10
    else:assert module.profile(n)[0].level==10
    saved=GameState.from_dict(game.to_dict());assert saved.world_npcs[n.id].body_attainments==n.body_attainments
    assert game.player.disciples[0].person is n
    n.immortal_body_level=15;assert body.options(n.to_dict())[0]['rank']==10
    after=copy.deepcopy(game.to_dict())
    with pytest.raises(ValueError):service.apply(game,'npc',n.id,axis,'material')
    assert game.to_dict()==after


@pytest.mark.parametrize('bad',['world','locked','teacher','body','foreign','no_stock','puppet'])
def test_body_failure_is_atomic(game,bad):
    n=game.world_npcs['student'];n.world=game.player.world='celestial';n.realm_index=9;n.immortal_body_level=10
    axis='body_art:lights:kun';method='material';kind='npc';identity=n.id
    add_item(game.player,'npc_training_dao_body_art_3',10)
    if bad=='world':n.world=game.player.world='asura'
    if bad=='locked':axis='body_art:lights:qian'
    if bad=='teacher':method='infuse'
    if bad=='body':n.spirit_state={'mode':'wandering','body_intact':False}
    if bad=='foreign':axis='body_art:ghost:wuxiang'
    if bad=='no_stock':game.player.inventory=[]
    if bad=='puppet':
        kind='puppet';identity='p';game.player.puppets=[dict(id='p',name='甲',type='mechanical',realm_index=9,layer=1,alive=True)]
    before=copy.deepcopy(game.to_dict())
    with pytest.raises(ValueError):service.apply(game,kind,identity,axis,method)
    assert game.to_dict()==before


def test_training_stays_with_actual_body_and_is_lost_on_destruction(game):
    from cultivation_life.system.npc_soul import escape_body
    n=game.world_npcs['student'];n.realm_index=9;n.immortal_body_level=10;n.body_attainments={'lights':{'kun':9}}
    p=game.player;p.ghost_host_body={**n.to_dict()};p.ghost_attachment={'active':True}
    # The original NPC projection remains the authority used by possessed-body adapters.
    assert divine_lights.profile(p.ghost_host_body)[1]['kun']==9
    assert escape_body(n,game.player.age)
    assert n.body_attainments=={} and divine_lights.profile(n)==({},{})
    with pytest.raises(ValueError):SectNpc.from_dict({**n.to_dict(),'body_attainments':{'lights':{'kun':True}}})


def test_domain_selection_retains_origin_and_switches_learned_only(game):
    n=game.world_npcs['student'];n.realm_index=9;n.world=game.player.world='celestial'
    n.transcendence=dict(conversion=1,capacity=1000,current=17);ensure(game)
    choices=domains.options(game,n.to_dict());assert len(choices)>=2
    add_item(game.player,'npc_training_dao_domain_3',30)
    service.apply(game,'npc',n.id,choices[0]['axis'],'material',10)
    origin=n.transcendence['doctrine']['origin']
    service.apply(game,'npc',n.id,choices[1]['axis'],'material',10)
    assert n.transcendence['doctrine']['origin']==origin
    assert n.transcendence['doctrine']['progress'][choices[1]['axis'][7:]]['level']==4
    domains.activate(game,resolve(game,'npc',n.id),choices[0]['axis'])
    assert n.transcendence['doctrine']['active']==origin and n.transcendence['current']==17


def test_technique_training_uses_original_equipped_levels(game):
    from cultivation_life.content_registry import TECHNIQUE_CATALOG
    from cultivation_life.system.npc_techniques import equipped
    n=game.world_npcs['student'];book=copy.deepcopy(TECHNIQUE_CATALOG['TECH_BASIC_QI']);book.level=3
    game.player.known_techniques=[book];service.teach(game,'npc',n.id,book.id)
    axis='technique:'+book.id
    service.apply(game,'npc',n.id,axis,'infuse',10)
    assert n.main_technique_level==3 and n.technique_levels[book.id]==3
    add_item(game.player,'npc_training_dao_technique_1',10)
    service.apply(game,'npc',n.id,axis,'material',10)
    assert n.main_technique_level==9 and equipped(game,n)[0][1].level==9
    assert presentation.public(game)['targets'][0]['learned_techniques'][0]['rank']==9
