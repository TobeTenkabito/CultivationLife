"""Adversarial school lifecycle and combat regressions using original actors."""
import copy
import random
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from test_npc_development import game
from test_mentorship import school
from test_mentorship_advanced import heir, make_avatar, deps
from cultivation_life.engine import GameEngine
from cultivation_life.models import SectNpc, GameState
from cultivation_life.system import mentorship as m, mentorship_advanced as a
from cultivation_life.rules import combat_power
from cultivation_life.runtime import encode_rng


@pytest.fixture
def live(tmp_path):
    engine = GameEngine(Path(__file__).resolve().parents[1], tmp_path)
    view = engine.create_game('师徒对抗', 'supreme_metal', 'demonic', 717,
                             custom_start={'world':'human','realm_index':4,'layer':5,'sect':'new'})
    game = engine._load(view['id']);p = game.player
    game.pending_event = None;p.opportunity = 10**9
    npc = SectNpc('audit-heir', '原嫡传', '', 2, 3, 40, 500, world=p.world,
                  location_id=p.location_id, spirit_root='supreme_metal', body_training=10, divine_sense_rank=17)
    game.world_npcs[npc.id] = npc
    p.disciples.append(game.link_relationship({'id':npc.id}))
    m.admit(game, 'player', npc.id).update(rank='heir', loyalty=100)
    return engine, game, npc


def ally(school):
    m.admit(school, 'teacher', 'player')
    key = next(k for k in m.rows(school, 'teacher') if k != 'player')
    m.person(school, key).affinity = 80
    m.record(school, 'teacher', key)['loyalty'] = 20
    a.execute(deps(school), school, 'plot', key, random.Random(1))
    return key


def test_dead_master_does_not_block_new_school(school):
    m.admit(school, 'teacher', 'player')
    school.world_npcs['teacher'].alive = False
    replacement = copy.deepcopy(school.world_npcs['teacher'])
    replacement.id = 'replacement';replacement.alive = True
    school.world_npcs[replacement.id] = replacement
    assert not m.admission_reason(school, replacement.id, 'player')


def test_warning_survives_power_order_change(heir):
    row = m.record(heir, 'player', 'student');row['loyalty'] = 10
    other = copy.deepcopy(heir.world_npcs['student']);other.id = 'other'
    heir.world_npcs[other.id] = other
    heir.player.disciples.append(heir.link_relationship({'id':other.id}))
    m.admit(heir, 'player', other.id)['loyalty'] = 10
    power = combat_power(heir.player)
    values = {'student':power, 'other':power * .9}
    port = deps(heir);port._npc_power = lambda n:values[n.id]
    a.maybe_rebellion(port, heir, random.Random(1))
    warned = heir.mentorship_state['rebellion']['at']
    heir.player.age += 1
    values['other'] = power * 1.1
    a.maybe_rebellion(port, heir, random.Random(1))
    assert heir.mentorship_state['rebellion']['at'] == warned
    assert len([h for h in heir.history if h.choice_id == 'rebellion_warning']) == 1


def test_winning_with_master_escape_still_transfers_school(school):
    key = ally(school)
    port = deps(school, outcome='victory_escape')
    a.execute(port, school, 'challenge_master', '', random.Random(1))
    assert m.record(school, 'teacher', 'player')['status'] == 'departed'
    assert any(r['id'] == key for r in school.player.disciples)
    assert m.person(school, 'teacher').alive


def test_failed_betrayal_still_changes_master_hostility(school):
    ally(school)
    a.execute(deps(school, outcome='defeat'), school, 'challenge_master', '', random.Random(1))
    assert m.person(school, 'teacher').affinity <= -60


def test_legacy_expulsion_archives_school_record(school, tmp_path):
    engine = GameEngine(Path(__file__).resolve().parents[1], tmp_path)
    row = m.admit(school, 'teacher', 'player')
    row.update(rank='heir');row['advanced'] = {'plot':True}
    engine._end_sanctioned_relationship(school, 'master', '师父')
    assert school.player.master is None
    assert row['status'] == 'expelled' and not row['advanced']['plot']


