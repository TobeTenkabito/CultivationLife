"""Fengyi reward, demonic-only cosmetic eligibility and painted animation assets."""
import hashlib
import json
from pathlib import Path
import pytest
from PIL import Image
from cultivation_life import character_skins as skins
from cultivation_life.models import Player
from test_npc_promises import ready, original

ROOT = Path(__file__).resolve().parents[1]
KEY = 'actor.cosmetic.diaochan-female'
ACHIEVEMENT = 'relationship_fengyi_pavilion'


@pytest.mark.parametrize('path',['dao','demonic','ghost','monster','buddhist','confucian'])
@pytest.mark.parametrize('gender',['male','female'])
def test_global_reward_restricts_current_path_and_gender_without_realm_gate(path,gender):
    p=Player('凤仪','none',path=path,gender=gender,realm_index=0)
    with pytest.raises(ValueError):skins.choose(p,KEY)
    correct=path=='demonic' and gender=='female'
    assert any(s['id']==KEY for s in skins.public(p)['locked']) == correct
    before=p.to_dict()
    skins.unlock_achievement_rewards(p,{ACHIEVEMENT:{}})
    if correct:
        skins.choose(p,KEY)
        assert skins.appearance(p)['combat']=='diaochan-female'
        restored=Player.from_dict(p.to_dict())
        assert skins.appearance(restored)==skins.appearance(p)
        p.path='dao'
        assert KEY not in {s['id'] for s in skins.eligible_skins(p)}
        assert (skins.appearance(p) or {}).get('combat')!='diaochan-female'
        with pytest.raises(ValueError):skins.choose(p,KEY)
        p.path='demonic'
        assert skins.appearance(p)['combat']=='diaochan-female'
    else:
        # Persisted IDs cannot bypass current path/sex, including stale wardrobe submissions.
        p.character_skins={'unlocked':[KEY],'selected':KEY}
        with pytest.raises(ValueError):skins.choose(p,KEY)
        assert (skins.appearance(p) or {}).get('combat')!='diaochan-female'
    after=p.to_dict();before.pop('character_skins');after.pop('character_skins')
    assert before==after


def test_real_fengyi_command_grants_skin_and_new_demonic_save_receives_global_reward(ready):
    e,g,actor,owner=ready
    g.player.path='demonic';e.store.save(g)
    result=e.contact_action(g.id,actor.id,'promise',owner.id,g.diplomacy_unit)
    assert ACHIEVEMENT in {a['id'] for a in result['new_achievements']}
    assert KEY in {s['id'] for s in result['player']['character_skins']['available']}
    assert e.select_character_skin(g.id,KEY)['player']['visual_actor']==KEY
    assert e.get_game(g.id)['player']['visual_actor']==KEY
    new=e.create_game('凤仪来世','none','demonic',330,gender='female')
    assert KEY in {s['id'] for s in new['player']['character_skins']['available']}
    assert not e.store.load(new['id']).player.milestones.get('fengyi_pavilion')
    other=e.create_game('道门','none','dao',331,gender='female')
    assert KEY not in {s['id'] for s in other['player']['character_skins']['available']}


def test_dedicated_attack_and_twelve_distinct_padded_effect_frames():
    folder=ROOT/'web/assets/pixel/diaochan'
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf8'))
    actor=manifest['actors']['diaochan-female'];action=actor['attack_action']
    assert action==actor['cast_effect']=='diaochan_phoenix'
    assert manifest['actions'][action]['contacts']==[2.1]
    clip=actor['animations'][action]
    assert clip['duration']==4 and clip['frames']==len(clip['rects'])==81
    assert clip['poses'][42]=='fan_release' and len(set(clip['poses']))==7
    assert set(actor['release_points'])==set(clip['poses'])-{'idle'}
    for name in ['figure','portrait','thumbnail','actions','casting']:
        with Image.open(folder/f'diaochan-female-{name}.png') as im:
            assert im.mode=='RGBA' and im.getchannel('A').getextrema()[0]==0
    with Image.open(folder/'diaochan-fx.png') as im:
        assert im.size==(1536,864)
        frames=[im.crop((i%4*384,i//4*288,i%4*384+384,i//4*288+288)) for i in range(12)]
        assert len({hashlib.sha256(f.tobytes()).digest() for f in frames})==12
        for f in frames:
            l,t,r,b=f.getbbox();assert 0<l<r<384 and 0<t<b<288
        coverage=lambda f:sum(f.getchannel('A').histogram()[128:])
        assert coverage(frames[-1])<coverage(frames[8])*.5
