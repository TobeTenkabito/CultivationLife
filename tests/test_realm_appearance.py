"""Realm selection boundaries and optional-package ownership, not pixel replicas."""
import json
from pathlib import Path
from cultivation_life.realm_appearance import resolve_realm_appearance
from cultivation_life.visual_assets import catalog, public_catalog

ROOT=Path(__file__).resolve().parents[1]
OWNER='official.monster-bloodlines'


def test_sparse_stages_keep_previous_form_and_history_does_not_invent_a_branch():
    forms=[dict(min_realm=1,appearance={'static':'seed','combat':'seed'}),
           dict(min_realm=4,variants={'shared':{'static':'humanoid','combat':'humanoid'}}),
           dict(min_realm=7,history_variants={'chosen':{'female':{'static':'elder','combat':'elder'}}})]
    for realm in [1,2,3]:
        assert resolve_realm_appearance(forms,realm)['static']=='seed'
    for realm in [4,5,6]:
        assert resolve_realm_appearance(forms,realm,variant='male')['static']=='humanoid'
    assert resolve_realm_appearance(forms,7,variant='female',history=['chosen'])['static']=='elder'
    assert resolve_realm_appearance(forms,7,variant='female',history=['unknown'])['static']=='humanoid'
    assert resolve_realm_appearance(forms,0) is None


def test_registry_separation_and_independent_installation_root(tmp_path):
    import shutil
    assert not any(OWNER in a.get('requires',[]) for a in catalog(ROOT)['assets'].values())
    enabled=[dict(id=OWNER,status='loaded')]
    assert not any(a.get('appearance_key') for a in public_catalog(ROOT,enabled,tmp_path)['assets'].values())
    target=tmp_path/'dlc/renamed-monster-pack'
    (target/'assets/visual').mkdir(parents=True)
    shutil.copy2(ROOT/'dlc/monster-bloodlines/manifest.json',target/'manifest.json')
    shutil.copy2(ROOT/'dlc/monster-bloodlines/assets/visual/registry.json',target/'assets/visual/registry.json')
    assert len([r for r in public_catalog(ROOT,enabled,tmp_path)['assets'].values() if r.get('appearance_key')])==8
    assert not any(a.get('appearance_key') for a in public_catalog(ROOT,[],tmp_path)['assets'].values())


def test_optional_registry_cannot_override_core_or_claim_another_package(tmp_path):
    package=tmp_path/'dlc/test';(package/'assets').mkdir(parents=True)
    (package/'manifest.json').write_text(json.dumps(dict(id=OWNER,visual_registry='r.json')),encoding='utf-8')
    core_id, original=next(iter(catalog(ROOT)['assets'].items()))
    rows={core_id:dict(file=f'/extension-assets/{OWNER}/override.png',requires=[OWNER]),
          'foreign':dict(file='/extension-assets/foreign/steal.png',requires=[OWNER])}
    (package/'assets/r.json').write_text(json.dumps(dict(assets=rows)),encoding='utf-8')
    result=public_catalog(ROOT,[dict(id=OWNER,status='loaded')],tmp_path)
    # Disabled core extension entries also reserve their identity.
    assert result['assets'].get(core_id)==original
    assert 'foreign' not in result['assets']


def test_all_eight_species_have_self_contained_action_manifests():
    counts={}
    for path in (ROOT/'dlc/monster-bloodlines/assets/visual').glob('*/manifest.json'):
        data=json.loads(path.read_text(encoding='utf-8'))
        counts[path.parent.name]=len(data['actors'])
        for identity,a in data['actors'].items():
            assert a['energy_effect']
            for mode in ['idle',a['attack_action'],'ward','hit','defeat']:
                clip=a['animations'][mode]
                assert len(clip['rects'])==clip['frames']
                assert clip['sheet'].startswith(f'/extension-assets/{OWNER}/')
                assert (ROOT/'dlc/monster-bloodlines/assets'/clip['sheet'].split('/',3)[3]).is_file()
        assert data['realm_forms']
    assert counts==dict(fox=16,serpent=11,avian=17,ape=23,turtle=19,insect=19,aquatic=19,flora=15)
