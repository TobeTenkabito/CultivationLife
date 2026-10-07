"""Real event persistence boundaries and all-world treasure coverage."""
import copy
import random
from pathlib import Path

import pytest

from cultivation_life.content_registry import MARKET_GOODS, WORLD_SYSTEMS
from cultivation_life.engine import GameEngine
from cultivation_life.engine.persistence.events import prepare_events
from cultivation_life.rules import max_hp, max_mp


@pytest.fixture
def local(tmp_path):
    engine = GameEngine(Path(__file__).resolve().parents[1], tmp_path / 'saves')
    game = engine.store.load(engine.create_game('事件验收', 'heavenly', 'demonic', 212, preset_id='core')['id'])
    game.player.path = 'demonic'
    return engine, game


@pytest.mark.parametrize('world', [w for w, p in WORLD_SYSTEMS['world_profiles'].items() if p['tier'] > 0])
@pytest.mark.parametrize('category', ['pill', 'artifact', 'technique'])
def test_every_world_and_location_has_lower_tier_treasure(local, world, category):
    engine, game = local
    game.player.world = world
    cap = WORLD_SYSTEMS['world_profiles'][world]['npc_realm_cap']
    game.player.realm_index = cap
    for location in engine.maps.worlds[world]['locations']:
        game.player.location_id = location['id']
        pool = engine._treasure_reward_pool(game, category)
        assert set(range(1, min(cap, 8) + 1)) <= {row['tier'] for row in pool}
        assert all(row['tier'] <= cap for row in pool)
        assert len({row['content_id'] for row in pool}) == len(pool)
        assert all(row['world'] == world for row in pool)
    game.player.realm_index = 1
    assert {row['tier'] for row in engine._treasure_reward_pool(game, category)} == {1}


def test_treasure_inheritance_does_not_change_market_or_catalog(local):
    engine, game = local
    before = copy.deepcopy(MARKET_GOODS)
    game.player.world = 'spirit'
    game.player.location_id = engine.maps.default_location('spirit')
    game.player.realm_index = 5
    first = engine._treasure_reward_pool(game, 'artifact')
    assert first == engine._treasure_reward_pool(game, 'artifact')
    assert before == MARKET_GOODS
    market = engine.maps.localize_goods(MARKET_GOODS, 'spirit', game.player.location_id, 'market')
    assert all(row in MARKET_GOODS and row['world'] == 'spirit' for row in market)


@pytest.mark.parametrize('rank', [0, 1, 5, 9])
def test_all_registered_event_definitions_survive_pending_reconciliation(local, rank):
    engine, game = local
    game.player.realm_index = rank
    deps = engine._dependencies.persistence_runtime.events
    rng = game.rng_state
    for definition in engine.events:
        game.pending_event = {key: copy.deepcopy(definition[key]) for key in ('id', 'title', 'body', 'choices')}
        prepare_events(deps, game)
        assert game.pending_event['id'] == definition['id']
        assert set(row['id'] for row in definition['choices']) <= set(row['id'] for row in game.pending_event['choices'])
        assert all('effects' not in row and 'conditions' not in row for row in game.pending_event['choices'])
        assert not prepare_events(deps, game), definition['id']
    assert game.rng_state == rng


@pytest.mark.parametrize('kind', ['master', 'companion'])
def test_manual_relationship_capture_at_mortal_rank_can_be_resolved_after_reload(local, kind):
    engine, game = local
    game.player.realm_index = 0
    game.player.layer = 1
    game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
    person = {'id': 'nearby', 'name': '故人', 'world': 'human', 'realm_index': 1,
              'layer': 1, 'alive': True, 'age': 30, 'lifespan': 100, 'path': 'dao', 'combat_power': 10}
    setattr(game.player, 'master' if kind == 'master' else 'dao_companion', person)
    engine.store.save(game)
    shown = engine.begin_relationship_capture(game.id, kind, person['id'])
    assert shown['pending_event']['id'] == 'EVT_RELATION_CAPTURE_001'
    reloaded = engine.get_game(game.id)
    assert reloaded['pending_event']['id'] == shown['pending_event']['id']
    choice = next(c for c in engine.events_by_id[shown['pending_event']['id']]['choices']
                  if any(e.get('stage') == 'abandon' for e in c['effects']))
    resolved = engine.choose(game.id, choice['id'], event_id=shown['pending_event']['id'])
    assert resolved['pending_event'] is None