def test_permanent_departure_archives_gifts_and_revokes_pacts(live):
    engine, game, npc = live
    relation = game.player.disciples[0]
    relation['items'] = {'npc_training_dao_body_1':2}
    row = m.record(game, 'player', npc.id)
    row['advanced'] = {'pact_avatar':True}
    plan = engine._plan_world_transition(game, 'spirit')
    engine._apply_world_transition(game, plan)
    assert not game.player.disciples
    assert row['status'] == 'departed' and not row['advanced']['pact_avatar']
    assert row['former_relation']['items'] == {'npc_training_dao_body_1':2}
    restored = GameState.from_dict(game.to_dict())
    assert m.record(restored, 'player', npc.id)['former_relation']['items'] == relation['items']


def test_breakthrough_event_cannot_skip_avatar_year(live, monkeypatch):
    engine, game, npc = live
    a.execute(engine, game, 'refine_avatar', npc.id, random.Random(1))
    original_age = npc.age
    def interrupt(g, rng):
        g.pending_event = {'id':'EVT_MASTER_ENCOUNTER_001'}
    monkeypatch.setattr(engine, '_resolve_breakthroughs', interrupt)
    game.player.age += 1
    engine._advance_world_year(game, random.Random(8), [], encounters=False)
    assert npc.age == original_age + 1
    assert game.mentorship_state['avatar']['last_age'] == game.player.age


def test_mortal_avatar_receives_real_combat_damage(live):
    engine, game, npc = live
    a.execute(engine, game, 'refine_avatar', npc.id, random.Random(1))
    power = sum(u.power for u in engine._player_combat_units(game))
    target = dict(target_name='来犯之人',target_power=power * 1.2,primary_power=power * 1.2,
                  target_realm_index=4,target_layer=5,path='dao',world='human',
                  combat_type='cultivator',action='spar',max_rounds=8,non_story_combat=True)
    engine._combat(game, target, False, random.Random(37))
    report = game.last_combat_report
    update = next((r for r in report['capability_updates'] if r['id'] == npc.id), None)
    assert update is not None, 'mortal original actor was omitted from combat settlement'
    assert update['vitality'] < 1 and npc.wounds > 0
    assert npc.alive


@pytest.mark.parametrize('route', ['capture', 'guixu'])
def test_legacy_master_breaks_archive_once(school, tmp_path, route):
    engine = GameEngine(Path(__file__).resolve().parents[1], tmp_path)
    row = m.admit(school, 'teacher', 'player')
    school.player.master['items'] = {'npc_training_dao_body_1':3}
    if route == 'capture':
        engine._break_capture_relationship(school, school.player.master, 'master', True)
    else:
        engine._break_guixu_relationship(school, 'teacher', player_defending=True)
    assert row['status'] == 'departed'
    assert row['former_relation']['items'] == {'npc_training_dao_body_1':3}
    m.end_person_relations(school, 'teacher')
    assert row['former_relation']['items'] == {'npc_training_dao_body_1':3}


@pytest.mark.parametrize('kind,success', [('living',True),('corpse',True),('corpse',False)])
def test_old_puppet_conversion_closes_inheritance(live, kind, success):
    engine, game, npc = live
    row = m.record(game, 'player', npc.id)
    row['advanced'] = {'pact_avatar':True,'precision_cycle':0,'precision_used':2}
    relation = game.player.disciples[0]
    relation['items'] = {'npc_training_dao_body_1':2}
    rng = Mock(wraps=random.Random(4));rng.random.return_value = 0. if success else .999
    result, _ = engine._convert_to_puppet(game, relation, kind, rng, True)
    assert result == ('created' if success else 'destroyed')
    assert not game.player.disciples
    assert row['status'] == 'departed' and not row['advanced']['pact_avatar']
    assert row['advanced']['precision_used'] == 2
    assert row['former_relation']['items'] == {'npc_training_dao_body_1':2}


