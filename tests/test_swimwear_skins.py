"""Universal cosmetic unlocks, authoritative commands and complete runtime artwork."""
import copy
import hashlib
import json
import random
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image
from cultivation_life import character_skins as skins, content_registry as registry
from cultivation_life.combat_visuals import combat_identity
from cultivation_life.engine import GameEngine
from cultivation_life.models import Player
from cultivation_life.rules import combat_power
from cultivation_life.visual_assets import public_catalog

ROOT = Path(__file__).resolve().parents[1]


def key(style, gender):
    return f'actor.cosmetic.swim-{style}-{gender}'


@pytest.mark.parametrize('path', ['dao', 'demonic', 'ghost', 'monster', 'buddhist', 'confucian'])
@pytest.mark.parametrize('gender', ['female', 'male'])
def test_all_paths_both_genders_real_rank_and_no_dlc_dependency(path, gender):
    p = Player('泳装', 'none', path=path, gender=gender, race='monster' if path == 'monster' else 'human')
    natural = skins.natural_appearance(p)
    assert skins.appearance(p) == natural  # No auto-replacement of growth art.
    initial = copy.deepcopy(p.to_dict())
    state = random.getstate()
    assert key('sunny', gender) in {s['id'] for s in skins.eligible_skins(p)}
    assert key('moon', gender) in {s['id'] for s in skins.public(p)['locked']}
    assert p.to_dict() == initial and state == random.getstate()
    for rank in (0, 1, 4):
        p.realm_index = rank
        with pytest.raises(ValueError):
            skins.choose(p, key('moon', gender))
    p.realm_index = 5
    with patch.object(registry, 'EXTENSION_REPORT', []):
        skins.choose(p, key('moon', gender))
        assert skins.appearance(p)['static'] == key('moon', gender)
        assert not skins.public(p)['locked']
        with pytest.raises(ValueError):
            skins.choose(p, key('moon', 'male' if gender == 'female' else 'female'))
    saved = p.to_dict()
    assert skins.appearance(Player.from_dict(saved))['static'] == key('moon', gender)


@pytest.mark.parametrize('field', ['sealed_cultivation', 'cultivation_suppression'])
def test_actual_attained_rank_unlocks_while_sealed_and_remains_recorded(field):
    p = Player('封印', 'none', gender='female', realm_index=1)
    setattr(p, field, {'realm_index': 5})
    skins.choose(p, key('moon', 'female'))
    setattr(p, field, {})
    assert skins.appearance(p)['static'] == key('moon', 'female')


@pytest.mark.parametrize('field', ['ghost_host_body', 'ghost_attachment', 'transformation_loadouts'])
def test_temporary_body_cannot_be_replaced_by_swimwear(field):
    p = Player('形态', 'none', gender='female', realm_index=5)
    skins.choose(p, key('moon', 'female'))
    setattr(p, field, {None: {'active': ['shape']}} if field == 'transformation_loadouts' else {'id': 'host'})
    before = copy.deepcopy(p.to_dict())
    assert skins.public(p)['blocked']
    with pytest.raises(ValueError):
        skins.choose(p, key('sunny', 'female'))
    assert skins.appearance(p) == skins.natural_appearance(p)
    assert p.to_dict() == before


def test_real_command_atomic_gate_roundtrip_and_combat_identity(tmp_path):
    engine = GameEngine(ROOT, tmp_path / 'saves')
    made = engine.create_game('游海', 'supreme_metal', 'dao', 327, gender='female',
                              custom_start=dict(world='human', realm_index=4))
    game = engine._load(made['id'])
    game.pending_event = None
    engine.store.save(game)
    engine.get_game(game.id)
    saved = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError):
        engine.select_character_skin(game.id, key('moon', 'female'))
    assert saved == engine.store._path(game.id).read_bytes()
    before = engine.store.load(game.id).to_dict()
    power = combat_power(engine.store.load(game.id).player)
    result = engine.select_character_skin(game.id, key('sunny', 'female'))
    assert result['player']['visual_actor'] == key('sunny', 'female')
    after = engine.store.load(game.id).to_dict()
    for row in (before, after):
        row.pop('updated_at', None)
        row['player'].pop('character_skins')
    assert after == before
    assert combat_power(engine.store.load(game.id).player) == power
    assert engine.get_game(game.id)['player']['visual_actor'] == key('sunny', 'female')
    game = engine._load(game.id)
    assert combat_identity(game, dict(combat_type='beast', target_name='灵鹤'))['hero'] == 'swim-sunny-female'
    engine.select_character_skin(game.id, '')
    assert engine.get_game(game.id)['player']['visual_actor'] == 'actor.path.dao-nascent-hero-female'


def test_shipped_static_and_all_battle_frames_are_complete_and_self_contained():
    assets = public_catalog(ROOT, [])['assets']
    entry = assets['base.swimwear_manifest']
    manifest = json.loads((ROOT / 'web' / entry['file'].lstrip('/')).read_text(encoding='utf8'))
    assert len(entry['skin_forms']) == len(manifest['actors']) == 4
    for identity, asset in assets.items():
        if not asset['file'].startswith('/assets/pixel/swimwear/'):
            continue
        target = ROOT / 'web' / asset['file'].lstrip('/')
        assert not asset['requires']
        assert hashlib.sha256(target.read_bytes()).hexdigest() == asset['sha256']
        if target.suffix == '.png':
            with Image.open(target) as im:
                assert im.mode == 'RGBA' and list(im.size) == asset['size']
                low, high = im.getchannel('A').getextrema()
                assert low == 0 and high >= 250  # Preserve generated soft alpha, including 254 interiors.
                if identity.startswith('actor.'):
                    x, y, r, b = im.getbbox()
                    assert 0 < x < r < im.width and 0 < y < b < im.height
    for actor in manifest['actors'].values():
        assert set(actor['animations']) == {'idle', 'attack', 'hit', 'ward', 'brace', 'defeat', 'domain'}
        assert actor['animations']['defeat']['poses'][-1] == 'down'
        poses = set()
        for clip in actor['animations'].values():
            poses.update(clip['poses'])
            assert clip['frames'] == len(clip['rects']) == len(clip['poses'])
            with Image.open(ROOT / 'web' / clip['sheet'].lstrip('/')) as sheet:
                for x, y, w, h, dx, dy in clip['rects']:
                    assert 0 <= x < x+w <= sheet.width and 0 <= y < y+h <= sheet.height
                    assert 0 < dx < dx+w < 384 and 0 < dy < dy+h < 288
                    assert sheet.crop((x, y, x+w, y+h)).getbbox()
        assert poses == {'idle', 'gather', 'release', 'guard', 'brace', 'hit', 'stagger', 'kneel', 'down', 'domain'}
