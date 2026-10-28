"""Historical costume gates and same-save, actual-kill achievement evidence."""
import copy
import hashlib
import json
import random
from pathlib import Path

import pytest
from PIL import Image
from cultivation_life import character_skins as skins
from cultivation_life.achievement_kills import KEY, EVENT, record
from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState, Player, SectNpc
from cultivation_life.world_state import race_pair

ROOT = Path(__file__).resolve().parents[1]
REWARDS = {'nobunaga-male': 'politics_world_unification',
           'seimei-male': 'ghost_hundred_non_ghost_kills'}


@pytest.mark.parametrize('path', ['dao', 'demonic', 'monster', 'ghost', 'buddhist', 'confucian'])
@pytest.mark.parametrize('skin,achievement', REWARDS.items())
def test_independent_global_gates_all_male_paths_no_realm_requirement(path, skin, achievement):
    p = Player('风雅', 'none', gender='male', path=path, realm_index=12)
    key = 'actor.cosmetic.' + skin
    with pytest.raises(ValueError): skins.choose(p, key)
    skins.unlock_achievement_rewards(p, {'ghost_story_first_parade': {}})
    with pytest.raises(ValueError): skins.choose(p, key)
    p.realm_index = 0
    before = p.to_dict()
    skins.unlock_achievement_rewards(p, {achievement: {}})
    skins.choose(p, key)
    assert skins.appearance(p)['combat'] == skin
    other = next(s for s in REWARDS if s != skin)
    with pytest.raises(ValueError): skins.choose(p, 'actor.cosmetic.' + other)
    after = p.to_dict()
    before.pop('character_skins'); after.pop('character_skins')
    assert after == before
    restored = Player.from_dict(p.to_dict())
    assert skins.appearance(restored) == skins.appearance(p)
    female = Player('风雅', 'none', gender='female')
    skins.unlock_achievement_rewards(female, {achievement: {}})
    with pytest.raises(ValueError): skins.choose(female, key)


def state():
    return GameState('same-save', 1, Player('百鬼', 'none', path='ghost'), '', '')


@pytest.mark.parametrize('invalid', ['other_player_path', 'ghost_victim', 'unknown_path', 'mortal', 'commission', 'mechanical', 'beast'])
def test_only_qualifying_kills_are_recorded(invalid):
    g = state()
    victim = dict(npc_id='one', path='dao', realm_index=1)
    if invalid == 'other_player_path': g.player.path = 'dao'
    elif invalid == 'ghost_victim': victim['path'] = 'ghost'
    elif invalid == 'unknown_path': victim.pop('path')
    elif invalid == 'mortal': victim['realm_index'] = 0
    elif invalid == 'commission': victim['actor'] = 'commission'
    else: victim['kind'] = invalid
    before = copy.deepcopy(g.to_dict())
    record(g, victim)
    assert g.to_dict() == before


def test_original_identity_wins_and_progress_is_bounded_and_persistent():
    g = state()
    g.world_npcs['ghost'] = SectNpc('ghost', '鬼修', '', 2, 1, 30, 200, path='ghost')
    record(g, dict(npc_id='ghost', path='dao', realm_index=2))
    assert KEY not in g.player.milestones
    for i in range(99): record(g, dict(npc_id=f'victim-{i}', path='dao', realm_index=1))
    g = GameState.from_dict(g.to_dict())
    record(g, dict(npc_id='victim-0', path='dao', realm_index=1))
    assert g.player.milestones[KEY] == 99
    g.player.path = 'dao'
    record(g, dict(npc_id='outside-ghost', path='dao', realm_index=1))
    assert g.player.milestones[KEY] == 99
    g.player.path = 'ghost'
    record(g, dict(npc_id='hundredth', path='demonic', realm_index=1))
    record(g, dict(npc_id='overflow', path='dao', realm_index=1))
    assert g.player.milestones[KEY] == 100
    assert len([r for r in g.history if r.event_id == EVENT]) == 100
    assert KEY not in state().player.milestones


def seed_kills(engine, game, count):
    # Invoke the shared real settlement; no fabricated achievement ledger.
    for i in range(count):
        npc = SectNpc(f'kill-{i}', '对手', '', 1, 1, 20, 100, path='dao')
        game.notable_npcs[npc.id] = npc
        engine._apply_cultivator_kill(game, dict(npc_id=npc.id, name=npc.name,
            realm_index=1, path='dao', race='human'), random.Random(i))
        assert not npc.alive


def test_hundredth_real_command_unlocks_and_new_save_inherits_reward_only(tmp_path):
    engine = GameEngine(ROOT, tmp_path)
    made = engine.create_game('鬼行', 'supreme_metal', 'ghost', 328, gender='male')
    g = engine._load(made['id'])
    g.pending_event = g.active_trial = None
    seed_kills(engine, g, 99)
    engine.store.save(g)
    assert 'ghost_hundred_non_ghost_kills' not in {r['id'] for r in engine.achievements.evaluate(g)}
    # The final actual captive execution goes through loading, validation and save.
    held = g.detain_person(dict(id='final', name='最后一人', realm_index=1, layer=1,
        age=20, lifespan=100, path='dao', world=g.player.world))
    g.player.prisoners.append(held)
    engine.store.save(g)
    result = engine.relationship_violence(g.id, 'captive', 'final')
    key = 'actor.cosmetic.seimei-male'
    assert engine.store.load(g.id).player.milestones[KEY] == 100
    assert key in {r['id'] for r in result['player']['character_skins']['available']}
    assert 'ghost_hundred_non_ghost_kills' in engine.achievements.metadata.read()['achievements']
    assert engine.select_character_skin(g.id, key)['player']['visual_actor'] == key
    with pytest.raises(ValueError): engine.relationship_violence(g.id, 'captive', 'final')
    assert engine.store.load(g.id).player.milestones[KEY] == 100
    assert engine.get_game(g.id)['player']['visual_actor'] == key
    new = engine.create_game('来世', 'none', 'dao', 329, gender='male')
    assert key in {r['id'] for r in new['player']['character_skins']['available']}
    assert KEY not in engine.store.load(new['id']).player.milestones