@pytest.mark.parametrize('kind', ['master', 'companion'])
def test_real_relationship_interception_warning_remains_actionable(local, kind):
    engine, game = local
    player = game.player
    player.realm_index, player.layer = 4, 3
    player.hp, player.mp = max_hp(player), max_mp(player)
    player.faction_id = 'tianjian'
    sect = game.sects[player.faction_id]
    target, leader = sect.npcs[:2]
    target.alive, target.realm_index, target.layer = True, 1, 1
    target.treasure_item_id = None
    leader.alive, leader.realm_index, leader.layer = True, 5, 9
    setattr(player, 'master' if kind == 'master' else 'dao_companion', target.to_dict())
    engine.store.save(game)
    shown = engine.relationship_violence(game.id, kind, target.id)
    assert shown['pending_event']['id'] == 'EVT_SECT_FIRST_WARNING_001'
    assert engine.get_game(game.id)['pending_event']['id'] == shown['pending_event']['id']
    resolved = engine.choose(game.id, 'acknowledge', event_id=shown['pending_event']['id'])
    assert resolved['pending_event'] is None
    assert engine.store.load(game.id).player.faction_id is not None


def test_repair_old_choices_and_preserve_reward_behind_removed_content(local):
    engine, game = local
    warning = engine._instantiate_event(engine.events_by_id['EVT_SECT_FIRST_WARNING_001'], game, random.Random(1))
    warning['choices'] = [{'id': 'obsolete_option', 'text': '旧选项', 'enabled': True}]
    reward = engine._prepare_treasure_reward_event(game, random.Random(2))
    warning['_followup_event'] = {'id': 'REMOVED_CONTENT', 'title': '已移除剧情', 'choices': [], '_followup_event': reward}
    game.pending_event = warning
    engine.store.save(game)
    shown = engine.get_game(game.id)
    assert [c['id'] for c in shown['pending_event']['choices']] == ['acknowledge']
    assert shown['pending_event']['_followup_event']['runtime'] == reward['runtime']
    result = engine.choose(game.id, 'acknowledge')
    assert result['pending_event']['id'] == reward['id']
    engine.choose(game.id, 'artifact')
    with pytest.raises(ValueError, match='没有待处理事件'):
        engine.choose(game.id, 'artifact')


def test_disabled_runtime_choices_and_stale_event_submission_are_rejected(local):
    engine, game = local
    event = engine._instantiate_event(engine.events_by_id['EVT_PERSONAL_REVENGE_001'], game, random.Random(1))
    event['choices'][0]['enabled'] = False
    event['choices'][0]['disabled_reason'] = '此人已不在场'
    game.pending_event = event
    engine.store.save(game)
    engine.get_game(game.id)
    before = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError, match='已经变化'):
        engine.choose(game.id, event['choices'][0]['id'], event_id='OLD_EVENT')
    with pytest.raises(ValueError, match='此人已不在场'):
        engine.choose(game.id, event['choices'][0]['id'], event_id=event['id'])
    assert engine.store._path(game.id).read_bytes() == before


def test_removed_head_promotes_earned_reward_without_reroll(local):
    engine, game = local
    reward = engine._prepare_treasure_reward_event(game, random.Random(2))
    game.pending_event = {'id': 'REMOVED_CONTENT', 'choices': [], '_followup_event': reward}
    engine.store.save(game)
    shown = engine.get_game(game.id)
    assert shown['pending_event']['runtime'] == reward['runtime']
    assert engine.store.load(game.id).rng_state == game.rng_state
    assert engine.store.load(game.id).history[-1].state_diff['event_id'] == 'REMOVED_CONTENT'
    engine.choose(game.id, 'pill', event_id=reward['id'])
    assert engine.store.load(game.id).pending_event is None


def test_event_structure_is_reconciled_inside_independent_space(local):
    from test_spatial_talismans import occupy
    engine, game = local
    occupy(engine, game)
    warning = engine._instantiate_event(engine.events_by_id['EVT_SECT_FIRST_WARNING_001'], game, random.Random(1))
    warning['choices'] = [{'id': 'obsolete_option', 'text': '旧选项'}]
    game.pending_event = warning
    engine.store.save(game)
    shown = engine.get_game(game.id)
    assert shown['pending_event']['choices'][0]['id'] == 'acknowledge'
    assert engine.store.load(game.id).pending_event['choices'][0]['id'] == 'acknowledge'
    assert engine.choose(game.id, 'acknowledge')['pending_event'] is None
