import copy
import math
import random
from pathlib import Path
from unittest.mock import patch

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState
from cultivation_life.content_registry import CONTENT_DOCUMENTS, ITEM_CATALOG, TECHNIQUE_CATALOG, WORLD_SYSTEMS
from cultivation_life.rules import (add_item, has_item, learn_technique, effective_karma, effective_sha_qi,
                                    effective_fame, has_living_master, max_hp, max_mp, opportunity_required)
from cultivation_life.system.buddhist_system import (buddhist_config, set_dharma_karma, selected_blessings,
                                                    site_state, followers)
from cultivation_life.system.path_modifiers import modifier, adjusted_cost, commission_duration, pursuit_immunity
from cultivation_life.system.combat_system import PlayerCombatSystem, BattleUnit, STAT_KEYS
from cultivation_life.system.faction_geography import local_authorities, authority_permission_exempt


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def setup(tmp_path):
    engine = GameEngine(ROOT, tmp_path / "saves")
    result = engine.create_game("照尘", "supreme_wood", "buddhist", seed=111)
    game = engine._load(result["id"])
    game.pending_event = None
    game.player.realm_index = 1
    game.player.layer = 1
    game.player.location_id = next(s.location_id for s in game.sects.values() if s.world=='human' and not s.extinct)
    game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
    art = copy.deepcopy(next(row for row in TECHNIQUE_CATALOG.values() if row.path == "buddhist"))
    learn_technique(game.player, art)
    add_item(game.player, "spirit_stone", 1_000_000)
    engine.store.save(game)
    return engine, game, art


def test_resource_projection_preserves_raw_and_other_paths(setup):
    engine, game, _ = setup
    player = game.player
    player.karma, player.sha_qi, player.fame = 120, 60, 20
    assert effective_karma(player) == effective_sha_qi(player) == 0
    assert effective_fame(player) == 200
    assert effective_karma(player, "dharma_assembly") == 120
    assert effective_sha_qi(player, "dharma_assembly") == 60
    shown = engine.present(game)["player"]
    assert shown["raw_karma"] == 120 and shown["raw_sha_qi"] == 60
    saved = GameState.from_dict(game.to_dict())
    assert (saved.player.karma, saved.player.sha_qi, saved.player.fame) == (120, 60, 20)
    player.path = "dao"
    assert effective_fame(player) == 20 and effective_sha_qi(player) == 60
    player.path = "demonic"
    assert effective_karma(player) == 0


@pytest.mark.parametrize("karma,multiplier", [(0, 1), (-25, 1.05), (-50, 1.1), (-100, 1.2), (100, 1)])
def test_uniform_six_stats_once_without_mutating_player(setup, karma, multiplier):
    _, game, _ = setup
    set_dharma_karma(game, karma)
    units = [BattleUnit("player", "照尘", "player", 100, 1, "buddhist")]
    before = game.player.to_dict()
    base = PlayerCombatSystem._aggregate_stats(units, player=game.player, terrain_tags=[])
    boosted = PlayerCombatSystem._aggregate_stats(units, player=game.player, terrain_tags=[], player_stat_multiplier=modifier(game, "combat_stats"))
    for key in STAT_KEYS:
        assert boosted[key] == pytest.approx(base[key] * multiplier)
    assert before == game.player.to_dict()


def test_companion_base_does_not_receive_negative_karma_bonus(setup):
    _, game, _ = setup
    units = [BattleUnit("player", "照尘", "player", 100, 1, "buddhist"), BattleUnit("friend", "友", "companion", 500, 2, "dao")]
    baseline = PlayerCombatSystem._aggregate_stats(units, player=game.player, terrain_tags=[])
    ally = PlayerCombatSystem._aggregate_stats(units[1:], terrain_tags=[])
    boosted = PlayerCombatSystem._aggregate_stats(units, player=game.player, terrain_tags=[], player_stat_multiplier=1.2)
    for key in STAT_KEYS:
        assert boosted[key] == pytest.approx(ally[key] + (baseline[key] - ally[key]) * 1.2)


