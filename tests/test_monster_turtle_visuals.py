"""Turtle lineage mapping, runtime atlas invariants and immutable projection."""
import copy,hashlib,json,random
from pathlib import Path
from unittest.mock import patch
import pytest
from PIL import Image
from cultivation_life import content_registry as registry
from cultivation_life.models import Player
from cultivation_life.monster_visuals import monster_appearance
from cultivation_life.visual_assets import extension_asset,public_catalog
from cultivation_life.errors import NotFoundError
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'dlc/monster-bloodlines/assets/visual/turtle'
DATA=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
def player(node,gender='female'):
    return Player(name='龟甲验收',spirit_root='heavenly',path='monster',gender=gender,monster_species_id='turtle',monster_evolution_id=node,monster_evolution_history=['TURTLE_SHELL_SOVEREIGN',node])
@pytest.mark.parametrize('node',list(DATA['nodes']))
@pytest.mark.parametrize('gender',['male','female'])
def test_true_node_projection_is_immutable(node,gender):
    p=player(node,gender);before=copy.deepcopy(p.to_dict());rng=random.getstate();a=monster_appearance(p)
    assert a['combat'] in DATA['actors'] and a['static']+'.figure' in public_catalog(ROOT,registry.EXTENSION_REPORT)['assets']
    assert p.to_dict()==before and random.getstate()==rng
def test_routes_retained_and_explicit_new_branch_wins():
    for node in ['TURTLE_OCEAN_EMPEROR','TURTLE_WORLD_SHELL']:
        p=player(node,'male');p.monster_evolution_history=['TURTLE_XUANWU_SOVEREIGN',node]
        assert monster_appearance(p)['combat']=='turtle-nascent-xuanwu-male'
        p.monster_evolution_history=[node];assert monster_appearance(p) is None
        p.monster_evolution_history=['TURTLE_TIDE_SOVEREIGN',node];assert monster_appearance(p) is None
    p=player('TURTLE_TIDE_5','male')
    assert monster_appearance(p)['combat']=='turtle-nascent-tide-male'
    p.monster_evolution_id='TURTLE_MAHAYANA_WORLD';p.realm_index=1;p.world='human'
    assert monster_appearance(p)['combat']=='turtle-integration-xuanwu-male'
def test_fallback_and_dlc_ownership():
    p=player('TURTLE_SPIRIT')
    with patch.object(registry,'EXTENSION_REPORT',[]):assert monster_appearance(p) is None
    for field,value in [('path','dao'),('monster_species_id','ape'),('monster_evolution_id','TURTLE_NOT_REAL'),('ghost_host_body',{'name':'宿身'}),('ghost_attachment',{'id':'x'})]:
        other=copy.deepcopy(p);setattr(other,field,value);assert monster_appearance(other) is None
    for row in json.loads((OUT/'registry.json').read_text(encoding='utf-8'))['assets'].values():
        with pytest.raises(NotFoundError):extension_asset(ROOT,ROOT,[],row['file'])
def test_packed_frames_and_endpoints():
    assert len(DATA['actors'])==19 and len(list(OUT.glob('*-portrait.png')))==19
    for identity,a in DATA['actors'].items():
        assert ('domain' in a['animations']) != a['creature']
        assert a['animations']['defeat']['poses'][-1]['pose']=='down'
        assert a['animations']['attack']['poses'][-1]['pose']=='idle'
        if a['creature']:assert identity.endswith('-shared')
        for g in a['animations'].values():
            p=OUT/g['sheet'].rsplit('/',1)[1];assert hashlib.sha256(p.read_bytes()).hexdigest()==g['sha256']
            assert g['frames']==len(g['rects'])==len(g['poses'])==round(g['duration']*20)+1
            with Image.open(p) as im:
                assert im.mode=='RGBA' and im.width*im.height*4<16*1024*1024
                assert len(set(im.getchannel('A').getdata()))>2
            for x,y,w,h,dx,dy in g['rects']:
                assert 0<=x<x+w<=g['size'][0] and 0<=y<y+h<=g['size'][1]
                assert 0<dx<dx+w<384 and 0<dy<dy+h<288
    provenance=json.loads((OUT/'provenance.json').read_text(encoding='utf-8'))
    assert provenance['painted_keyposes']==171 and provenance['animation_clips']==126
    assert next(s for s in provenance['sources'] if s['identity']=='turtle-iron-shared' and s['kind']=='actions')['file'].endswith('-v2.png')
