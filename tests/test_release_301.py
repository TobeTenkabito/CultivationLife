"""Changed gameplay, cosmetic persistence and actual exported character contracts."""
import copy
import hashlib
import json
import random
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from cultivation_life import character_skins, content_registry as registry
from cultivation_life.combat_visuals import combat_identity
from cultivation_life.engine import GameEngine
from cultivation_life.models import Player
from cultivation_life.rules import body_combat_power, combat_power, expected_combat_power, max_hp, max_mp
from cultivation_life.npc_names import person_name, SURNAMES, GIVEN_NAMES
from cultivation_life.system.relationships.dependents import proposal_species_allowed

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def ready(tmp_path):
    engine = GameEngine(ROOT, tmp_path / 'saves')
    made = engine.create_game('皮肤验收', 'none', 'dao', 301, gender='female')
    game = engine._load(made['id'])
    game.pending_event = None
    return engine, game


@pytest.mark.parametrize('path,old,expected', [('dao', 298, 300), ('monster', 300, 308), ('monster', 898, 900), ('monster', 950, 950)])
def test_mortal_lifespan_real_event_reload_and_submit(ready, path, old, expected):
    engine, game = ready
    game.player.path = path
    game.player.monster_lifespan_scaled = path == 'monster'
    game.player.lifespan = old
    event = engine._instantiate_event(engine.events_by_id['EVT_MORTAL_BODY_BEGIN_001'], game, random.Random(301))
    game.pending_event = event
    engine.store.save(game)
    assert engine.get_game(game.id)['pending_event']['id'] == event['id']
    engine.choose(game.id, 'begin')
    actual = engine.store.load(game.id).player.lifespan
    if old == 300:
        assert 308 <= actual <= 315
    else:
        assert actual == expected


def test_body_power_reaches_eighty_percent_and_actual_battle_unit(ready):
    engine, game = ready
    p = game.player
    p.body_training = 53
    p.hp, p.mp = max_hp(p), 0
    assert body_combat_power(p) == pytest.approx(expected_combat_power(5, 1) * .8)
    assert combat_power(p) >= body_combat_power(p)
    assert engine._player_combat_units(game)[0].power == combat_power(p)
    previous = 0
    for rank in range(101):
        p.body_training = rank
        assert body_combat_power(p) >= previous
        previous = body_combat_power(p)


def test_skin_selection_reload_is_cosmetic_and_locked_skin_is_atomic(ready):
    engine, game = ready
    p = game.player
    p.realm_index = 7
    p.world = 'spirit'
    p.location_id = engine.maps.default_location('spirit')
    engine.store.save(game)
    game = engine._load(game.id)
    key = 'actor.path.dao-nascent-hero-female'
    before = copy.deepcopy(game.to_dict())
    shown = engine.select_character_skin(game.id, key)
    saved = engine.store.load(game.id)
    assert shown['player']['visual_actor'] == key
    assert character_skins.appearance(saved.player)['combat'] == 'dao-nascent-hero-female'
    assert engine.get_game(game.id)['player']['character_skins']['selected'] == key
    after = saved.to_dict()
    for raw in (before, after):
        raw.pop('updated_at', None)
        raw['player'].pop('character_skins', None)
    assert after == before
    snapshot = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError):
        engine.select_character_skin(game.id, 'actor.path.demonic-integration-hero-male')
    assert engine.store._path(game.id).read_bytes() == snapshot
    # Already attained forms remain when the character is sealed on descent.
    game = engine._load(game.id)
    original = copy.deepcopy(game.player.character_skins)
    plan = engine._plan_world_transition(game, 'human', 'sealed_descent')
    engine._apply_world_transition(game, plan)
    assert game.player.character_skins == original
    assert character_skins.appearance(game.player)['static'] == key