def test_five_real_action_units_grace_and_restoration(setup):
    engine, game, _ = setup
    game.player.realm_index = 5
    unit = int(WORLD_SYSTEMS["time_units"]["5"])
    set_dharma_karma(game, -26)
    assert pursuit_immunity(game, "fame")
    assert not pursuit_immunity(game, "war")
    for _ in range(5 * unit - 1):
        game.player.age += 1
        engine._advance_buddhist_year(game)
    assert pursuit_immunity(game, "fame")
    engine._advance_buddhist_year(game)
    assert not pursuit_immunity(game, "fame")
    game.player.hostility["sect:wanmo"] = 100
    set_dharma_karma(game, -25)
    assert pursuit_immunity(game, "fame") and game.player.hostility["sect:wanmo"] == 100
    set_dharma_karma(game, -30)
    assert game.buddhist_state["grace_units"] == 5


def test_fame_immunity_blocks_new_bounty_but_keeps_existing(setup):
    engine, game, _ = setup
    game.player.fame = 10_000
    engine._maybe_wanted_encounter(game, random.Random(1))
    assert not game.player.hostility.get("world:human")
    game.player.hostility["sect:wanmo"] = 200
    engine._maybe_wanted_encounter(game, random.Random(2))
    assert game.player.hostility["sect:wanmo"] > 0 or game.pending_event is not None


def test_world_local_blessings_maximum_and_zero_clear(setup):
    engine, game, _ = setup
    set_dharma_karma(game, 50)
    engine.store.save(game)
    for key in ("market", "natal", "commission"):
        engine.buddhist_action(game.id, "blessing", blessing=key)
    with pytest.raises(ValueError, match="最多"):
        engine.buddhist_action(game.id, "blessing", blessing="stipend")
    game = engine._load(game.id)
    assert adjusted_cost(game, 101, "market") == 81
    assert adjusted_cost(game, 101, "natal") == 81
    assert commission_duration(game, 6) == 5
    game.player.world = "spirit"
    assert adjusted_cost(game, 101, "market") == 101
    game.player.world = "human"
    set_dharma_karma(game, 0)
    assert not selected_blessings(game)
    set_dharma_karma(game, 20)
    assert not selected_blessings(game)


def test_remote_followers_decay_to_temple_floor_without_remote_stipend(setup):
    engine, game, _ = setup
    remote = site_state(game.buddhist_state, "spirit", "hundred_races_city")
    remote.update(followers=100, temple=2)
    set_dharma_karma(game, 50)
    game.buddhist_state["worlds"]["spirit"]["blessings"] = ["stipend"]
    stones = engine._spirit_stones(game.player)
    for _ in range(20):
        engine._advance_buddhist_year(game)
    assert remote["followers"] == 80
    assert engine._spirit_stones(game.player) == stones
    assert game.buddhist_state["dharma_karma"] == 50


def test_annual_order_pays_upkeep_before_cash_and_cleanses(setup):
    engine, game, _ = setup
    site_state(game.buddhist_state, "human", game.player.location_id)["followers"] = 10
    set_dharma_karma(game, .01)
    game.buddhist_state["worlds"]["human"]["blessings"] = ["stipend", "karma_decay", "sha_decay"]
    game.player.karma = game.player.sha_qi = 100
    stones = engine._spirit_stones(game.player)
    engine._advance_buddhist_year(game)
    assert game.buddhist_state["dharma_karma"] < 0
    assert game.player.karma == game.player.sha_qi == 100
    assert engine._spirit_stones(game.player) == stones