def test_old_concubine_conversion_closes_inheritance(live):
    engine, game, npc = live
    npc.gender = 'female';npc.affinity = 100
    game.rng_state = encode_rng(random.Random(1))
    game.player.disciples[0]['items'] = {'npc_training_dao_body_1':2}
    m.record(game, 'player', npc.id)['advanced'] = {'pact_possession':True}
    engine.store.save(game)
    engine.manage_concubine(game.id, npc.id, 'recruit')
    saved = engine.store.load(game.id)
    assert any(r['id'] == npc.id for r in saved.player.concubines)
    row = m.record(saved, 'player', npc.id)
    assert row['status'] == 'departed' and not row['advanced']['pact_possession']
    assert row['former_relation']['items'] == {'npc_training_dao_body_1':2}
    assert not saved.player.concubines[0].get('items'), 'archived gifts must not be copied into the new relation'


@pytest.mark.parametrize('outcome', ['killed', 'victory_escape', 'defeat'])
def test_old_violence_ends_school_even_when_target_survives(live, monkeypatch, outcome):
    engine, game, npc = live
    game.player.disciples[0]['items'] = {'npc_training_dao_body_1':2}
    m.record(game, 'player', npc.id)['advanced'] = {'pact_avatar':True}
    engine.store.save(game)
    monkeypatch.setattr(engine, '_combat', Mock(return_value=(outcome, '战斗结果')))
    engine.relationship_violence(game.id, 'disciple', npc.id)
    saved = engine.store.load(game.id)
    row = m.record(saved, 'player', npc.id)
    assert not saved.player.disciples
    assert row['status'] == 'departed' and not row['advanced']['pact_avatar']
    assert row['former_relation']['items'] == {'npc_training_dao_body_1':2}
    original = m.person(saved, npc.id)
    assert original.alive == (outcome != 'killed')
    if original.alive: assert original.affinity == -100


def test_actual_new_admission_archives_dead_master_metadata(live):
    engine, game, _ = live
    old = SectNpc('old-teacher','故师','',5,2,100,900,world='human',location_id=game.player.location_id)
    new = SectNpc('new-teacher','新师','',5,3,100,900,world='human',location_id=game.player.location_id)
    game.world_npcs[old.id] = old
    new.faction_id = game.player.faction_id
    game.sects[game.player.faction_id].npcs.append(new)
    game.player.master = game.link_relationship({'id':old.id})
    m.admit(game, old.id, 'player')
    game.player.master['items'] = {'npc_training_dao_body_1':4}
    old.alive = False
    game.rng_state = encode_rng(random.Random(1))
    engine.store.save(game)
    engine.manage_faction_relationship(game.id, new.id, 'master')
    saved = engine.store.load(game.id)
    assert saved.player.master['id'] == new.id
    history = m.record(saved, old.id, 'player')
    assert history['status'] == 'departed'
    assert history['former_relation']['items'] == {'npc_training_dao_body_1':4}


@pytest.mark.parametrize('outcome', ['defeat','dead','defeat_survived','controlled','stalemate'])
def test_failed_takeover_never_transfers_peers(school, outcome):
    key = ally(school)
    a.execute(deps(school, outcome), school, 'challenge_master', '', random.Random(1))
    assert m.record(school, 'teacher', 'player')['status'] == 'expelled'
    assert not any(r['id'] == key for r in school.player.disciples)


@pytest.mark.parametrize('change', [
    lambda g,k:setattr(m.person(g,k), 'location_id', 'elsewhere'),
    lambda g,k:setattr(m.person(g,k), 'world', 'spirit'),
    lambda g,k:setattr(m.person(g,k), 'alive', False),
    lambda g,k:m.record(g,'teacher',k).update(loyalty=80),
    lambda g,k:m.record(g,'teacher',k).update(rank='registered'),
])
def test_stale_plot_rejected_before_combat_and_charge(school, change):
    key = ally(school);change(school,key)
    before = copy.deepcopy(school.to_dict());port = deps(school)
    with pytest.raises(ValueError): a.execute(port, school, 'challenge_master', '', random.Random(1))
    assert school.to_dict() == before and not port._combat.called
