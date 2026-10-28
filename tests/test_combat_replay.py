"""Truthful, bounded ordinary-combat replay facts, without new settlement."""
import copy
import hashlib
import json
import random
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from cultivation_life.combat_visuals import beast_kind, combat_identity, report_visuals
from cultivation_life.engine import GameEngine
from cultivation_life.engine import engine_combat_runtime

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def engine(tmp_path_factory):
    return GameEngine(ROOT, tmp_path_factory.mktemp('combat-replay') / 'saves')


def fight(engine, *, ratio=.9, seed=42):
    made = engine.create_game('观战者', 'heavenly', 'dao', seed, preset_id='core')
    game = engine.store.load(made['id'])
    target = dict(target_name='青翎灵鹫', target_power=engine._player_battle_power(game)*ratio,
                  target_realm_index=game.player.realm_index, combat_type='beast', action='hunt_beast')
    rng = random.Random(seed)
    engine._combat(game, target, False, rng)
    return game, target, rng


@pytest.mark.parametrize('ratio', [.2, .9, 4])
def test_reports_capture_real_initial_loss_and_end(engine, ratio):
    game, target, rng = fight(engine, ratio=ratio)
    report = game.last_combat_report
    assert report['visual']['enemy'] == 'hunt-jade-eagle'
    before = copy.deepcopy(game.to_dict())
    state = rng.getstate()
    assert report_visuals(game, target, report) == report['visual']
    assert game.to_dict() == before and rng.getstate() == state
    assert len(json.dumps(report['visual'])) < 512
    previous = None
    for row in report['rounds']:
        facts = row['ordinary_exchange']
        if previous is not None:
            assert facts['opening'] == previous
        for index, side in enumerate(['player', 'enemy']):
            assert 0 <= facts['after'][index] <= facts['before'][index] <= row[f'{side}_combat_state_max']
        previous = [row['player_combat_state'], row['enemy_combat_state']]
    assert previous == [report['player_combat_state'], report['enemy_combat_state']]


def test_visual_metadata_does_not_change_rng_outcomes_or_resources(engine):
    made = engine.create_game('只读回放', 'heavenly', 'dao', 721, preset_id='core')
    original = engine.store.load(made['id'])
    a, b = copy.deepcopy(original), copy.deepcopy(original)
    target = dict(target_name='刀螳', target_power=engine._player_battle_power(a)*.8,
                  target_realm_index=a.player.realm_index, combat_type='beast')
    ra, rb = random.Random(119), random.Random(119)
    result_a = engine._combat(a, copy.deepcopy(target), False, ra)
    with patch.object(engine_combat_runtime, 'report_visuals', return_value=None):
        result_b = engine._combat(b, copy.deepcopy(target), False, rb)
    a.last_combat_report.pop('visual')
    assert result_a == result_b and ra.getstate() == rb.getstate()
    assert a.to_dict() == b.to_dict()


def test_only_field_stages_are_excluded_not_mixed_battles(engine):
    game, target, _ = fight(engine)
    report = copy.deepcopy(game.last_combat_report)
    report['rounds'][0]['voisinage'] = {}
    assert report_visuals(game, target, report)['enemy'] == 'hunt-jade-eagle'
    for row in report['rounds']:
        row.pop('ordinary_exchange', None)
        row['initiative'] = 'voisinage'
    assert report_visuals(game, target, report) is None
    report = game.last_combat_report
    game.player.path = 'ghost'
    assert report_visuals(game, target, report)['hero'] == 'ghost-hero-male'
    game.player.path = 'dao'
    game.player.ghost_host_body = {'name': '宿身'}
    assert report_visuals(game, target, report)['hero'] == 'dao-male'


@pytest.mark.parametrize('path', ['dao', 'demonic', 'buddhist', 'confucian', 'ghost', 'monster', 'asura'])
@pytest.mark.parametrize('gender', ['male', 'female'])
def test_all_paths_have_gender_matched_fallback_without_rng(engine, path, gender):
    game, target, rng = fight(engine)
    game.player.path, game.player.gender = path, gender
    target = dict(target_name='匿名对手', combat_type='cultivator', path=path, gender=gender)
    before, random_state = copy.deepcopy(game.to_dict()), rng.getstate()
    with patch('cultivation_life.content_registry.EXTENSION_REPORT', []):
        visual = report_visuals(game, target, game.last_combat_report)
    faction = 'demonic' if path == 'demonic' else 'dao'
    assert visual['hero'] == f'{faction}-{gender}'
    assert visual['enemy'].startswith(faction+'-') and visual['enemy'].endswith('-m' if gender == 'male' else '-f')
    assert before == game.to_dict() and random_state == rng.getstate()