def test_three_stages_saved_events_and_no_reroll(setup):
    engine, game, art = setup
    started_age = game.player.age
    view = engine.buddhist_action(game.id, "start", technique=art.id)
    saved = engine.store.load(game.id)
    original_rng = saved.rng_state
    original_event = copy.deepcopy(saved.pending_event)
    engine.get_game(game.id)
    assert engine.store.load(game.id).rng_state == original_rng
    assert engine.store.load(game.id).pending_event == original_event
    for stage in range(3):
        assert view["buddhist_system"]["assembly"]["stage"] == stage
        view = engine.choose(game.id, view["pending_event"]["choices"][0]["id"])
        if stage < 2:
            view = engine.buddhist_action(game.id, "continue")
    assert view["buddhist_system"]["assembly"] is None
    assert view["player"]["age"] == started_age + 3
    assert len(view["buddhist_system"]["history"]) == 1


def test_interrupted_long_unit_resumes_remaining_years(setup):
    engine, game, art = setup
    game.player.realm_index = 5
    engine.store.save(game)
    unit = int(WORLD_SYSTEMS["time_units"]["5"])
    with patch.object(engine, "_advance_world_year", return_value=False):
        view = engine.buddhist_action(game.id, "start", technique=art.id)
    assert view["buddhist_system"]["assembly"]["stage_years"] == 1
    with patch.object(engine, "_advance_world_year", return_value=True):
        view = engine.buddhist_action(game.id, "continue")
    assert view["player"]["age"] == game.player.age + unit
    assert view["pending_event"]["id"].startswith("EVT_DHARMA_")


@pytest.mark.parametrize("score,outcome", [(90,"大成"),(60,"成功"),(25,"平稳"),(-10,"失利")])
def test_four_outcomes_and_floor(setup, score, outcome):
    engine, game, _ = setup
    site = site_state(game.buddhist_state, "human", game.player.location_id)
    site.update(temple=2, followers=80)
    game.buddhist_state["assembly"] = {"score": score, "burden": 0, "world":"human", "location":game.player.location_id, "attendance":100}
    assert outcome in engine._finish_buddhist_assembly(game)
    assert site["followers"] >= 80


def test_assembly_negative_threshold_and_nonlethal_defeat(setup):
    engine, game, art = setup
    set_dharma_karma(game, -26)
    engine.store.save(game)
    with pytest.raises(ValueError, match="-25"):
        engine.buddhist_action(game.id, "start", technique=art.id)
    target = {"target_name":"问法者", "target_power":1e12, "target_realm_index":8, "target_layer":9, "combat_type":"cultivator"}
    result, _ = engine._combat(game, target, False, random.Random(2))
    assert result == "defeat" and game.player.alive and game.player.hp >= 1


def test_disabling_freezes_data_and_restores_saved_event(setup):
    engine, game, art = setup
    engine.buddhist_action(game.id, "start", technique=art.id)
    game = engine.store.load(game.id)
    before = copy.deepcopy(game.buddhist_state)
    pending = copy.deepcopy(game.pending_event)
    with patch.dict(buddhist_config(), enabled=False):
        game.player.age += 100
        engine._advance_buddhist_year(game)
        assert engine._public_buddhist(game) == {"available":False}
        assert game.buddhist_state == before
        assert modifier(game, "combat_stats") == 1
    game.pending_event = None
    engine.store.save(game)
    engine.buddhist_action(game.id, "continue")
    assert engine.store.load(game.id).pending_event == pending


def test_assembly_lock_allows_trial_medicine_and_return_after_disabled_travel(setup):
    engine, game, art = setup
    engine.buddhist_action(game.id, 'start', technique=art.id)
    engine.assert_buddhist_operation_allowed(game.id, 'use-item')
    with pytest.raises(ValueError, match='法会'):
        engine.assert_buddhist_operation_allowed(game.id, 'travel')
    away = engine.store.load(game.id)
    away.player.world = 'spirit'
    away.player.location_id = engine.maps.default_location('spirit')
    engine.store.save(away)
    engine.assert_buddhist_operation_allowed(game.id, 'travel')


