"""Soul forms, shared thirteen-stage domains and real upper-trial entry/submit."""
import copy
import json
import random
from pathlib import Path
from unittest.mock import patch

import pytest
from cultivation_life.engine import GameEngine
from cultivation_life.models import Player
from cultivation_life.content_registry import CONTENT_DOCUMENTS, WORLD_SYSTEMS
from cultivation_life.system import ghost_soul_form as soul
from cultivation_life.system.upper_voisinage_rules import definitions, player_source, project
from cultivation_life.system.upper_voisinage import quote
from cultivation_life.system.combat.trials import load_battle, dump_battle, run_batch
from cultivation_life.rules import opportunity_required, max_hp, max_mp, add_item
from cultivation_life.save_schema import migrate_document, SAVE_SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def ready(tmp_path):
    e = GameEngine(ROOT, tmp_path)
    shown = e.create_game('照魂', 'mutated_yin', 'ghost', 260, preset_id='reincarnation_upper')
    return e, e._load(shown['id'])


def fund(g):
    p=g.player
    p.opportunity=opportunity_required(p)
    add_item(p,'spirit_stone',100000000)
    key=WORLD_SYSTEMS['upper_voisinages']['worlds'][p.world]['material_id']
    p.crafting_materials += [dict(id=f'cost-{i}',material_id=key,quality=1) for i in range(10)]


@pytest.mark.parametrize('version',[1,7,8,9])
def test_old_saves_explicitly_rejected_without_mutation(version):
    old={'version':version,'id':'old','player':{'world_voisinages':{'reincarnation':{'levels':{'old':9}}}},'rng_state':'unchanged'}
    before=copy.deepcopy(old)
    with pytest.raises(ValueError,match='不兼容'):
        migrate_document(old)
    assert old==before
    assert SAVE_SCHEMA_VERSION==10


def test_old_save_file_survives_load_and_is_visible_as_incompatible(ready):
    e,g=ready
    path=e.store._path(g.id)
    raw=json.loads(path.read_text(encoding='utf-8'));raw['version']=9
    path.write_text(json.dumps(raw,ensure_ascii=False),encoding='utf-8')
    before=path.read_bytes()
    with pytest.raises(ValueError,match='不兼容'):e._load(g.id)
    assert path.read_bytes()==before
    row=next(r for r in e.store.list_games() if r['id']==g.id)
    assert row['compatible'] is False and '不兼容' in row['incompatibility']


@pytest.mark.parametrize('key',list(json.loads((ROOT/'dlc/ghost-reincarnation/content/ghost_soul_forms.json').read_text(encoding='utf-8'))['forms']))
def test_all_36_forms_persist_and_project_legal_distinct_rules(ready,key):
    e,g=ready
    cause,route=key.split('.')
    before=g.rng_state
    soul.confirm(g,cause,route)
    p=g.player;b=soul.stored(p);state=p.world_voisinages['reincarnation'];state.update(levels={b['blueprint_id']:4},active=b['blueprint_id'])
    row=soul.catalog()['forms'][key]
    soul.configure(p,'soul_form_secondary',soul.effect_key(row['secondary_choices'][-1]))
    state['levels'][b['blueprint_id']]=8
    soul.configure(p,'soul_form_feature',row['feature_choices'][0])
    state['levels'][b['blueprint_id']]=13;b['finalized']=True;p.realm_index=12
    actual=player_source(p).voisinages[0]
    assert 2<=len(actual.effects)<=3 and len(actual.features)==1
    copied=player_source(p,cap=8).voisinages[0]
    assert copied.effects==actual.effects and copied.features==actual.features
    assert copied.stability < actual.stability
    loaded=Player.from_dict(p.to_dict())
    assert player_source(loaded)==player_source(p) and g.rng_state==before
    frozen=copy.deepcopy(p.world_voisinages)
    with patch.dict(CONTENT_DOCUMENTS,{'ghost_soul_forms.json':{}}):
        assert len(definitions(p))==2 and not player_source(p).voisinages
    assert p.world_voisinages==frozen


