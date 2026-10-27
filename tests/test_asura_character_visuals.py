"""Asura art follows attained rank and package ownership without changing state."""
import copy
import hashlib
import json
import random
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image
from cultivation_life import content_registry as registry
from cultivation_life.character_visuals import character_appearance
from cultivation_life.combat_visuals import combat_identity
from cultivation_life.models import Player
from cultivation_life.visual_assets import public_catalog, extension_asset
from cultivation_life.errors import NotFoundError

ROOT = Path(__file__).resolve().parents[1]
OWNER = 'official.asura-manifestation'
OUT = ROOT/'dlc/asura-manifestation/assets/visual/characters'


@pytest.mark.parametrize('gender', ['male', 'female'])
def test_attained_rank_boundary_read_only_and_disabled(gender):
    p = Player(name='修罗外观', spirit_root='heavenly', path='demonic', gender=gender, realm_index=8, world='asura')
    base = dict(static=f'actor.path.demonic-integration-hero-{gender}', combat=f'demonic-integration-hero-{gender}')
    assert character_appearance(p) == base  # Visiting Asura retains base art, never grants Asura art.
    p.realm_index = 9
    before = copy.deepcopy(p.to_dict()); rng = random.getstate()
    expected = dict(static=f'actor.path.asura-hero-{gender}', combat=f'asura-hero-{gender}')
    assert character_appearance(p) == expected
    assert character_appearance(p.to_dict()) == expected
    assert p.to_dict() == before and random.getstate() == rng
    for rank in [10, 11, 12]:
        p.realm_index = rank
        assert character_appearance(p) == expected
    p.realm_index = 4; p.world = 'human'
    p.sealed_cultivation = dict(realm_index=9, upper_world='asura')
    assert character_appearance(p) == expected
    assert character_appearance(p, role='npc') is None
    with patch.object(registry, 'EXTENSION_REPORT', [r for r in registry.EXTENSION_REPORT if r['id'] != OWNER]):
        assert character_appearance(p) == base
    assert character_appearance({**p.to_dict(), 'path': 'dao'}) == dict(
        static=f'actor.path.dao-integration-hero-{gender}', combat=f'dao-integration-hero-{gender}')
    for key, value in [('race','monster'), ('gender','unknown'), ('transformed',True),
                       ('ghost_host_body', {'id':'host'}), ('ghost_attachment', {'id':'host'}), ('identity_known',False)]:
        changed = {**p.to_dict(), key: value}
        assert character_appearance(changed) is None


def test_owned_images_and_all_animation_frames():
    data = json.loads((OUT/'manifest.json').read_text(encoding='utf8'))
    assert data['version'] == '1.3.0' and len(data['actors']) == 2
    rows = json.loads((OUT.parent/'registry.json').read_text(encoding='utf8'))['assets']
    assert len([r for r in rows.values() if not r.get('domain_styles') and not r.get('domain_controls') and not r.get('domain_art')]) == 9
    disabled = [r for r in registry.EXTENSION_REPORT if r['id'] != OWNER]
    assert not set(rows) & public_catalog(ROOT, disabled)['assets'].keys()
    for row in rows.values():
        target = extension_asset(ROOT, ROOT, registry.EXTENSION_REPORT, row['file'])
        assert hashlib.sha256(target.read_bytes()).hexdigest() == row['sha256']
        with pytest.raises(NotFoundError):
            extension_asset(ROOT, ROOT, disabled, row['file'])
        if target.suffix == '.png':
            image = Image.open(target)
            assert image.mode == 'RGBA' and list(image.size) == row['size']
            assert image.getextrema()[-1][0] == 0
    for identity, actor in data['actors'].items():
        atlas = Image.open(OUT/f'{identity}-actions.png')
        groups = actor['animations']
        assert len(groups) == 8  # Seven clips plus the spell alias.
        assert groups['attack']['poses'][-1] == 'idle'
        assert groups['defeat']['poses'][-1] == 'down'
        assert len(set(sum([g['poses'] for g in groups.values()], []))) == 9
        assert actor['role'] == 'hero' and actor['faction'] == 'demonic'
        for group in groups.values():
            assert group['frames'] == len(group['rects']) == len(group['poses'])
            for x,y,w,h,ox,oy in group['rects']:
                assert 0 <= x < x+w <= atlas.width and 0 <= y < y+h <= atlas.height
                assert 0 < ox < ox+w < 384 and 0 < oy < oy+h < 288
                assert atlas.crop((x,y,x+w,y+h)).getchannel('A').getbbox()


@pytest.mark.parametrize('gender', ['male', 'female'])
def test_real_preset_projection_and_trial_mirror(tmp_path, gender):
    from cultivation_life.engine import GameEngine
    engine = GameEngine(ROOT, tmp_path/'saves')
    made = engine.create_game('修罗外观', 'heavenly', 'demonic', seed=613, preset_id='asura_upper', gender=gender)
    game = engine.store.load(made['id'])
    before = copy.deepcopy(game.to_dict())
    target = dict(target_name='心魔', combat_type='trial', visual_variant='heart_demon', path='demonic', gender=gender)
    visual = combat_identity(game, target)
    assert visual['hero'] == visual['enemy'] == f'asura-hero-{gender}'
    assert game.to_dict() == before
    engine._combat(game, dict(target, target_realm_index=9, target_power=engine._player_battle_power(game)*.5), False, random.Random(613))
    assert game.last_combat_report['visual']['hero'] == f'asura-hero-{gender}'
    engine.store.save(game)
    assert character_appearance(engine.store.load(made['id']).player)['combat'] == f'asura-hero-{gender}'
