"""Achievement authority, cross-save rewards and the two complete costume sets."""
import copy
import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image
from cultivation_life import character_skins as skins
from cultivation_life.models import Player
from cultivation_life.engine import GameEngine

ROOT=Path(__file__).resolve().parents[1]
ACHIEVEMENT='cultivation_rootless_legend'


@pytest.mark.parametrize('gender',['female','male'])
@pytest.mark.parametrize('path',['dao','demonic','monster','ghost','buddhist','confucian'])
def test_achievement_required_even_at_high_realm_and_no_realm_gate_after_grant(gender,path):
    p=Player('沧海','none',gender=gender,path=path,realm_index=8)
    key=f'actor.cosmetic.swim-tide-{gender}'
    assert key in {s['id'] for s in skins.public(p)['locked']}
    with pytest.raises(ValueError):skins.choose(p,key)
    before=copy.deepcopy(p.to_dict());p.realm_index=0
    assert skins.unlock_achievement_rewards(p,{ACHIEVEMENT:{}})
    skins.choose(p,key)
    assert skins.appearance(p)['combat']==f'swim-tide-{gender}'
    after=p.to_dict();after.pop('character_skins');before.pop('character_skins');before['realm_index']=0
    assert after==before
    restored=Player.from_dict(p.to_dict())
    assert skins.appearance(restored)==skins.appearance(p)
    assert not skins.unlock_achievement_rewards(restored,{ACHIEVEMENT:{}})
    opposite='male' if gender=='female' else 'female'
    with pytest.raises(ValueError):skins.choose(p,f'actor.cosmetic.swim-tide-{opposite}')


def test_real_global_achievement_unlocks_existing_and_new_saves(tmp_path):
    e=GameEngine(ROOT,tmp_path/'saves')
    old=e.create_game('未达成','supreme_metal','dao',323,gender='female')
    key='actor.cosmetic.swim-tide-female'
    e.get_game(old['id']);before=e.store._path(old['id']).read_bytes()
    with pytest.raises(ValueError):e.select_character_skin(old['id'],key)
    assert e.store._path(old['id']).read_bytes()==before
    legend=e.store.load(e.create_game('传奇','none','dao',324)['id'])
    legend.player.realm_index=8
    assert ACHIEVEMENT not in {r['id'] for r in e.achievements.evaluate(legend,player_rank=2)}
    assert ACHIEVEMENT in {r['id'] for r in e.achievements.evaluate(legend,player_rank=1)}
    assert key in {r['id'] for r in e.get_game(old['id'])['player']['character_skins']['available']}
    assert key in e.store.load(old['id']).player.character_skins['unlocked']
    assert e.select_character_skin(old['id'],key)['player']['visual_actor']==key
    new=e.create_game('新周目','none','dao',325,gender='male')
    assert 'actor.cosmetic.swim-tide-male' in {r['id'] for r in new['player']['character_skins']['available']}
    assert new['player']['realm_index']<4


def test_tide_assets_have_all_keyposes_and_transparent_statics():
    manifest=json.loads((ROOT/'web/assets/pixel/tide/manifest.json').read_text(encoding='utf-8'))
    assert set(manifest['actors'])=={'swim-tide-female','swim-tide-male'}
    for identity,actor in manifest['actors'].items():
        assert actor['cast_effect']=='tidal_wave'
        assert len(actor['animations'])==7
        for clip in actor['animations'].values():
            assert len(clip['rects'])==len(clip['poses'])
        for kind in ['figure','portrait','thumbnail']:
            im=Image.open(ROOT/f'web/assets/pixel/tide/{identity}-{kind}.png')
            lo,hi=im.getchannel('A').getextrema()
            assert im.mode=='RGBA' and lo==0 and hi>=250


def test_painted_water_sequence_is_complete_unique_and_padded():
    path=ROOT/'web/assets/pixel/tide/water-keyframes.png'
    catalog=json.loads((ROOT/'content/visual_assets.json').read_text(encoding='utf-8'))
    row=catalog['assets']['effect.tidal_wave.keyframes']
    assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256']
    atlas=Image.open(path)
    assert atlas.mode=='RGBA' and list(atlas.size)==row['size']==[1536,1152]
    frames=[atlas.crop((i%4*384,i//4*288,(i%4+1)*384,(i//4+1)*288)) for i in range(16)]
    assert len({hashlib.sha256(im.tobytes()).digest() for im in frames})==16
    for frame in frames:
        box=frame.getbbox()
        assert box and 0<box[0]<box[2]<384 and 0<box[1]<box[3]<288
    # The ending must shed water rather than repeat the massive impact silhouette.
    coverage=lambda im:sum(n for i,n in enumerate(im.getchannel('A').histogram()) if i>=128)
    assert coverage(frames[-1])<coverage(frames[9])*.7