def test_market_display_and_actual_charge_use_same_price(setup):
    engine, game, _ = setup
    set_dharma_karma(game, 50)
    game.buddhist_state["worlds"]["human"]["blessings"] = ["market"]
    engine._ensure_market(game, random.Random(12))
    base = copy.deepcopy(game.market_offers)
    view = engine._public_market(game)
    offer = view["offers"][0]
    original = next(row for row in base if row["id"] == offer["id"])
    assert offer["price"] == math.ceil(original["price"] * .8)
    assert game.market_offers == base
    stones = engine._spirit_stones(game.player)
    engine.store.save(game)
    engine.buy_market_offer(game.id, offer["id"])
    assert engine._spirit_stones(engine.store.load(game.id).player) == stones - offer["price"]


def test_black_market_bulk_uses_unit_discount(setup):
    engine, game, _ = setup
    set_dharma_karma(game, 50)
    game.buddhist_state["worlds"]["human"]["blessings"] = ["market"]
    row = next(row for row in __import__('cultivation_life.content_registry',fromlist=['MARKET_GOODS']).MARKET_GOODS if row.get('world','human')=='human' and row['kind']=='item' and not ITEM_CATALOG[row['content_id']].root_grant)
    game.auction_state = {"status":"black_market", "world":"human", "location_id":game.player.location_id, "black_market_results":[{"id":"test", "kind":"item", "content_id":row['content_id'], "name":"丹", "price":101}]}
    assert engine._public_auction(game)["black_market_results"][0]["price"] == 81
    stones = engine._spirit_stones(game.player)
    engine.store.save(game)
    engine.buy_black_market_item(game.id, 'test', 3)
    assert engine._spirit_stones(engine.store.load(game.id).player) == stones - 243


def test_local_authorities_and_membership_exemption(setup):
    _, game, _ = setup
    local = local_authorities(game, game.player.world, game.player.location_id)
    assert local
    authority = local[0]
    assert not authority_permission_exempt(game, authority)
    game.player.faction_id = authority.id
    assert authority_permission_exempt(game, authority)
    authority.extinct = True
    assert authority not in local_authorities(game, game.player.world, game.player.location_id)


@pytest.mark.parametrize("yin,destination", [(0,"spirit"),(100,"hell")])
def test_buddhist_human_routes_use_central_transition(setup, yin, destination):
    engine, game, _ = setup
    game.player.realm_index = 5
    game.player.qi_experience['yin'] = yin
    assert engine._ascension_destination('buddhist', game.player) == destination
    plan = engine._plan_world_transition(game, destination)
    engine._apply_world_transition(game, plan)
    assert game.player.world == destination and game.player.path == 'buddhist'


def test_hell_ascension_reuses_nine_trials_and_reincarnation_core(setup):
    engine, game, _ = setup
    game.player.world='hell'; game.player.location_id=engine.maps.default_location('hell')
    game.player.realm_index=8;game.player.layer=9;game.player.opportunity=opportunity_required(game.player)
    game.player.hp=max_hp(game.player);game.player.mp=max_mp(game.player)
    engine.store.save(game)
    view=engine.begin_celestial_ascension(game.id)
    saved=engine.store.load(game.id)
    assert saved.active_trial['destination']=='reincarnation' and len(saved.active_trial['event_ids'])==9
    plan=engine._plan_world_transition(saved,'reincarnation')
    engine._apply_world_transition(saved,plan)
    assert saved.player.path=='buddhist' and saved.player.world=='reincarnation'


@pytest.mark.parametrize('book,world', [('yaoque_water','monster_realm'),('yaoque_wind','phantom_underworld'),('mingque_water','hell'),('moque_thunder','true_demon'),('zique_water','spirit')])
def test_root_completion_books_are_actionable_and_consume_once(setup, book, world):
    engine,game,_=setup
    game.player.world=world;game.player.location_id=engine.maps.default_location(world);game.player.realm_index=5
    add_item(game.player,book,2);engine.store.save(game)
    item=next(row for row in engine.present(game)['player']['inventory'] if row['id']==book)
    assert item['root_grant']
    engine.use_item(game.id,book)
    saved=engine.store.load(game.id)
    assert ITEM_CATALOG[book].root_grant in saved.player.additional_roots and has_item(saved.player,book,1)
    with pytest.raises(ValueError,match='已经拥有'):
        engine.use_item(game.id,book)
    assert has_item(engine.store.load(game.id).player,book,1)