def test_real_contemplation_choice_training_and_locked_stages(ready):
    e,g=ready;fund(g);e.store.save(g)
    old_age=g.player.age
    with patch.object(e,'_advance_world_year',return_value=True):
        shown=e.upper_voisinage_action(g.id,'soul_form_contemplate','battle_scars')
    assert shown['pending_event']['id']=='EVT_SOUL_CONTEMPLATION'
    assert e._load(g.id).player.age==old_age+WORLD_SYSTEMS['time_units']['9']
    e.choose(g.id,'sever',event_id='EVT_SOUL_CONTEMPLATION')
    g=e._load(g.id);p=g.player;b=soul.stored(p);key=b['blueprint_id']
    assert not g.active_trial and key not in p.world_voisinages['reincarnation'].get('levels',{})
    energy=copy.deepcopy(p.immortal_aperture)
    for rank in range(1,5):e.upper_voisinage_action(g.id,'train',key)
    g=e._load(g.id)
    assert g.player.immortal_aperture==energy
    with pytest.raises(ValueError,match='辅权能'):e.upper_voisinage_action(g.id,'train',key)
    with pytest.raises(ValueError):e.upper_voisinage_action(g.id,'soul_form_secondary','restore_body')
    e.upper_voisinage_action(g.id,'soul_form_secondary','suppress')
    with pytest.raises(ValueError,match='第 10 阶'):e.upper_voisinage_action(g.id,'train',key)
    for realm,stop in [(10,8),(11,13)]:
        g=e._load(g.id);g.player.realm_index=realm;fund(g);e.store.save(g)
        if realm==11:e.upper_voisinage_action(g.id,'soul_form_feature','execution')
        while e._load(g.id).player.world_voisinages['reincarnation']['levels'][key]<stop:
            e.upper_voisinage_action(g.id,'train',key)
    e.upper_voisinage_action(g.id,'select',key)
    g=e._load(g.id)
    assert soul.stored(g.player)['finalized'] and player_source(g.player).voisinages
    before=e.store._path(g.id).read_bytes()
    with pytest.raises(ValueError):e.upper_voisinage_action(g.id,'soul_form_contemplate','life_death')
    assert before==e.store._path(g.id).read_bytes()


@pytest.mark.parametrize('path,preset',[('ghost','reincarnation_upper'),('monster','nether_upper')])
@pytest.mark.parametrize('realm',[9,10,11])
def test_trial_snapshots_power_fields_and_real_entry(ready,path,preset,realm):
    e,_=ready
    args={'monster_species_id':'serpent'} if path=='monster' else {}
    shown=e.create_game('渡劫', 'mutated_yin',path,261,preset_id=preset,**args)
    g=e._load(shown['id']);p=g.player;p.realm_index=realm;p.layer=9;p.awaiting_major_breakthrough=True
    if path=='monster':
        from cultivation_life.engine.orchestration.dlc_birth import monster
        monster(p,261)
    key=definitions(p)[0]['id'];p.world_voisinages[p.world]={'levels':{key:12},'active':key}
    p.immortal_aperture.update(current=1000,capacity=1000)
    fund(g);e.store.save(g)
    if path=='ghost':e.breakthrough(g.id)
    else:
        from cultivation_life.system.monster_bloodline_system import evolution_candidates
        choice=next(c for c in evolution_candidates(p) if c['enabled'])
        e.evolve_monster(g.id,choice['id'])
    g=e._load(g.id);t=g.active_trial;b=load_battle(t['snapshot'])
    assert t['kind']==path+'_upper' and g.player.realm_index==realm
    enemies=[v for k,v in b.units.items() if k!='player']
    assert len(enemies)==(2 if realm==11 else 1)
    for enemy in enemies:
        assert enemy.unit.power==b.units['player'].unit.power
        assert bool(enemy.unit.capabilities.voisinages)==(realm>=10)
        if realm>=10:
            assert enemy.unit.capabilities.voisinages[0].stability==player_source(p,cap=8).voisinages[0].stability
    for stat,v in t['battle_state']['stats']['player'].items():assert t['battle_state']['stats']['enemy'][stat]==v*len(enemies)
    # Actual event load/submit; either a real defeat or real victory is accepted.
    result=e.choose(g.id,'fight',event_id=g.pending_event['id'])
    saved=e._load(g.id)
    if realm<11 and saved.player.alive:
        assert saved.player.realm_index==realm+1 and not saved.active_trial
        assert result['last_combat_report']['total_rounds']==5
    elif not saved.player.alive:
        assert saved.player.realm_index==realm and not saved.active_trial


def test_soul_read_only_and_possession_frozen(ready):
    e,g=ready;soul.confirm(g,'life_death','guard');before=g.to_dict()
    for _ in range(3):soul.public(g.player,g)
    assert g.to_dict()==before
    g.player.ghost_host_body={'id':'host'}
    g.player.ghost_core_state={}
    with pytest.raises(ValueError,match='寄身'):soul.validate(g.player)
    assert not soul.definition(g.player)


def test_interrupted_contemplation_resumes_remaining_clock_once(ready):
    e,g=ready;age=g.player.age
    with patch.object(e,'_advance_world_year',return_value=False):
        e.upper_voisinage_action(g.id,'soul_form_contemplate','life_death')
    g=e._load(g.id)
    assert g.player.age==age+1 and not g.active_trial
    assert g.player.world_voisinages['reincarnation']['contemplation']['elapsed']==1
    with pytest.raises(ValueError,match='未完成'):e.upper_voisinage_action(g.id,'soul_form_contemplate','oath')
    with patch.object(e,'_advance_world_year',return_value=True):
        shown=e.upper_voisinage_action(g.id,'soul_form_contemplate','life_death')
    assert shown['pending_event']['id']=='EVT_SOUL_CONTEMPLATION'
    assert e._load(g.id).player.age==age+100
    e.choose(g.id,'cancel')
    assert not e._load(g.id).active_trial and soul.stored(e._load(g.id).player) is None
