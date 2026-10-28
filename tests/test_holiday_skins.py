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


@pytest.mark.parametrize('path', ['dao', 'demonic', 'ghost', 'monster', 'buddhist', 'confucian'])
@pytest.mark.parametrize('gender', ['female', 'male'])
def test_holiday_no_rank_or_dlc_gate_and_pure_cosmetic(path, gender):
    p = Player('节日', 'none', path=path, gender=gender, realm_index=0,
               race='monster' if path == 'monster' else 'human')
    power = combat_power(p)
    original = copy.deepcopy(p.to_dict())
    with patch.object(registry, 'EXTENSION_REPORT', []):
        for style in ('christmas', 'halloween'):
            key = f'actor.cosmetic.{style}-{gender}'
            skins.choose(p, key)
            assert skins.appearance(p) == dict(static=key, combat=f'{style}-{gender}')
            assert skins.appearance(Player.from_dict(p.to_dict()))['static'] == key
            with pytest.raises(ValueError):
                skins.choose(p, f'actor.cosmetic.{style}-'+('male' if gender == 'female' else 'female'))
    after = p.to_dict()
    for row in (original, after): row.pop('character_skins')
    assert after == original and combat_power(p) == power


def test_holiday_effect_metadata_belongs_to_selected_actor():
    manifest = json.loads((ROOT/'web/assets/pixel/holiday/manifest.json').read_text(encoding='utf8'))
    for identity, actor in manifest['actors'].items():
        assert actor['holiday_effect'] == ('halloween-bats' if identity == 'halloween-male' else identity.split('-')[0])
    ordinary = json.loads((ROOT/'web/assets/pixel/swimwear/manifest.json').read_text(encoding='utf8'))
    assert all('holiday_effect' not in a for a in ordinary['actors'].values())


def test_shipped_static_and_all_battle_frames_are_complete_and_self_contained():
    assets = public_catalog(ROOT, [])['assets']
    entry = assets['base.holiday_manifest']
    manifest = json.loads((ROOT / 'web' / entry['file'].lstrip('/')).read_text(encoding='utf8'))
    assert len(entry['skin_forms']) == len(manifest['actors']) == 4
    for identity, asset in assets.items():
        if not asset['file'].startswith('/assets/pixel/holiday/'):
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


def test_christmas_painted_frames_are_unique_padded_and_dissipate():
    path = ROOT/'web/assets/pixel/holiday/christmas-keyframes.png'
    atlas = Image.open(path)
    assert atlas.size == (1536,1152) and atlas.mode == 'RGBA'
    frames = [atlas.crop((i%4*384,i//4*288,i%4*384+384,i//4*288+288)) for i in range(16)]
    assert len({hashlib.sha256(im.tobytes()).digest() for im in frames}) == 16
    for frame in frames:
        left,top,right,bottom = frame.getbbox()
        assert 0 < left < right < 384 and 0 < top < bottom < 288
    coverage = lambda im: sum(im.getchannel('A').histogram()[128:])
    assert coverage(frames[-1]) < coverage(frames[10])*.2
