"""Gender-shared flora identity projection and packaged visual invariants."""
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
OUT=ROOT/'dlc/monster-bloodlines/assets/visual/flora'
DATA=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))

def player(node,gender='female'):
    return Player(name='草木验收',spirit_root='heavenly',path='monster',gender=gender,monster_species_id='flora',monster_evolution_id=node,monster_evolution_history=['FLORA_SHAPED_SOVEREIGN',node])

@pytest.mark.parametrize('node',list(DATA['nodes']))
@pytest.mark.parametrize('gender',['male','female'])
def test_true_node_projection_is_shared_and_immutable(node,gender):
    p=player(node,gender);before=copy.deepcopy(p.to_dict());rng=random.getstate();a=monster_appearance(p)
    assert a['combat'] in DATA['actors'] and a['combat'].endswith('-shared')
    assert a['static']+'.figure' in public_catalog(ROOT,registry.EXTENSION_REPORT)['assets']
    assert a==monster_appearance(player(node,'male' if gender=='female' else 'female'))
    assert p.to_dict()==before and random.getstate()==rng

def test_merged_history_and_explicit_routes():
    for node in ['FLORA_EVERGREEN_EMPEROR','FLORA_WORLD_CANOPY']:
        p=player(node,'male');p.monster_evolution_history=['FLORA_WORLD_TREE_LORD',node]
        assert monster_appearance(p)['combat']=='flora-nascent-world-shared'
        p.monster_evolution_history=['FLORA_SHAPED_SOVEREIGN',node]
        assert monster_appearance(p)['combat']=='flora-nascent-ancient-shared'
        p.monster_evolution_history=[node];assert monster_appearance(p) is None
        p.monster_evolution_history=['FLORA_FLOWER_SOVEREIGN',node];assert monster_appearance(p) is None
        p.monster_evolution_history=['FLORA_THORN_SOVEREIGN',node];assert monster_appearance(p) is None
    p=player('FLORA_FLOWER_5','male')
    assert monster_appearance(p)['combat']=='flora-nascent-flower-shared'
    p.monster_evolution_id='FLORA_MAHAYANA_ORIGIN_TREE';p.realm_index=1;p.world='human'
    assert monster_appearance(p)['combat']=='flora-integration-world-shared'

def test_humanization_at_nascent_and_four_stage_reuse():
    assert len(DATA['nodes'])==31
    for node,rule in DATA['nodes'].items():
        actor=DATA['actors'][monster_appearance(player(node))['combat']]
        assert actor['creature']==(rule['realm']<4)
        assert actor['sex'] is None
    for prefix,route in [('ANCIENT','ancient'),('FLOWER','flower'),('THORN','thorn')]:
        for realm in [5,6,7,8]:
            stage='integration' if realm>=7 else 'nascent'
            assert monster_appearance(player(f'FLORA_{prefix}_{realm}'))['combat']==f'flora-{stage}-{route}-shared'

def test_fallback_and_dlc_ownership():
    p=player('FLORA_SPIRIT')
    with patch.object(registry,'EXTENSION_REPORT',[]):assert monster_appearance(p) is None
    for field,value in [('path','dao'),('monster_species_id','ape'),('monster_evolution_id','FLORA_NOT_REAL'),('ghost_host_body',{'name':'宿身'}),('ghost_attachment',{'id':'x'})]:
        other=copy.deepcopy(p);setattr(other,field,value);assert monster_appearance(other) is None
    for row in json.loads((OUT/'registry.json').read_text(encoding='utf-8'))['assets'].values():
        with pytest.raises(NotFoundError):extension_asset(ROOT,ROOT,[],row['file'])

def test_atlas_anatomical_scale_endpoints_and_provenance():
    assert len(DATA['actors'])==15 and len(list(OUT.glob('*-portrait.png')))==15
    for identity,a in DATA['actors'].items():
        assert identity.endswith('-shared') and a['sex'] is None
        assert ('domain' in a['animations']) != a['creature']
        assert a['anchor']==[192,256]
        assert a['animations']['defeat']['poses'][-1]['pose']=='down'
        assert a['animations']['attack']['poses'][-1]['pose']=='idle'
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
    assert provenance['painted_keyposes']==135 and provenance['animation_clips']==98
    for s in provenance['sources']:
        assert hashlib.sha256((ROOT/s['file']).read_bytes()).hexdigest()==s['sha256']
    for ident in ['moon-blossom','integration-ancient']:
        assert next(s for s in provenance['sources'] if s['identity']==f'flora-{ident}-shared' and s['kind']=='static')['file'].endswith('-v2.png')