def test_dead_master_does_not_block_events_or_faction_request(setup):
    engine,game,_=setup
    game.player.master={'id':'deceased','name':'故师','alive':False}
    assert not has_living_master(game.player)
    assert engine._condition({'path':'player.has_master','op':'eq','value':False},game)
    sect=next(row for row in game.sects.values() if row.world=='human' and not row.extinct and any(n.alive and n.realm_index>1 for n in row.npcs))
    game.player.faction_id=sect.id
    npc=next(n for n in sect.npcs if n.alive and n.realm_index>1)
    engine.store.save(game)
    # Both accepted and rejected requests are legitimate; the obsolete "already has master" guard must not fire.
    engine.manage_faction_relationship(game.id,npc.id,'master')
    saved=engine.store.load(game.id)
    assert f'master:{npc.id}' in saved.player.relationship_attempts


def test_invalid_dlc_config_is_rejected():
    from cultivation_life.buddhist_content import validate_buddhist_content
    bad=copy.deepcopy(CONTENT_DOCUMENTS['buddhist_way.json'])
    bad['settings']['temples'][3]['decay']=0
    with pytest.raises(ValueError):validate_buddhist_content(bad,CONTENT_DOCUMENTS)


def test_natal_single_and_bulk_quote_match_discounted_charge(setup):
    engine, game, _ = setup
    game.player.realm_index = 3
    add_item(game.player, 'starfall_blade')
    set_dharma_karma(game, 50)
    game.buddhist_state['worlds']['human']['blessings'] = ['natal']
    engine.store.save(game)
    shown = engine.natal_artifact_action(game.id, 'bind', 'starfall_blade')
    assert shown['natal_artifact']['refine_cost'] == math.ceil(380 * .8)
    for action in ['refine', 'refine_all']:
        before = engine._load(game.id)
        view = engine.present(before)['natal_artifact']
        cost = view['refine_cost' if action == 'refine' else 'refine_all_cost']
        stones = engine._spirit_stones(before.player)
        engine.natal_artifact_action(game.id, action)
        after = engine._load(game.id)
        assert engine._spirit_stones(after.player) == stones - cost


def test_actual_upper_ascension_completion_and_path_survival(setup):
    engine, game, _ = setup
    for world, destination in [('hell', 'reincarnation'), ('spirit', 'celestial')]:
        run = copy.deepcopy(game)
        run.player.world = world
        run.player.location_id = engine.maps.default_location(world)
        run.player.realm_index = 8; run.player.layer = 9
        run.player.hp = max_hp(run.player); run.player.mp = max_mp(run.player)
        run.active_trial = {'step_index': 8, 'event_ids': list(range(9)), 'destination': destination}
        outcome, _ = engine._resolve_celestial_ascension_step(run, 'ascension_thunder_3', random.Random(1))
        assert outcome == 'trial_completed' and run.player.world == destination
        assert run.player.path == 'buddhist' and run.player.realm_index == 9


def test_wrong_world_book_rejection_does_not_consume(setup):
    engine, game, _ = setup
    game.player.realm_index = 5
    add_item(game.player, 'yaoque_water')
    engine.store.save(game)
    with pytest.raises(ValueError, match='妖阙'):
        engine.use_item(game.id, 'yaoque_water')
    assert has_item(engine.store.load(game.id).player, 'yaoque_water')


def test_living_master_still_prevents_duplicate_mentorship(setup):
    engine, game, _ = setup
    game.player.master = {'id': 'living', 'name': '师父', 'alive': True}
    assert has_living_master(game.player)
    assert engine._condition({'path': 'player.has_master', 'op': 'eq', 'value': True}, game)


