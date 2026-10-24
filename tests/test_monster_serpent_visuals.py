"""Serpent assets follow true bloodline and DLC ownership without mutating saves."""
import copy
import hashlib
import json
import random
from pathlib import Path
from unittest.mock import patch
import pytest
from PIL import Image
from cultivation_life import content_registry as registry
from cultivation_life.models import Player
from cultivation_life.monster_visuals import monster_appearance, serpent_appearance, fox_appearance
from cultivation_life.visual_assets import extension_asset, public_catalog
from cultivation_life.errors import NotFoundError

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'dlc/monster-bloodlines/assets/visual/serpent'
DATA=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
OWNER='official.monster-bloodlines'

def player(node,gender='female'):
    return Player(name='蛇族验收',spirit_root='heavenly',path='monster',gender=gender,
                  monster_species_id='serpent',monster_evolution_id=node,monster_evolution_history=[node])

@pytest.mark.parametrize('node',list(DATA['nodes']))
@pytest.mark.parametrize('gender',['male','female'])
def test_actual_node_selects_self_contained_art_without_mutation(node,gender):
    p=player(node,gender);before=copy.deepcopy(p.to_dict());rng=random.getstate()
    a=monster_appearance(p)
    assert a==serpent_appearance(p) and a['combat'] in DATA['actors']
    assert a['static']+'.figure' in public_catalog(ROOT,registry.EXTENSION_REPORT)['assets']
    assert p.to_dict()==before and random.getstate()==rng and fox_appearance(p) is None

def test_sealed_display_does_not_change_real_bloodline_art_and_missing_stages_fall_back():
    p=player('SERPENT_ANCESTRAL_DRAGON','male');p.world='human';p.realm_index=1
    assert monster_appearance(p)['combat']=='serpent-integration-dragon-male'
    for node in ['SERPENT_EARTH_DEVOURER','SERPENT_TRUE_DRAGON','SERPENT_CELESTIAL_DRAGON','SERPENT_NOT_REAL']:
        p.monster_evolution_id=node
        assert monster_appearance(p) is None
    p.monster_evolution_id='SERPENT_MAHAYANA_ORIGIN'
    assert monster_appearance(p)['combat']=='serpent-integration-serpent-male'

def test_disabled_dlc_and_borrowed_bodies_do_not_use_serpent_art():
    p=player('SERPENT_SPIRIT')
    with patch.object(registry,'EXTENSION_REPORT',[]):assert monster_appearance(p) is None
    for field,value in [('path','dao'),('monster_species_id','turtle'),('ghost_host_body',{'name':'宿身'}),('ghost_attachment',{'id':'x'})]:
        other=copy.deepcopy(p);setattr(other,field,value);assert monster_appearance(other) is None
    for row in json.loads((OUT/'registry.json').read_text(encoding='utf-8'))['assets'].values():
        with pytest.raises(NotFoundError):extension_asset(ROOT,ROOT,[],row['file'])

def test_runtime_atlases_fit_and_low_realms_have_no_domain_clip():
    assert len(DATA['actors'])==11 and len(list(OUT.glob('*-portrait.png')))==11
    for identity,a in DATA['actors'].items():
        assert ('domain' in a['animations']) != a['creature']
        assert a['animations']['defeat']['poses'][-1]['pose']=='down'
        for g in a['animations'].values():
            path=OUT/g['sheet'].rsplit('/',1)[1]
            assert hashlib.sha256(path.read_bytes()).hexdigest()==g['sha256']
            assert g['frames']==len(g['rects'])==len(g['poses'])==round(g['duration']*20)+1
            with Image.open(path) as im:assert im.mode=='RGBA' and im.width*im.height*4<16*1024*1024
            for x,y,w,h,dx,dy in g['rects']:
                assert 0<=x<x+w<=g['size'][0] and 0<=y<y+h<=g['size'][1]
                assert 0<dx<dx+w<384 and 0<dy<dy+h<288
    sources=json.loads((OUT/'provenance.json').read_text(encoding='utf-8'))
    male=next(s for s in sources['sources'] if s['kind']=='static' and s['identity']=='serpent-integration-dragon-male')
    assert male['file'].endswith('dragon-male-v2.png')
    assert sources['painted_keyposes']==99 and sources['animation_clips']==70
