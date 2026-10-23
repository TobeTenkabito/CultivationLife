"""Fox DLC ownership, bloodline selection and immutable painted runtime assets."""
import copy
import hashlib
import json
import random
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image

from cultivation_life import content_registry as registry
from cultivation_life.models import Player
from cultivation_life.monster_visuals import fox_appearance
from cultivation_life.visual_assets import extension_asset, public_catalog
from cultivation_life.errors import NotFoundError

ROOT=Path(__file__).resolve().parents[1]
OWNER='official.monster-bloodlines'
OUT=ROOT/'dlc/monster-bloodlines/assets/visual/fox'
DATA=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))


def fox(node, gender='female', history=None):
    return Player(name='狐族验收',spirit_root='heavenly',path='monster',gender=gender,
                  monster_species_id='fox',monster_evolution_id=node,
                  monster_evolution_history=history or [node])


@pytest.mark.parametrize('node',list(DATA['nodes']))
@pytest.mark.parametrize('gender',['female','male'])
def test_every_shipped_node_has_explicit_asset_or_history_fallback(node,gender):
    p=fox(node,gender,['FOX_NINE_TAIL',node]); before=copy.deepcopy(p.to_dict()); rng=random.getstate()
    selected=fox_appearance(p)
    assert selected and selected['combat'] in DATA['actors']
    assert selected['static']+'.figure' in public_catalog(ROOT,registry.EXTENSION_REPORT)['assets']
    assert p.to_dict()==before and random.getstate()==rng
    assert 'visual_actor' not in p.to_dict()


def test_shared_stages_keep_history_until_explicit_branch_and_ignore_location_or_sealing():
    p=fox('FOX_DREAM_EMPEROR',history=['FOX_MOON_DREAM','FOX_ILLUSION_LORD','FOX_DREAM_EMPEROR'])
    assert fox_appearance(p)['combat']=='fox-nascent-moon-female'
    p.world='human';p.realm_index=1
    assert fox_appearance(p)['combat']=='fox-nascent-moon-female'
    p.monster_evolution_id='FOX_MYSTIC_7'
    assert fox_appearance(p)['combat']=='fox-integration-mystic-female'
    assert fox_appearance(fox('FOX_DREAM_EMPEROR')) is None
    for node in ['FOX_NOT_REAL','FOX_NETHER_TRUE_1']:
        assert fox_appearance(fox(node)) is None


def test_disabled_dlc_host_and_other_species_cannot_request_fox_art():
    p=fox('FOX_KING')
    assert fox_appearance(p)['combat']=='fox-king-shared'
    with patch.object(registry,'EXTENSION_REPORT',[]):
        assert fox_appearance(p) is None
    for field,value in [('ghost_host_body',{'name':'宿身'}),('ghost_attachment',{'id':'x'}),
                        ('monster_species_id','turtle'),('path','dao')]:
        other=copy.deepcopy(p);setattr(other,field,value)
        assert fox_appearance(other) is None
    for row in public_catalog(ROOT,registry.EXTENSION_REPORT)['assets'].values():
        if OWNER not in row.get('requires',[]):continue
        with pytest.raises(NotFoundError):extension_asset(ROOT,ROOT,[],row['file'])


def test_runtime_complete_and_bounded_and_preserves_spirit_tail_alpha():
    assert len(DATA['actors'])==16
    assert len(list(OUT.glob('*-portrait.png')))==20
    for identity,actor in DATA['actors'].items():
        assert set(actor['animations'])=={'idle','attack','fox_spell','hit','ward','brace','defeat','domain'}
        group=actor['animations']['attack']
        path=OUT/group['sheet'].rsplit('/',1)[1]
        assert hashlib.sha256(path.read_bytes()).hexdigest()==group['sha256']
        with Image.open(path) as im:
            assert im.width*im.height*4 < 16*1024*1024
            pixels=np.asarray(im)
            assert not pixels[pixels[:,:,3]==0].any()
            if 'integration' in identity:
                assert ((pixels[:,:,3]>0)&(pixels[:,:,3]<192)).sum()>100
        for name,g in actor['animations'].items():
            assert g['frames']==len(g['poses'])==len(g['rects'])==round(g['duration']*20)+1
            for x,y,w,h,dx,dy in g['rects']:
                assert 0<=x<x+w<=g['size'][0] and 0<=y<y+h<=g['size'][1]
                assert 0<dx<dx+w<384 and 0<dy<dy+h<288
        assert actor['animations']['defeat']['poses'][-1]['pose']=='down'
    provenance=json.loads((OUT/'provenance.json').read_text(encoding='utf-8'))
    assert provenance['painted_keyposes']==144 and provenance['animation_clips']==112


def test_approved_nascent_pixels_are_byte_identical():
    frozen=json.loads((ROOT/'tests/fixtures/fox_approved_pixel_hashes.json').read_text(encoding='utf-8'))
    for key,a in frozen.items():
        for kind in ['portrait','figure','thumbnail']:
            assert hashlib.sha256((OUT/f'fox-nascent-{key}-{kind}.png').read_bytes()).hexdigest()==a[kind]