def test_primary_and_cached_identity_take_precedence_over_proxy_defaults(engine):
    game, _, _ = fight(engine)
    game.encounter_npc_cache = [dict(id='cached-caster', npc=dict(path='demonic', gender='female'))]
    target = dict(npc_id='cached-caster', path='dao', gender='male')
    assert combat_identity(game, target)['enemy'].startswith('demonic-')
    assert combat_identity(game, target)['enemy'].endswith('-f')
    game.encounter_npc_cache = []
    target = dict(members=[dict(path='demonic', gender='female')])
    assert combat_identity(game, target)['enemy'].startswith('demonic-')
    assert combat_identity(game, target)['enemy'].endswith('-f')


def test_visual_identity_snapshot_survives_host_loss(engine):
    game, target, _ = fight(engine)
    game.player.ghost_host_body = dict(name='女宿身', path='demonic', gender='female')
    identity = combat_identity(game, target)
    game.player.ghost_host_body = None
    assert report_visuals(game, target, game.last_combat_report, identity=identity)['hero'] == 'demonic-female'


def test_actual_mixed_rounds_capture_only_ordinary_loss():
    from test_domain_combat import fight as field_fight, capability
    result, _ = field_fight(capability(), capability(), rounds=3)
    assert result.rounds and all(row.get('ordinary_exchange') for row in result.rounds)
    for row in result.rounds:
        exchange = row['ordinary_exchange']
        assert exchange['actors'] == {'player': True, 'enemy': True}
        for i in range(2):
            assert 0 <= exchange['after'][i] <= exchange['before'][i]
        assert row['voisinage']


def test_field_only_opening_then_ordinary_stages_remain_replayable(engine):
    from test_domain_combat import fight as field_fight, capability, voisinage
    from cultivation_life.system.combat.contracts import CombatCapabilities
    resolution, _ = field_fight(capability(definition=voisinage(effect='strike',effect_power=.03),current=200),
                                CombatCapabilities(),rounds=8)
    first, following = resolution.rounds[0], resolution.rounds[1]
    assert first['initiative'] == 'voisinage' and 'ordinary_exchange' not in first
    assert following['ordinary_exchange']['opening'][1] == first['enemy_combat_state']
    assert following['ordinary_exchange']['opening'][1] < first['enemy_combat_state_max']
    game, target, _ = fight(engine)
    assert report_visuals(game,target,resolution.to_dict())['enemy'] == 'hunt-jade-eagle'


def test_trial_rows_capture_ordinary_and_domain_stages():
    from scripts.calibrate_immortal_trials import fixture
    from cultivation_life.engine.progression.immortal_trials import initialize
    from cultivation_life.system.combat.trials import run_batch
    for kind in ('human_decline', 'voisinage_backlash'):
        game = fixture(kind, field_rank=4, temper=10, stance='guard', investment=40)
        battle = initialize(game, game.active_trial)
        _, rows = run_batch(battle, game.active_trial['battle_state'], random.Random(1))
        if kind == 'voisinage_backlash':
            assert all('ordinary_exchange' not in row for row in rows)
            assert report_visuals(game, game.active_trial['target'], dict(rounds=rows))['domains']
        else:
            assert any(row.get('ordinary_exchange') for row in rows)
            assert report_visuals(game, game.active_trial['target'], dict(rounds=rows))


def test_beast_categories_match_actual_hunt_names():
    assert beast_kind('裂岩妖狼') == 'quadruped'
    assert beast_kind('青翎灵鹫') == 'avian'
    assert beast_kind('碧甲刀螳') == 'insect'