def test_unification_earns_nobunaga_on_existing_ledger(tmp_path):
    e = GameEngine(ROOT, tmp_path)
    g = e._load(e.create_game('天下', 'none', 'dao', 330, gender='male')['id'])
    sects = [s for s in g.sects.values() if s.kind == 'sect' and not s.extinct and s.world == g.player.world]
    own = sects[0]; g.player.faction_id = own.id
    for other in sects[1:]:
        g.sect_relations[race_pair(own.id, other.id)] = dict(status='vassal', overlord=own.id, subject=other.id)
    assert 'politics_world_unification' in {r['id'] for r in e.achievements.evaluate(g)}
    e.store.save(g)
    assert 'actor.cosmetic.nobunaga-male' in {r['id'] for r in e.get_game(g.id)['player']['character_skins']['available']}


def test_combat_outcomes_count_actual_kills_not_captures_or_escaped_souls(tmp_path):
    from cultivation_life.engine.engine_combat_runtime import _settle_combat_kill
    e = GameEngine(ROOT, tmp_path)
    g = e._load(e.create_game('交锋验收', 'supreme_metal', 'ghost', 331, gender='male')['id'])
    g.pending_event = g.active_trial = None
    target = dict(target_name='异道对手', target_realm_index=1, path='dao',
                  target_power=1, combat_type='cultivator', non_story_combat=True)
    result, _ = e._combat(g, dict(target), False, random.Random(331))
    assert result != 'killed' and KEY not in g.player.milestones
    result, _ = e._combat(g, dict(target), True, random.Random(331))
    assert result == 'killed' and g.player.milestones[KEY] == 1
    result, _ = _settle_combat_kill(e._dependencies.combat_runtime, g,
        {'body_escaped_ids': ['escaping']}, None,
        dict(npc_id='escaping', name='逃逸元婴', path='dao', realm_index=4), random.Random(331), '')
    assert result == 'victory_escape' and g.player.milestones[KEY] == 1


def test_original_assets_have_complete_poses_and_transparency():
    folder = ROOT / 'web/assets/pixel/historical'
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    assert set(manifest['actors']) == set(REWARDS)
    for identity, actor in manifest['actors'].items():
        assert len(actor['animations']) == 7
        assert len(actor['spell_palette']) == 3
        poses = set()
        for clip in actor['animations'].values():
            assert len(clip['poses']) == len(clip['rects'])
            poses.update(clip['poses'])
        assert {'idle','gather','guard','brace','hit','stagger','kneel','down','domain',
                'fan_draw','fan_windup','fan_open','fan_release','fan_follow','fan_close'} <= poses
        action = actor['attack_action']
        assert action == actor['cast_effect']
        assert manifest['actions'][action]['contacts'] == [2.1]
        clip = actor['animations'][action]
        assert clip['poses'][42] == 'fan_release' and clip['poses'][0] == clip['poses'][-1] == 'idle'
        assert clip['duration'] == 4. and len(set(clip['poses'])) == 7
        assert set(actor['release_points']) == set(clip['poses'])-{'idle'}
        assert actor['release_points']['fan_release'] == actor['release_point']
        for kind in ['figure','portrait','thumbnail','actions','casting']:
            im = Image.open(folder / f'{identity}-{kind}.png')
            lo, hi = im.getchannel('A').getextrema()
            assert im.mode == 'RGBA' and lo == 0 and hi >= 250
            assert max(im.size) <= 2048


def test_painted_effects_are_unique_padded_and_have_dissipation():
    folder = ROOT / 'web/assets/pixel/historical'
    catalog = json.loads((ROOT/'content/visual_assets.json').read_text(encoding='utf-8'))['assets']
    for name, effect in [('nobunaga','nobunaga_command'),('seimei','seimei_lunar')]:
        path = folder / f'{name}-fx.png'
        assert hashlib.sha256(path.read_bytes()).hexdigest() == catalog[f'effect.{effect}.keyframes']['sha256']
        atlas = Image.open(path)
        assert atlas.mode == 'RGBA' and atlas.size == (1536,864)
        frames = [atlas.crop((i%4*384,i//4*288,i%4*384+384,i//4*288+288)) for i in range(12)]
        assert len({hashlib.sha256(im.tobytes()).digest() for im in frames}) == 12
        for frame in frames:
            left,top,right,bottom = frame.getbbox()
            assert 0 < left < right < 384 and 0 < top < bottom < 288
        coverage = lambda im: sum(im.getchannel('A').histogram()[128:])
        assert coverage(frames[-1]) < coverage(frames[8])*.5
