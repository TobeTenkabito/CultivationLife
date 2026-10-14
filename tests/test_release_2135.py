"""Actual commands for reversible descent, partial work and captive lifespan repairs."""
import json
import sys
import copy
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from test_other_systems_audit_fixes import api, snapshot
from test_relationship_possession_audit_fixes import relationship_game
from cultivation_life.content_registry import REALMS
from cultivation_life.models import SectNpc
from cultivation_life.rules import max_hp, max_mp
from cultivation_life.system.owned_training import quote
from cultivation_life.system.upper_institutions import account, definition


@pytest.mark.parametrize('path', ['dao', 'monster'])
def test_training_quote_keeps_preview_pure_and_updates_finite_lifespan(path):
    from cultivation_life.models import Player
    player=Player('师长','supreme_metal',realm_index=8,layer=1)
    player.opportunity=1e8;player.mp=max_mp(player)
    target=dict(name='目标',realm_index=1,layer=REALMS[1].layers,age=30,lifespan=70,path=path,combat_power=100)
    original=copy.deepcopy(target)
    plan=quote(player,target,'cultivation',1)
    multiplier=3 if path=='monster' else 1
    assert target==original
    assert plan['result']['lifespan'] >= REALMS[2].lifespan[0]*multiplier
    target['lifespan']=None
    assert quote(player,target,'cultivation',1)['result']['lifespan'] is None


def report(name, facts):
    print(name + ': ' + json.dumps(facts, ensure_ascii=False), flush=True)


def test_disabled_race_content_skips_recruitment_without_rng_or_roster_changes(api,monkeypatch):
    from cultivation_life.engine.world import npcs
    from cultivation_life.models import SectState
    import random
    engine,_=api
    monkeypatch.setattr(npcs,'RACE_DEFINITIONS',{})
    sect=SectState('empty-race','目标宗门','nether',npcs=[])
    rng=random.Random(8712);before=rng.getstate()
    assert engine._recruit_sect_npc(sect,1000,rng) is None
    assert not sect.npcs and rng.getstate()==before


def test_temporary_descent_returns_and_preserves_original_ties(api):
    engine, act = api
    original = relationship_game(engine, 'spirit')
    faction, master = original.player.faction_id, original.player.master['id']
    due_age=original.player.age+3000
    original.player.next_tribulation_age=due_age
    engine.store.save(original)
    assert faction and master and original.player.disciples
    act(original.id, 'secret-art', art='suppress', action='activate', realm_index=1, layer=1)
    act(original.id, 'cross-world', destination='human')
    descended = engine._load(original.id)
    assert descended.player.world == 'human'
    assert descended.player.sealed_cultivation['visit_only']
    frozen = snapshot(engine, original.id)
    act(original.id, 'secret-art', art='suppress', action='cancel', status=400)
    assert engine.store._path(original.id).read_bytes() == frozen
    act(original.id,'advance',action='rest',years=1)
    act(original.id, 'cross-world', destination='spirit')
    act(original.id, 'secret-art', art='suppress', action='cancel')
    returned = engine._load(original.id)
    assert returned.player.world == 'spirit'
    assert returned.player.faction_id == faction
    assert returned.player.master['id'] == master and len(returned.player.disciples) == 1
    assert (returned.player.realm_index, returned.player.layer) == (8, 1)
    assert returned.player.faction_contribution == original.player.faction_contribution
    assert returned.player.cultivation_suppression is None and returned.player.sealed_cultivation is None
    assert returned.player.next_tribulation_age==due_age



def test_captive_training_to_immortal_rank_keeps_life_after_release(api):
    engine, act = api
    game = relationship_game(engine, 'spirit')
    npc = SectNpc('audit-trained', '培养俘虏', '', 5, REALMS[5].layers, 1000, 1001,
                  world='spirit', path='dao', spirit_root='supreme_metal')
    game.notable_npcs[npc.id] = npc
    prisoner = game.detain_person(dict(id=npc.id, combat_power=100))
    game.player.prisoners.append(prisoner)
    plan = quote(game.player, prisoner, 'cultivation', 1)
    game.player.opportunity = plan['opportunity'] + 10
    game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
    engine.store.save(game)
    act(game.id, 'owned-training', target_id=npc.id, kind='prisoner', axis='cultivation', batches=1)
    trained = engine._load(game.id).player.prisoners[0]
    assert trained['realm_index'] == 6 and REALMS[6].lifespan is None
    assert trained['lifespan'] is None
    act(game.id, 'captive-action', target_id=npc.id, action='release')
    act(game.id, 'advance', action='rest', years=1)
    final = engine._load(game.id).notable_npcs[npc.id]
    assert final.alive and final.lifespan is None
    report('trained_immortal_lifespan', {'trained_rank':trained['realm_index'], 'rank_lifespan':REALMS[6].lifespan,
        'saved_lifespan':trained['lifespan'], 'final_alive':final.alive, 'death_reason':final.death_reason})


def test_resumed_institution_job_consumes_only_remaining_years(api):
    engine, act = api
    shown = engine.create_game('机构履约审计', 'supreme_metal', 'dao', 8712,
        custom_start=dict(world='nether', realm_index=9, layer=1, immortal_power_converted=True))
    game = engine._load(shown['id'])
    game.pending_event = None
    game.settings['silent_events'] = True
    game.player.location_id = definition(game)['location']
    game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
    game.player.next_tribulation_age = game.player.age + 40
    game.player.tribulation_power = 1
    engine.store.save(game)
    act(game.id, 'upper-institution', action='join')
    act(game.id, 'upper-institution', action='accept')
    start_age = engine._load(game.id).player.age
    act(game.id, 'upper-institution', action='work')
    interrupted = engine._load(game.id)
    assert interrupted.player.age - start_age == 40
    assert account(interrupted)['job']['progress'] == 40
    assert interrupted.active_trial['kind'] == 'periodic_thunder'
    for _ in range(8):
        shown = engine.get_game(game.id)
        event = shown.get('pending_event')
        if not event:
            break
        choice = next(c for c in event['choices'] if c.get('enabled', True))
        act(game.id, 'choice', event_id=event['id'], choice_id=choice['id'])
    ready = engine._load(game.id)
    assert ready.player.alive and not ready.pending_event and not ready.active_trial
    remaining = account(ready)['job']['years'] - account(ready)['job']['progress']
    resume_age = ready.player.age
    act(game.id, 'upper-institution', action='work')
    final = engine._load(game.id)
    actual = final.player.age - resume_age
    assert remaining == 60 and actual == 60
    assert account(final)['job']['progress'] == account(final)['job']['years'] == 100
    report('institution_resume_overrun', {'first_elapsed':40, 'remaining_years':remaining,
        'resume_elapsed':actual, 'extra_years':actual-remaining, 'job_progress':account(final)['job']['progress']})
