"""Optional art identity, ownership and real battle projection invariants."""
import copy
import json
import random
from pathlib import Path
from unittest.mock import patch
import pytest
from PIL import Image
from cultivation_life import content_registry as registry
from cultivation_life.models import Player
from cultivation_life.character_visuals import character_appearance
from cultivation_life.visual_assets import public_catalog, extension_asset
from cultivation_life.errors import NotFoundError

ROOT=Path(__file__).resolve().parents[1]
PACKAGES={'ghost':'ghost-reincarnation','confucian':'sage-way','buddhist':'buddhist-dharma'}

@pytest.mark.parametrize('path',PACKAGES)
@pytest.mark.parametrize('gender',['male','female'])
def test_identity_read_only_and_ownership(path,gender):
    p=Player(name='验收',spirit_root='heavenly',path=path,gender=gender)
    before=copy.deepcopy(p.to_dict());rng=random.getstate()
    a=character_appearance(p);assert a==dict(static=f'actor.path.{path}-hero-{gender}',combat=f'{path}-hero-{gender}')
    assert p.to_dict()==before and random.getstate()==rng
    npc={**p.to_dict(),'id':'stable-person','age':80}
    assert character_appearance(npc,role='npc')['combat']==f'{path}-npc-{gender}'
    with patch.object(registry,'EXTENSION_REPORT',[]):assert character_appearance(p) is None
    for key,value in [('ghost_host_body',{'id':'host'}),('ghost_attachment',{'id':'host'}),('race','monster'),('gender','unknown')]:
        other=copy.deepcopy(p);setattr(other,key,value);assert character_appearance(other) is None
    npc['identity_known']=False;assert character_appearance(npc,role='npc') is None

@pytest.mark.parametrize('path,package',PACKAGES.items())
def test_shipped_assets_and_action_endpoints(path,package):
    out=ROOT/'dlc'/package/'assets/visual/characters'
    data=json.loads((out/'manifest.json').read_text(encoding='utf8'))
    entries=json.loads((out.parent/'registry.json').read_text(encoding='utf8'))['assets']
    assert len(data['actors'])==4 and len([r for r in entries.values() if not r.get('domain_styles') and not r.get('domain_controls') and not r.get('domain_art')])==17
    for row in entries.values():
        target=extension_asset(ROOT,ROOT,registry.EXTENSION_REPORT,row['file'])
        import hashlib
        assert hashlib.sha256(target.read_bytes()).hexdigest()==row['sha256']
        with pytest.raises(NotFoundError):extension_asset(ROOT,ROOT,[],row['file'])
        if target.suffix=='.png':
            im=Image.open(target);assert list(im.size)==row['size'] and im.mode=='RGBA'
            assert im.getextrema()[-1][0]==0
    for actor in data['actors'].values():
        groups=actor['animations'];assert groups['attack']['poses'][-1]=='idle'
        assert groups['defeat']['poses'][-1]=='down'
        assert len(set(sum([a['poses'] for a in groups.values()],[])))==9
        assert actor['energy_effect'] and actor['sex'] in ['male','female']
    assert not any(key.startswith('actor.path.'+path+'-') for key in json.loads((ROOT/'content/visual_assets.json').read_text(encoding='utf8'))['assets'])

def test_real_combat_new_npc_with_core_hero(tmp_path):
    from cultivation_life.engine import GameEngine
    from cultivation_life.combat_visuals import combat_identity
    engine=GameEngine(ROOT,tmp_path/'saves');made=engine.create_game('验收','heavenly','dao',seed=510,preset_id='core')
    game=engine.store.load(made['id']);before=copy.deepcopy(game.to_dict())
    target=dict(target_name='来客',path='buddhist',gender='female',race='human',combat_type='cultivator')
    visual=combat_identity(game,target)
    assert visual['enemy']=='buddhist-npc-female' and visual['hero'].startswith('dao-')
    assert game.to_dict()==before
    engine._combat(game,{**target,'target_power':engine._player_battle_power(game)*.5,'target_realm_index':3},False,random.Random(510))
    assert game.last_combat_report['visual']['enemy']=='buddhist-npc-female'

def test_ghost_female_user_selected_red_source_and_actions():
    p=ROOT/'dlc/ghost-reincarnation/assets/visual/characters/provenance.json'
    data=json.loads(p.read_text(encoding='utf8'))['sources']
    hero=next(r for r in data if r['identity']=='ghost-hero-female')
    npc=next(r for r in data if r['identity']=='ghost-npc-female')
    assert hero['static_source']=='source/ghost-npc-female.png'
    assert hero['actions_source']=='source/ghost-npc-female-actions.png'
    assert npc['static_source']=='source/ghost-hero-female.png'
    assert npc['actions_source']=='source/ghost-hero-female-actions.png'
