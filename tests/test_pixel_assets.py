"""The runtime pack must work from a clean checkout without ignored design files."""
import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / 'web/assets/pixel/v1'

# Frozen selected redraws, independently pinned so an older catalog cannot pass.
STATIC_REDRAWS = {
    'dao.male.figure': '855968da53f3bd20015f0cb0ad035fc9a313958664431a138ece6f2cee134472',
    'dao.male.portrait': 'b977df840451c45546d5c9772ed5e0c101f4bec0a57c37da92e4f560e5b5d049',
    'dao.female.figure': '73b5933a15bc560a48070ceea9d1a5858b67b63e1c2891452c19c34c20d6356a',
    'dao.female.portrait': 'd20e4dc1cc7d21a3ae9d6db2530d8905e6843e7bd8d64eee4d3f29ebc1a94a01',
    'demonic.male.figure': '417a6df03a8c10bac099fe1c01d25341aa3aae911cc0b65783403fe4c5dc748e',
    'demonic.male.portrait': '9b3de315e590430cecd9ef02586353beb9bb1199b69a1ab8c872cab8cb6abcd3',
    'demonic.female.figure': 'ec942ac3eccb9e78ab63082ba2e29605ef327171bf8c6f56963aa469cc33dd1b',
    'demonic.female.portrait': 'beae995477a7750824c1c2adbd833031bd1b40fb91ce67e10ef7b96f7d60ac52',
}


def test_selected_protagonist_redraws_are_the_runtime_assets():
    catalog = json.loads((PACK/'catalog.js').read_text(encoding='utf-8').removeprefix(
        'window.PixelAssetCatalog = ').strip().removesuffix(';'))
    for identity, digest in STATIC_REDRAWS.items():
        asset = catalog['assets']['actor.human.'+identity]
        assert hashlib.sha256((PACK/asset['file']).read_bytes()).hexdigest() == digest
        assert asset['size'] == ([256, 288] if identity.endswith('.figure') else [128, 128])


def test_reviewed_runtime_catalog_and_pixels():
    source = (PACK / 'catalog.js').read_text(encoding='utf-8')
    catalog = json.loads(source.removeprefix('window.PixelAssetCatalog = ').strip().removesuffix(';'))
    assert catalog['version'] == 1
    assert catalog['cell'] == [96, 96]
    assert catalog['anchor'] == [48, 84]
    assert len(catalog['frames']) == len(set(catalog['frames'])) == 16
    assert catalog['frames'][0] == 'idle_s'
    assert catalog['frames'][12:] == ['meditate', 'cast', 'hit', 'guard']
    assert len(catalog['assets']) == 13
    for asset in catalog['assets'].values():
        path = PACK / asset['file']
        assert path.resolve().parent == PACK.resolve()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == asset['sha256']
        with Image.open(path) as image:
            assert list(image.size) == asset['size']
            if 'atlas' in path.name:
                assert image.mode == 'RGBA'
                assert set(image.getchannel('A').getdata()) == {0, 255}
                for i in range(16):
                    frame = image.crop((i % 4 * 96, i // 4 * 96, i % 4 * 96 + 96, i // 4 * 96 + 96))
                    if catalog['frames'][i] in asset.get('frames', catalog['frames']):
                        assert frame.getbbox() is not None
                    else:
                        assert frame.getbbox() is None
    demonic = json.loads((PACK / 'provenance.json').read_text())['demonic_characters']
    for gender in ('male', 'female'):
        for kind in ('atlas',):
            row = catalog['assets'][f'actor.human.demonic.{gender}.{kind}']
            assert row['sha256'] == demonic['source_hashes'][row['file']]
        assert catalog['assets'][f'actor.human.demonic.{gender}.atlas']['frames'] == catalog['frames'][:13]
    assert 'not literal geography' in json.loads((PACK / 'provenance.json').read_text())['usage']


def test_runtime_has_no_design_dependency_or_gameplay_ports():
    assert (ROOT / 'web/assets/pixel/LUCIDE-LICENSE').is_file()
    for name in ('visual-assets.js', 'pixel-home.js'):
        source = (ROOT / 'web' / name).read_text(encoding='utf-8')
        assert 'design/' not in source
        for forbidden in ('Math.random', 'fetch(', 'setInterval', 'setTimeout', '/advance', '/choice'):
            assert forbidden not in source