def test_actual_neighborhood_resolution_does_not_create_animation_exchanges():
    from test_domain_combat import fight as field_fight, capability
    from cultivation_life.system.combat.contracts import CombatCapabilities
    result, _ = field_fight(capability(), CombatCapabilities(), enemy_power=1_000_000)
    assert result.rounds and all('ordinary_exchange' not in row for row in result.rounds)


def test_known_npc_visual_identity_uses_real_gender_and_path(engine):
    game, target, _ = fight(engine)
    npc = next(iter(game.world_npcs.values()))
    npc.race, npc.path, npc.gender = 'human', 'demonic', 'female'
    target = dict(npc_id=npc.id, combat_type='cultivator', target_name=npc.name)
    visual = report_visuals(game, target, game.last_combat_report)
    assert visual['enemy'].startswith('demonic-') and visual['enemy'].endswith('-f')


def test_runtime_atlases_are_local_reviewed_bounded_and_hash_verified():
    root = ROOT / 'web/assets/pixel/combat'
    data = json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    assert len(data['actors']) == 24 and data['requires'] == []
    assert not any(path.suffix.lower() == '.gif' for path in root.iterdir())
    groups = {}
    for identity, actor in data['actors'].items():
        defeat = actor['animations']['defeat']
        assert defeat['facing'] == (1 if identity.startswith(('companion-', 'corpse-', 'mechanical-')) else -1)
        assert defeat['cell'] == [384, 288]
        assert defeat['poses'][-1]['pose'] == 'defeat'
        for group in actor['animations'].values():
            groups[group['sheet']] = group
            assert len(group['rects']) == group['frames'] == len(group['poses'])
            for x, y, w, h, dx, dy in group['rects']:
                assert x >= 0 and y >= 0 and dx >= 0 and dy >= 0
                assert x+w <= group['size'][0] and y+h <= group['size'][1]
    for url, group in groups.items():
        assert url.startswith('/assets/pixel/combat/')
        path = ROOT/'web'/url.lstrip('/')
        assert hashlib.sha256(path.read_bytes()).hexdigest() == group['sha256']
        with Image.open(path) as image:
            assert list(image.size) == group['size']
    # Current actors only, not every figure in the roster at once.
    hero = data['actors']['demonic-female']['animations']
    for enemy in ['avian', 'quadruped', 'insect', 'dao-1-m', 'demonic-1-f']:
        active = {g['sheet']:g for g in [*hero.values(), *data['actors'][enemy]['animations'].values()]}
        assert sum(g['size'][0]*g['size'][1]*4 for g in active.values()) < 64*1024*1024


@pytest.mark.parametrize('path', ['dao', 'demonic', 'buddhist'])
@pytest.mark.parametrize('gender', ['male', 'female'])
def test_six_participants_prefer_distinct_legal_portraits_then_reuse(engine, path, gender):
    from cultivation_life.combat_visuals import _human_assets
    from cultivation_life.system.combat_system import BattleUnit
    game, _, _ = fight(engine)
    units = [BattleUnit(f'ally-{i}', f'同行{i}', 'companion', 10, 1, path) for i in range(3)]
    game.player.party = [dict(id=u.id, gender=gender, path=path) for u in units]
    members = [dict(npc_id=f'foe-{i}', name=f'对手{i}', power=10, path=path, gender=gender) for i in range(3)]
    with patch('cultivation_life.content_registry.EXTENSION_REPORT', []):
        visual = combat_identity(game, dict(members=members), player_units=units)
    assert visual['schema_version'] == 2 and len(json.dumps(visual)) < 4096
    used = set()
    for side in ('hero', 'npc'):
        for i, row in enumerate(visual['teams'][side]):
            key = units[i].id if side == 'hero' else members[i]['npc_id']
            legal = _human_assets(path, gender, key, companion=side == 'hero')
            unused = set(legal) - used
            assert row['asset'] in legal and row['gender'] == gender
            if unused:
                assert row['asset'] not in used
            used.add(row['asset'])
    assert len(used) == (3 if path == 'demonic' else 4)


