"""Regional gameplay, knowledge boundaries, merchant snapshots and war tiers."""
import copy
import json
import random

import pytest

from test_heavens_m1 import local, quiet, issue, ROOT
from test_heavens_incidents import positioned, finish
from cultivation_life.models import SectNpc
from cultivation_life.rules import max_mp
from cultivation_life.system.heavens import intelligence, operations
from cultivation_life.system.heavens.incident_definitions import REGIONAL_CASES, response
from cultivation_life.system.heavens.schema import validate_state
from cultivation_life.system.war.policy import system_war_allowed
from cultivation_life.ui_preferences import load_ui_preferences, write_ui_preferences


def test_regions_are_distinct_and_use_real_map_sites():
    maps = json.loads((ROOT/'content/maps.json').read_text(encoding='utf-8'))['worlds']
    assert len(REGIONAL_CASES) == 22
    for category in ('anomaly', 'conflict'):
        rows = [r for r in REGIONAL_CASES if r.category == category]
        assert {r.world for r in rows} == maps.keys()-{'rift', 'lost'}
        assert len({r.name for r in rows}) == len({r.glimpse for r in rows}) == 11
        for row in rows:
            assert {row.location, row.field} <= {p['id'] for p in maps[row.world]['locations']}


@pytest.mark.parametrize('desc', REGIONAL_CASES, ids=lambda d:d.id)
@pytest.mark.parametrize('action', ['incident_preserve', 'incident_seal'])
def test_regional_branches_are_persisted_real_actions(local, desc, action):
    bundle = quiet(local)
    work = positioned(bundle, desc)
    if desc.category == 'conflict' and action == 'incident_preserve':
        patient = SectNpc('regional-patient', '伤者', '散修', desc.rank, 1, 30, None,
                          world=desc.world, location_id=desc.field)
        patient.wounds = 3
        work.world_npcs[patient.id] = patient
        bundle[0].store.save(work)
    start = work.player.age
    work = finish(bundle, desc, action)
    saved = work.heavens_state['runtime']['incidents'][desc.id]
    assert saved['stage'] == 'closed'
    assert work.player.age-start == desc.survey_years+response(desc, action).years+2
    if response(desc, action).effect == 'aid':
        assert work.world_npcs['regional-patient'].wounds == 2
        assert '伤者' in saved['outcome']
    elif response(desc, action).effect == 'mana':
        assert work.player.mp <= max_mp(work.player)
        assert '实际恢复' in saved['outcome']
    validate_state(work.heavens_state)
    with pytest.raises(ValueError):
        issue(bundle, action, target=desc.id)


def test_no_synthetic_patients_or_cross_world_treatment(local):
    bundle = quiet(local)
    desc = next(r for r in REGIONAL_CASES if r.id == 'human_conflict')
    positioned(bundle, desc); issue(bundle, 'incident_survey', target=desc.id)
    positioned(bundle, desc, True)
    before = bundle[0].store._path(bundle[1].id).read_bytes()
    with pytest.raises(ValueError, match='实际伤者'):
        issue(bundle, 'incident_preserve', target=desc.id)
    assert bundle[0].store._path(bundle[1].id).read_bytes() == before
    issue(bundle, 'incident_seal', target=desc.id)


def war(world='celestial'):
    return dict(id='test-war', world=world, status='active', logs=[dict(text='玉京：甲宗与乙宗交锋，甲宗撤退。')])


@pytest.mark.parametrize('observer,subject,expected', [
    ('human','celestial',1),('human','spirit',2),('spirit','celestial',2),
    ('spirit','human',3),('celestial','human',3),('celestial','spirit',3),('celestial','asura',3)])
def test_same_real_event_has_observer_relative_detail(local, observer, subject, expected):
    game=local[1];game.player.world=observer;game.wars=[war(subject)]
    before=copy.deepcopy(game.to_dict())
    row=intelligence.news(game)[0]
    assert row['level']==expected
    if expected<3:
        assert not {'war_id','world','status'} & row.keys()
        assert '玉京' not in row['text'] and '甲宗' not in row['text'] and '撤退' not in row['text']
    if expected==1:
        assert '仙界' not in row['text']
    assert game.to_dict()==before


def test_hidden_dossiers_cannot_be_fetched_directly(local):
    engine, game, deps=local
    game.player.world='human';engine.store.save(game)
    view=operations.project(game,'known',deps=deps)
    serialized=json.dumps(view,ensure_ascii=False)
    assert '登仙台逆诏' not in serialized and '玉京护送簿' not in serialized
    assert view['sites']==[] and view['migrations']==[]
    for target in ('celestial_anomaly','celestial_conflict','celestial_seal','sea_echo'):
        with pytest.raises(ValueError,match='远界传闻'):
            engine.heavens_view(game.id,'known',target)
        with pytest.raises(ValueError,match='远界传闻'):
            operations.preview(deps, game.id, 'observe' if target == 'sea_echo' else 'incident_survey', target, {})


def test_merchant_completion_preserves_snapshot_without_live_access(local):
    engine,game,_=local;game.player.world='human';game.wars=[war()]
    engine._ensure_merchant(game)
    report=engine._merchant_intelligence(game,'celestial',3,random.Random(9))
    assert '甲宗撤退' in report
    saved=copy.deepcopy(game.merchant_state['heavens_reports'])
    assert saved[0]['level']==3 and saved[0]['acquired_age']==game.player.age
    game.wars[0]['logs'].append(dict(text='乙宗撤退，新一轮已结束。'))
    assert intelligence.news(game)[0]['level']==1
    assert game.merchant_state['heavens_reports']==saved
    assert '乙宗撤退' not in saved[0]['text']


def test_merchant_relay_only_accepts_intelligence(local):
    engine,game,_=local;game.player.world='human';engine._ensure_merchant(game)
    alliance=game.merchant_state['worlds']['human'][0]
    catalog=engine._merchant_procurement_catalog(game,alliance)
    remote=next(row for row in catalog if row['world']=='celestial')
    assert remote['intel_only'] and not remote['targets'] and not remote['materials']
    quote=engine._merchant_quote(game,alliance,dict(kind='intel',source_world='celestial',stars=3))
    assert quote['years']>0 and quote['fee']>0
    with pytest.raises(ValueError,match='无法发布委托'):
        engine._merchant_quote(game,alliance,dict(kind='escort',source_world='celestial',stars=3))


def test_system_war_tiers_and_player_exception(local):
    engine,game,_=local
    first,second=list(game.sects.values())[:2]
    first.world='celestial';second.world='human'
    assert not system_war_allowed(game,'sect',first.id,second.id)
    before=copy.deepcopy(game.to_dict())
    with pytest.raises(ValueError,match='同层级'):
        engine._start_war(game,'sect',first.id,second.id)
    assert game.to_dict()==before
    started=engine._start_war(game,'sect',first.id,second.id,initiated_by_player=True)
    assert started in game.wars
    second.world='asura'
    assert system_war_allowed(game,'sect',first.id,second.id)


@pytest.mark.parametrize('old,new',[('c','a'),('e','f')])
def test_retired_theme_migration_preserves_motion(tmp_path,old,new):
    (tmp_path/'data').mkdir()
    (tmp_path/'data/ui_preferences.json').write_text(json.dumps(dict(theme=old,reduced_motion=True)))
    assert load_ui_preferences(tmp_path)==dict(theme=new,reduced_motion=True)
    with pytest.raises(ValueError):write_ui_preferences(tmp_path,dict(theme=old))