def test_monster_history_unlocks_only_attained_branches_and_disabled_dlc_hides_them():
    p = Player('狐', 'none', path='monster', gender='female', monster_species_id='fox',
               monster_evolution_id='FOX_MYSTIC_7', monster_evolution_history=['FOX_KING', 'FOX_MOON_DREAM', 'FOX_ILLUSION_LORD', 'FOX_MYSTIC_7'])
    character_skins.remember(p)
    keys = {s['id'] for s in character_skins.eligible_skins(p)}
    old = 'actor.monster.fox-nascent-moon-female'
    assert old in keys and not any('nine-tail' in key for key in keys)
    character_skins.choose(p, old)
    saved = copy.deepcopy(p.to_dict())
    assert character_skins.appearance(p)['static'] == old
    with patch.object(registry, 'EXTENSION_REPORT', []):
        assert character_skins.eligible_skins(p) == []
        assert character_skins.appearance(p) is None
    assert p.to_dict() == saved
    assert character_skins.appearance(Player.from_dict(saved))['static'] == old


def test_names_expand_without_duplicates_or_serial_suffixes():
    assert len(SURNAMES) >= 120 and len(GIVEN_NAMES) >= 200
    rng = random.Random(301)
    used = set()
    for _ in range(1500):
        name = person_name(rng, used)
        assert name not in used and name.isalpha() and len(name) <= 4
        used.add(name)
    assert len({t.name for t in registry.TECHNIQUE_CATALOG.values()}) == len(registry.TECHNIQUE_CATALOG)


def test_monster_proposal_filter_and_stale_acceptance(ready):
    engine, game = ready
    p = game.player
    p.path, p.realm_index, p.monster_lifespan_scaled = 'monster', 1, True
    for npc in engine._all_world_npcs(game):
        npc.gender = 'female'
    owner = next(iter(game.world_npcs.values()))
    owner.gender, owner.realm_index, owner.path = 'male', 3, 'dao'
    class Trigger(random.Random):
        def random(self): return 0
        def choice(self, values): return values[0]
    assert not engine._maybe_concubine_proposal(game, Trigger())
    owner.path = 'monster'
    assert engine._maybe_concubine_proposal(game, Trigger())
    owner.path = 'dao'
    engine.store.save(game)
    assert engine.get_game(game.id)['pending_event']['id'] == 'SYS_CONCUBINE_PROPOSAL'
    result = engine.choose(game.id, 'accept')
    assert not result['concubine_system']['status']
    assert not engine.store.load(game.id).player.concubine_rejection_aftermath
    p.realm_index = 4
    assert proposal_species_allowed(p, owner)


def test_eight_base_forms_have_complete_static_and_motion_assets():
    catalog = json.loads((ROOT / 'content/visual_assets.json').read_text(encoding='utf-8'))['assets']
    entry = catalog['base.character_manifest']
    manifest = json.loads((ROOT / 'web' / entry['file'].lstrip('/')).read_text(encoding='utf-8'))
    assert len(entry['character_forms']) == len(manifest['actors']) == 8
    for form in entry['character_forms'] + entry['skin_forms']:
        for kind, size in [('portrait', (128, 128)), ('figure', (256, 288)), ('thumbnail', (128, 144))]:
            asset = catalog[form['static'] + '.' + kind]
            path = ROOT / 'web' / asset['file'].lstrip('/')
            assert hashlib.sha256(path.read_bytes()).hexdigest() == asset['sha256']
            with Image.open(path) as im:
                assert im.mode == 'RGBA' and im.size == size
                x, y, right, bottom = im.getbbox()
                assert 0 < x < right < im.width and 0 < y < bottom < im.height
    for actor in manifest['actors'].values():
        action = manifest['actions'][actor['attack_action']]
        assert action['duration'] == actor['animations'][actor['attack_action']]['duration']
        assert all(0 < contact < action['duration'] for contact in action['contacts'])
        assert set(actor['animations']) == {'idle', 'attack', 'hit', 'ward', 'brace', 'defeat', 'domain'}
        assert actor['animations']['defeat']['poses'][-1] == 'down'
        for clip in actor['animations'].values():
            assert clip['frames'] == len(clip['rects']) == len(clip['poses'])
            for x, y, w, h, dx, dy in clip['rects']:
                assert 0 <= x < x + w <= clip['size'][0] and 0 <= y < y + h <= clip['size'][1]
                assert 0 < dx < dx + w < 384 and 0 < dy < dy + h < 288