def test_corpse_and_living_use_authoritative_source_sex_not_mutable_proxy(engine):
    from cultivation_life.system.combat_system import BattleUnit
    game, _, _ = fight(engine)
    npc = next(iter(game.world_npcs.values()))
    npc.gender, npc.path = 'female', 'dao'
    game.player.puppets = [dict(id='corpse-one', type='corpse', source_npc_id=npc.id, gender='male'),
                           dict(id='living-one', type='living', source_npc_id=npc.id, gender='male')]
    units = [BattleUnit('player', game.player.name, 'player', 10, 1),
             BattleUnit('corpse-one', '炼尸', 'corpse', 10, 1),
             BattleUnit('living-one', '活傀', 'living', 10, 1)]
    before = copy.deepcopy(game.to_dict())
    result = combat_identity(game, dict(target_name='对手'), player_units=units)
    team = result['teams']['hero']
    assert team[1]['asset'] == 'corpse-female' and team[1]['gender'] == 'female'
    assert team[2]['asset'] == 'companion-female' and team[2]['gender'] == 'female'
    assert game.to_dict() == before


def test_mechanical_and_beasts_never_borrow_human_portraits_to_avoid_duplicates(engine):
    from cultivation_life.system.combat_system import BattleUnit
    game, _, _ = fight(engine)
    units = [BattleUnit(f'gear-{i}', f'机关{i}', 'mechanical', 10, 1) for i in range(3)]
    members = [dict(name='裂岩妖狼', kind='beast', power=10), dict(name='青翎灵鹫', kind='beast', power=10),
               dict(name='碧甲刀螳', kind='beast', power=10)]
    result = combat_identity(game, dict(members=members), player_units=units)
    assert [row['asset'] for row in result['teams']['hero']] == ['mechanical-puppet'] * 3
    assert {row['asset'] for row in result['teams']['npc']} == {'hunt-rock-wolf', 'hunt-jade-eagle', 'hunt-jade-mantis'}
    assert all(row['gender'] is None for team in result['teams'].values() for row in team)


def test_snapshot_uses_actual_deployment_caps_only_display_and_survives_changes(engine):
    from cultivation_life.system.combat_system import BattleUnit
    game, target, _ = fight(engine)
    units = [BattleUnit('player', game.player.name, 'player', 10, 1)]
    units += [BattleUnit(f'gear-{i}', f'机关{i}', 'mechanical', 10, 1) for i in range(5)]
    units.insert(1, BattleUnit('broken', '损坏机关', 'mechanical', 0, 1, integrity=0))
    snapshot = combat_identity(game, target, player_units=units)
    assert len(snapshot['teams']['hero']) == 3 and snapshot['team_counts']['hero'] == 6
    assert all(row['id'] != 'broken' for row in snapshot['teams']['hero'])
    game.player.gender = 'female'
    game.player.puppets.clear()
    assert report_visuals(game, target, game.last_combat_report, identity=snapshot) is snapshot


def test_six_actor_upper_decode_bound_counts_shared_sheets_only_once():
    data = json.loads((ROOT/'web/assets/pixel/combat/manifest.json').read_text(encoding='utf-8'))
    def size(item):
        groups = {group['sheet']: group for group in item['animations'].values()}
        return sum(group['size'][0]*group['size'][1]*4 for group in groups.values())
    npcs = sorted([size(actor) for actor in data['actors'].values() if actor['role'] == 'npc'], reverse=True)
    hero = max(size(actor) for actor in data['actors'].values() if actor['role'] == 'hero')
    # Conservative: even includes both teams' defeat sheets and all hero moves.
    assert hero + sum(npcs[:5]) < 96*1024*1024


def test_trial_summary_roster_without_unit_ids_retains_the_real_player(engine):
    game, target, _ = fight(engine)
    report = copy.deepcopy(game.last_combat_report)
    report['player_roster'] = [dict(name=game.player.name, power=100, kind_name='玩家')]
    visual = report_visuals(game, target, report)
    assert visual['teams']['hero'][0]['id'] == 'player'
    assert visual['teams']['hero'][0]['asset'] == visual['hero']


