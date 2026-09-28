import copy
import random
from pathlib import Path
from unittest.mock import patch

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.models import HistoryRecord, SectNpc
from cultivation_life.system.npc_social import social_hint, instantiate_social

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def setup(tmp_path):
    engine = GameEngine(ROOT, tmp_path)
    shown = engine.create_game('问道', 'supreme_wood', 'dao', seed=1440)
    game = engine.store.load(shown['id'])
    game.pending_event = None
    return engine, game


def test_social_preview_is_stable_pure_and_lazy(setup):
    engine, game = setup
    npc = next(n for sect in game.sects.values() for n in sect.npcs if social_hint(game, n)['companion_name'])
    before = game.to_dict()
    hint = social_hint(game, npc)
    assert hint == social_hint(game, npc)
    assert game.to_dict() == before
    count = len(game.notable_npcs)
    instantiate_social(game, npc)
    partner = game.notable_npcs[npc.social_profile['companion_id']]
    assert partner.name == hint['companion_name']
    assert partner.social_profile['companion_id'] == npc.id
    instantiate_social(game, npc)
    instantiate_social(game, partner)
    assert len(game.notable_npcs) == count + 1
    engine.store.save(game)
    loaded = engine.store.load(game.id)
    assert engine._find_npc(loaded, npc.id).social_profile == npc.social_profile
    assert loaded.notable_npcs[partner.id].to_dict() == partner.to_dict()


def test_fixed_pair_migrates_without_resurrecting_or_changing_age(setup):
    engine, game = setup
    npc = game.world_npcs['wu_xingyun']
    npc.name = '巫迟烟'; npc.gender = 'male'; npc.alive = False; npc.age += 83
    before_age = npc.age
    engine.store.save(game)
    loaded = engine._load(game.id)
    npc = loaded.world_npcs['wu_xingyun']
    assert (npc.name, npc.gender, npc.age, npc.alive) == ('巫行云', 'female', before_age, False)
    assert social_hint(loaded, npc)['companion_name'] == '曾沧海'
    instantiate_social(loaded, npc)
    assert loaded.world_npcs['zeng_canghai'].social_profile['companion_id'] == npc.id


def test_both_npc_views_show_only_name_and_count(setup):
    engine, game = setup
    game.player.faction_id = 'tianjian'
    sect_rows = engine._public_faction(game)['roster']
    world_rows = engine._public_world_npcs(game)
    for row in [*sect_rows, *world_rows]:
        if row.get('is_player'):
            continue
        assert set(row['social_hint']) <= {'companion_name', 'concubine_count'}
        assert 'social_profile' not in row


def test_master_consult_rewards_cooldown_and_clue_hook(setup):
    engine, game = setup
    npc = game.sects['tianjian'].npcs[0]
    npc.affinity = 20.0
    game.player.master = engine._relationship_snapshot(npc.id, npc.name, npc.realm_index, npc.layer,
        'tianjian', npc.age, npc.lifespan, world=npc.world)
    game.player.realm_index = 1
    game.player.layer = 1
    engine.store.save(game)
    before = game.player.opportunity
    affinity = game.player.master['affinity']
    with patch.object(engine, '_tianji_npc_conversation_clue', return_value=' 获悉天机榜线索。') as clue:
        engine.request_from_master(game.id, 'consult')
        clue.assert_called_once()
    loaded = engine.store.load(game.id)
    assert loaded.player.opportunity > before
    assert loaded.player.master['affinity'] > affinity
    assert loaded.player.master['last_requests']['consult'] == loaded.player.age
    with pytest.raises(ValueError, match='本年度'):
        engine.request_from_master(game.id, 'consult')
    loaded.player.age += 1
    loaded.player.master['world'] = 'spirit'
    # NPC world is authoritative when synchronizing relationships.
    engine._find_npc(loaded, npc.id).world = 'spirit'
    engine.store.save(loaded)
    with pytest.raises(ValueError):
        engine.request_from_master(game.id, 'consult')


def test_history_snapshot_remains_independent():
    record = HistoryRecord('test', 1, 300, 'test', None, 'ok', 'test', {'nested': {'items': [1]}}, ['world_news'])
    expected = copy.deepcopy(record)
    serialized = record.to_dict()
    serialized['state_diff']['nested']['items'].append(2)
    serialized['tags'].append('changed')
    assert record == expected


def test_indexed_treasures_preserve_candidates_and_rng():
    from cultivation_life.engine.world.npcs import _select_npc_treasure
    from cultivation_life.content_registry import MARKET_GOODS, ITEM_CATALOG
    worlds = {row.get('world', 'human') for row in MARKET_GOODS}
    for world in [*worlds, 'unknown']:
        for realm in range(0, 13):
            npc = SectNpc('probe', '索引校验', '', realm, 1, 30, None, world=world)
            actual_world = world if world in worlds else ('spirit' if realm >= 6 else 'human')
            candidates = [row for row in MARKET_GOODS if row['kind'] == 'item'
                          and row.get('world', 'human') == actual_world and int(row['tier']) == max(1, min(8, realm))
                          and not {'currency', 'root_manual'} & set(ITEM_CATALOG[row['content_id']].tags)]
            candidates.sort(key=lambda row: int(row['price']), reverse=True)
            old_rng, new_rng = random.Random(932), random.Random(932)
            expected = old_rng.choice(candidates[:4])['content_id'] if candidates else None
            assert _select_npc_treasure(npc, new_rng) == expected
            assert old_rng.getstate() == new_rng.getstate()
