"""Approved social art ships without local design files and preserves actual identities."""
import hashlib
import json
from pathlib import Path

from PIL import Image
from cultivation_life.content_registry import WORLD_NPC_TEMPLATES

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / 'web/assets/pixel/social'


def test_adopted_pack_identity_and_integrity():
    catalog = json.loads((PACK / 'catalog.js').read_text(encoding='utf-8').removeprefix('window.NpcArtCatalog = ').strip().removesuffix(';'))
    provenance = json.loads((PACK / 'provenance.json').read_text(encoding='utf-8'))
    assert set(catalog['reserved_fixed_ids']) == set(WORLD_NPC_TEMPLATES)
    assert set(catalog['fixed']) == set(WORLD_NPC_TEMPLATES) - {'rank_xingmu'}
    assert provenance['pending_excluded'] == ['rank_xingmu']
    assert len(catalog['actors']) == 59
    assert len(provenance['files']) == 118
    assert set(p.name for p in PACK.glob('*.png')) == set(provenance['files'])
    for identity, key in catalog['fixed'].items():
        actor, npc = catalog['actors'][key], WORLD_NPC_TEMPLATES[identity]
        for field in ('race', 'path', 'gender'):
            assert actor[field] == getattr(npc, field)
        if identity in {'rank_lingxi', 'rank_shuangdi', 'asura_bloodmoon_witch'}:
            assert actor['art_gender_override']['art_gender'] == 'female'
            assert actor['gender'] == 'male'
    assert set(catalog['pools']) == {f'human.{path}.{gender}' for path in ('dao', 'demonic') for gender in ('male', 'female')}
    for pool, keys in catalog['pools'].items():
        assert len(keys) == len(set(keys)) == 4
        for key in keys:
            a = catalog['actors'][key]
            assert '.'.join(a[k] for k in ('race', 'path', 'gender')) == pool
    for key, actor in catalog['actors'].items():
        fixed = key.startswith('fixed-')
        for kind in ('figure', 'portrait'):
            asset = actor[kind]
            file = PACK / asset['file']
            assert file.resolve().parent == PACK.resolve()
            assert hashlib.sha256(file.read_bytes()).hexdigest() == asset['sha256'] == provenance['files'][file.name]
            with Image.open(file) as image:
                assert image.mode == 'RGBA'
                expected = ((256, 288) if fixed else (128, 192)) if kind == 'figure' else ((128, 128) if fixed else (96, 96))
                assert image.size == expected == tuple(asset['size'])
                assert set(image.getchannel('A').getdata()) == {0, 255}
                assert len({p[:3] for p in image.getdata() if p[3]}) <= (64 if fixed else 48)


def test_social_presentation_has_no_gameplay_or_authoring_dependency():
    source = (ROOT / 'web/npc-art.js').read_text(encoding='utf-8')
    for forbidden in ('design/', 'Math.random', 'fetch(', 'localStorage', 'setInterval', '/choice', '/advance'):
        assert forbidden not in source