def test_multiunit_metadata_does_not_change_settlement_or_random_state(engine):
    made = engine.create_game('群战只读', 'heavenly', 'dao', 916, preset_id='core')
    original = engine.store.load(made['id'])
    power = engine._player_battle_power(original)
    original.player.puppets = [dict(id=f'guard-{i}', name=f'机关{i}', type='mechanical',
        alive=True, durability=100, combat_power=power*.2, realm_index=original.player.realm_index) for i in range(2)]
    a,b = copy.deepcopy(original), copy.deepcopy(original)
    target = dict(target_name='联合验收', target_power=power*1.3, target_realm_index=original.player.realm_index,
        members=[dict(npc_id=f'enemy-{i}', name=f'敌方{i}', power=power/3, gender='female', path='dao') for i in range(3)])
    ra,rb = random.Random(51),random.Random(51)
    first = engine._combat(a,copy.deepcopy(target),False,ra)
    with patch.object(engine_combat_runtime, 'report_visuals', return_value=None):
        second = engine._combat(b,copy.deepcopy(target),False,rb)
    assert len(a.last_combat_report['visual']['teams']['hero']) == 3
    a.last_combat_report.pop('visual')
    assert first == second and ra.getstate() == rb.getstate() and a.to_dict() == b.to_dict()


def test_battlefield_catalog_separates_duels_and_groups_and_preserves_open_scene():
    root = ROOT/'web/assets/pixel/combat'
    data = json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    assert set(data['battlefields']) == {'single','group'}
    urls = set()
    for mode, rows in data['battlefields'].items():
        assert set(rows) == {'开阔','狭窄','险要'}
        for name, scene in rows.items():
            assert scene['mode']==mode and scene['name']==name and scene['requires']==[]
            path = ROOT/'web'/scene['file'].lstrip('/')
            assert hashlib.sha256(path.read_bytes()).hexdigest() == scene['sha256']
            with Image.open(path) as image:
                assert list(image.size) == scene['size']
            assert scene['file'] not in urls
            urls.add(scene['file'])
    opened = data['battlefields']['single']['开阔']
    assert opened['file'] == data['terrace']
    assert opened['sha256'] == '87e129336dc44e789fbab6a975d59f729ccd27d5d27d5e100668cdfb55ac7a1c'


def test_all_painted_defeat_poses_use_explicit_body_scale_not_canvas_fit():
    import math
    from PIL import Image
    from scripts.prepare_combat_assets import normalize_fall
    root = ROOT/'web/assets/pixel/combat'
    data = json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    path = ROOT/'scripts/combat_asset_scale.json'
    recipe = json.loads(path.read_text(encoding='utf-8'))
    assert data['scale_contract']['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert set(data['actors']) == set(recipe['actors'])
    for identity, actor in data['actors'].items():
        ref = actor['scale_reference']
        assert ref['standing_height'] == (None if actor.get('creature') else 176)
        if not actor.get('creature') and not identity.startswith(('companion-', 'corpse-', 'mechanical-')):
            # Existing normal standing figures are already calibrated. Do not
            # turn the genuinely crouched support stances into standing bodies.
            assert abs(actor['animations']['idle']['rects'][0][3]-176) <= 1
        clip = actor['animations']['defeat']
        assert len(clip['scale_calibration']) == clip['frames']
        for pose, calibration in zip(clip['poses'], clip['scale_calibration']):
            assert .5 <= calibration['scale'] <= 1.2
            assert math.isclose(calibration['painted_head']*calibration['scale'], ref['reference_head'])
            if pose['pose'] != 'defeat':
                assert calibration['scale'] == 1
        # Different postures/crops of the same painted stage receive exactly
        # the same scale; no bbox-dependent breathing/pumping of the whole body.
        stages = {}
        for pose, calibration in zip(clip['poses'], clip['scale_calibration']):
            stage = (pose['pose'], pose.get('stage', 0))
            assert stages.setdefault(stage, calibration['scale']) == calibration['scale']
    first, second = Image.new('RGBA', (384,288)), Image.new('RGBA', (384,288))
    first.paste('#abcdef', (80,120,280,256))
    second.paste('#abcdef', (100,210,220,256))
    poses = [dict(pose='defeat', anchor=[192,256], stage=3)]*2
    images, records = normalize_fall('dao-male', [first,second], poses)
    assert records[0]['scale'] == records[1]['scale'] == .75
    assert [im.getbbox()[3] for im in images] == [256,256]
    assert [im.getbbox()[2]-im.getbbox()[0] for im in images] == [150,90]
