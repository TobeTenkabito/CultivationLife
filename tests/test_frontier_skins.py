"""1890s cosmetics, rank-seven swimwear and painted revolver choreography."""
import copy
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image
from cultivation_life import character_skins as skins, content_registry as registry
from cultivation_life.models import Player
from cultivation_life.engine import GameEngine
from cultivation_life.visual_assets import public_catalog

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('path',['dao','demonic','ghost','monster','buddhist','confucian'])
@pytest.mark.parametrize('gender',['male','female'])
def test_unlock_gender_pure_cosmetic_and_roundtrip(path,gender):
    p=Player('荒原','none',path=path,gender=gender)
    cowboy=f'actor.cosmetic.frontier-{gender}'
    swim=f'actor.cosmetic.swim-integration-{gender}'
    with patch.object(registry,'EXTENSION_REPORT',[]):
        before=copy.deepcopy(p.to_dict())
        skins.choose(p,cowboy)
        after=p.to_dict()
        before.pop('character_skins');after.pop('character_skins')
        assert before==after
        assert skins.appearance(p)['static']==cowboy
        for rank in [0,4,5,6]:
            p.realm_index=rank
            with pytest.raises(ValueError):skins.choose(p,swim)
            assert swim in {s['id'] for s in skins.public(p)['locked']}
        p.realm_index=7;skins.choose(p,swim)
        p.realm_index=4
        assert skins.appearance(Player.from_dict(p.to_dict()))['static']==swim
        other='male' if gender=='female' else 'female'
        with pytest.raises(ValueError):skins.choose(p,f'actor.cosmetic.frontier-{other}')


@pytest.mark.parametrize('field',['sealed_cultivation','cultivation_suppression'])
def test_swimwear_uses_attained_rank(field):
    p=Player('沧溟','none',gender='female',realm_index=1)
    setattr(p,field,dict(realm_index=7))
    skins.choose(p,'actor.cosmetic.swim-integration-female')
    assert skins.appearance(p)['combat']=='swim-integration-female'


def test_real_gate_has_no_charge_or_save_mutation(tmp_path):
    e=GameEngine(ROOT,tmp_path/'saves')
    made=e.create_game('边界','supreme_metal','dao',322,gender='female',preset_id='core')
    e.get_game(made['id']);before=e.store._path(made['id']).read_bytes()
    with pytest.raises(ValueError):e.select_character_skin(made['id'],'actor.cosmetic.swim-integration-female')
    assert e.store._path(made['id']).read_bytes()==before


def test_shipped_originals_and_gun_keyframes():
    assets=public_catalog(ROOT,[])['assets'];entry=assets['base.frontier_manifest']
    manifest=json.loads((ROOT/'web'/entry['file'].lstrip('/')).read_text(encoding='utf8'))
    assert len(entry['skin_forms'])==len(manifest['actors'])==4
    for identity,row in assets.items():
        if not row['file'].startswith('/assets/pixel/frontier/'):continue
        path=ROOT/'web'/row['file'].lstrip('/')
        assert not row['requires'] and hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256']
        if path.suffix=='.png':
            with Image.open(path) as im:
                assert im.mode=='RGBA' and list(im.size)==row['size']
                assert im.getchannel('A').getextrema()[0]==0
    for identity,actor in manifest['actors'].items():
        gun=identity.startswith('frontier-')
        assert (actor.get('cast_effect')=='revolver') is gun
        action='revolver' if gun else 'attack'
        assert actor['attack_action']==action and manifest['actions'][action]['contacts']==[2.1]
        for clip in actor['animations'].values():
            assert len(clip['poses'])==len(clip['rects'])==clip['frames']
            with Image.open(ROOT/'web'/clip['sheet'].lstrip('/')) as sheet:
                for x,y,w,h,dx,dy in clip['rects']:
                    assert 0<=x<x+w<=sheet.width and 0<=y<y+h<=sheet.height
                    assert 0<dx<dx+w<384 and 0<dy<dy+h<288
        if gun:
            poses=actor['animations']['revolver']['poses']
            assert list(dict.fromkeys(poses))==['idle','gather','aim','release','recoil','recover','holster']
            assert poses[40]=='release' and poses[44]=='recoil'
            assert len(set(map(tuple,actor['animations']['revolver']['rects'])))==7
        else:assert 'cast_effect' not in actor
