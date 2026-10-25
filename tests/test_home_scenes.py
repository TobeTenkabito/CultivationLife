"""Presentation derivatives preserve the original entities and settlement."""
import copy
import hashlib
import json
from pathlib import Path
import pytest
from PIL import Image
from cultivation_life.engine import GameEngine
from cultivation_life.combat_visuals import combat_identity, MIRROR_VARIANTS

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture(scope='module')
def engine(tmp_path_factory):
    return GameEngine(ROOT,tmp_path_factory.mktemp('home-scenes')/'saves')

@pytest.mark.parametrize('gender',['male','female'])
@pytest.mark.parametrize('path',['dao','demonic','ghost','confucian','buddhist'])
def test_mirrors_use_current_hero_without_mutation(engine,gender,path):
    data=engine.create_game('镜像', 'heavenly','dao',606,gender=gender,preset_id='core')
    game=engine.store.load(data['id']);game.player.path=path;before=copy.deepcopy(game.to_dict())
    for variant in MIRROR_VARIANTS:
        visual=combat_identity(game,dict(combat_type='trial',visual_variant=variant,target_name='镜像'))
        member=visual['teams']['npc'][0]
        assert member['asset']==visual['hero'] and member['visual_variant']==variant
        assert member['gender']==gender
    assert game.to_dict()==before

def test_names_and_foreign_souls_do_not_authorize_mirroring(engine):
    game=engine.store.load(engine.create_game('镜像边界','heavenly','dao',607,preset_id='core')['id'])
    for target in [dict(combat_type='trial',target_name='天魔心魔三尸'),
                   dict(combat_type='cultivator',visual_variant='heart_demon'),
                   dict(combat_type='trial',battle_kind='foreign_soul'),
                   dict(combat_type='trial',visual_variant='arbitrary')]:
        visual=combat_identity(game,target)
        assert 'visual_variant' not in visual['teams']['npc'][0]
        assert visual['enemy']!=visual['hero']

def test_building_stage_assets_are_distinct_and_bounded():
    folder=ROOT/'web/assets/pixel/buildings';data=json.loads((folder/'manifest.json').read_text())
    assert len(data['assets'])==46
    hashes=[]
    for filename,row in data['assets'].items():
        path=folder/filename;digest=hashlib.sha256(path.read_bytes()).hexdigest();hashes.append(digest)
        assert digest==row['sha256']
        image=Image.open(path);assert image.mode=='RGBA' and image.size==(96,96)
        bounds=image.getchannel('A').getbbox();assert bounds and 0<bounds[0]<bounds[2]<96 and 0<bounds[1]<bounds[3]<96
    assert len(set(hashes))==46

