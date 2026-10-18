"""Real event submission and resumption after a Guixu announcement."""
import copy
import random
from unittest.mock import patch
import pytest

from test_regional_calendar import regional
from test_concubine_system import _AlwaysTrigger
from cultivation_life.content_registry import CONTENT_DOCUMENTS


def prepare_journey(engine, game):
    game.settings.update(silent_events=False, guixu_event_popup=True)
    game.player.realm_index = 4
    game.player.layer = 1
    game.player.next_tribulation_age = None
    destination = 'lanjiang_steppe'
    plan = engine.maps.travel_plan(game.player.world, game.player.location_id, destination, 4,
                                  engine._monster_travel_multiplier(game.player, destination))
    assert plan.years > 1
    dungeon = next(d for d in engine._guixu_definitions().values() if d['world'] == 'human')
    cycle = game.guixu_state['cycles'][dungeon['id']]
    cycle.update(phase='closed', next_announce_age=game.player.age + 1,
                 next_open_age=game.player.age + 1 + dungeon['announce_lead_years'])
    engine.store.save(game)
    return destination, plan.years


def test_guixu_event_travel_reload_and_resume_keeps_total_time(regional):
    engine, game = regional
    destination, total = prepare_journey(engine, game)
    start = game.player.age
    engine.travel_map(game.id, destination)
    first = engine.store.load(game.id)
    assert first.pending_event['id'] == 'EVT_GUIXU_ANNOUNCE'
    assert first.map_journey['completed'] == first.player.age - start == 1
    with pytest.raises(ValueError, match='事件'):
        engine.travel_map(game.id, destination)
    public = engine.get_game(game.id)
    choice = next(c['id'] for c in public['pending_event']['choices'] if c.get('enabled', True))
    engine.choose(game.id, choice, event_id='EVT_GUIXU_ANNOUNCE')
    after = engine.store.load(game.id)
    assert after.map_journey['completed'] == 1
    # Later natural notifications can interrupt again. Resolve each through
    # the real submit endpoint; no silent-events shortcut or fake year hook.
    for _ in range(30):
        shown = engine.get_game(game.id)
        if shown['pending_event']:
            event = shown['pending_event']
            choice = next(c['id'] for c in event['choices'] if c.get('enabled', True))
            engine.choose(game.id, choice, event_id=event['id'])
        else:
            engine.travel_map(game.id, destination)
        after = engine.store.load(game.id)
        if after.player.location_id == destination:
            break
    assert after.player.location_id == destination
    assert after.player.age - start == total
    assert after.map_journey is None


@pytest.mark.parametrize('role', ['master', 'dao_companion', 'dao_friends', 'disciples', 'concubines', 'offspring'])
def test_existing_special_role_never_receives_proposal(regional, role):
    engine, game = regional
    game.settings['silent_events'] = False
    game.player.gender = 'female'
    npc = next(iter(game.world_npcs.values()))
    npc.gender, npc.realm_index, npc.world = 'male', 4, game.player.world
    related = dict(id=npc.id, npc_id=npc.id, world=npc.world, alive=True)
    setattr(game.player, role, [related] if role in {'dao_friends','disciples','concubines','offspring'} else related)
    with patch.object(engine, '_all_world_npcs', return_value=[npc]):
        assert not engine._maybe_concubine_proposal(game, _AlwaysTrigger())
    before = npc.affinity
    result, _ = engine._resolve_concubine_proposal(game, dict(runtime=dict(owner_id=npc.id)), False)
    assert result == 'relationship_changed' and npc.affinity == before
    assert not game.player.concubine_rejection_aftermath


def test_spirit_crossing_checks_one_point_three():
    import json
    from test_regional_calendar import ROOT
    data = json.loads((ROOT/'content/story_chain_events.json').read_text(encoding='utf-8'))
    event = next(e for e in data['events'] if e['id'] == 'EVT_SPIRIT_CROSSING_003')
    check = event['choices'][0]['effects'][0]['checks'][0]
    assert check == dict(stat='combat_ratio', op='gte', value=1.3)