def test_permissions_are_per_authority_and_persist_across_reload(setup):
    engine, game, _ = setup
    first = local_authorities(game, 'human', game.player.location_id)[0]
    second = next(row for row in game.sects.values() if row.world == 'human' and row.id != first.id and not row.extinct)
    second.location_id = first.location_id
    second.player_founded_site = True
    engine.store.save(game)
    view = engine.buddhist_action(game.id, 'permission', authority=first.id)['buddhist_system']
    rows = {row['id']: row for row in view['permissions']}
    assert rows[first.id]['permitted'] and not rows[second.id]['permitted']
    assert engine.get_game(game.id)['buddhist_system']['permissions'] == view['permissions']


def test_temple_payment_changes_current_site_only(setup):
    engine, game, _ = setup
    stones = engine._spirit_stones(game.player)
    cost = engine._public_buddhist(game)['temple_cost']
    engine.buddhist_action(game.id, 'temple')
    saved = engine.store.load(game.id)
    site = site_state(saved.buddhist_state, 'human', saved.player.location_id)
    assert site['temple'] == 1 and site['followers'] == 20
    assert engine._spirit_stones(saved.player) == stones - cost


def test_unlicensed_purge_stops_at_temple_floor_and_can_issue_wanted(setup):
    engine, game, _ = setup
    local = local_authorities(game, 'human', game.player.location_id)[0]
    site = site_state(game.buddhist_state, 'human', game.player.location_id)
    site.update(temple=2, followers=1000)
    game.buddhist_state['assembly'] = {'score':90, 'burden':0, 'world':'human', 'location':game.player.location_id, 'attendance':100}
    class PurgeRoll:
        def random(self): return 0
    result = engine._finish_buddhist_assembly(game, rng=PurgeRoll())
    assert site['followers'] == 80
    assert game.player.hostility[f'sect:{local.id}'] > WORLD_SYSTEMS['faction_conflict']['wanted_threshold']
    assert '驱散' in result


def test_merchant_quotes_and_boards_share_duration_modifier(setup):
    engine, game, _ = setup
    view = engine._public_merchant(game)
    alliance = game.merchant_state['worlds']['human'][0]
    baseline = engine._merchant_board(game, alliance)
    normal_quote = engine._merchant_quote(game, alliance, {'kind':'intel', 'stars':3})
    set_dharma_karma(game, 50)
    game.buddhist_state['worlds']['human']['blessings'] = ['commission']
    faster = engine._merchant_board(game, alliance)
    for original, accelerated in zip(baseline, faster):
        assert accelerated['years'] == math.ceil(original['years'] * .8)
    quote = engine._merchant_quote(game, alliance, {'kind':'intel', 'stars':3})
    assert quote['years'] == math.ceil(normal_quote['years'] * .8)
    engine._merchant_post(game, alliance, {'kind':'intel', 'stars':3, 'preview_token':quote['preview_token']})
    assert game.merchant_state['posted'][-1]['years'] == quote['years']


def test_buddhist_dlc_runs_without_other_optional_packages(tmp_path):
    import json
    import subprocess
    import sys
    preferences = {path.parent.name: path for path in (ROOT/'dlc').glob('*/manifest.json')}
    # Fresh process selects only this DLC; no registry globals leak to other tests.
    package_root = tmp_path/'packages'
    import shutil
    shutil.copytree(ROOT/'dlc/buddhist-dharma', package_root/'dlc/buddhist-dharma')
    code = '''
from cultivation_life.content_registry import ContentRegistry
from pathlib import Path
import sys
registry=ContentRegistry.load(Path(sys.argv[1])/'content', Path(sys.argv[2]))
assert [r['id'] for r in ContentRegistry.extension_report if r['status']=='loaded']==['official.buddhist-dharma']
assert 'buddhist_way.json' in ContentRegistry.loaded_documents
assert registry.world_systems['world_profiles']['reincarnation']['enabled']
assert next(r for r in registry.world_systems['world_transition_routes'] if r['id']=='progression:hell:reincarnation')['enabled']
'''
    subprocess.run([sys.executable, '-c', code, str(ROOT), str(package_root)], check=True)
