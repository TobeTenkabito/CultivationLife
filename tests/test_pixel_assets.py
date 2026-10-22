"""The runtime pack must work from a clean checkout without ignored design files."""
import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / 'web/assets/pixel/v1'

# Frozen selected redraws, independently pinned so an older catalog cannot pass.
STATIC_REDRAWS = {
    'dao.male.figure': '998a5f1398dbc58951ce6e080bc533b1cd33c502c9ba2b1423503287015cf58b',
    'dao.male.portrait': 'd2fff01e03db386608616d664c0ab33993e6ec889cc3043ff21ae2be6b37282a',
    'dao.female.figure': 'ecff917772738c3ead6f587082a4c939852d482602eea5afdd8523a7e0996bf4',
    'dao.female.portrait': '8f9bbd700f20280dee30bcb1f03716e7d286a68bbfae3637c013c1a620fa9de3',
    'demonic.male.figure': '31397b527b03d35acc53ce2c7b89a5f3b4b56284dedd3b46ae29bfe11082cb6d',
    'demonic.male.portrait': '619b0c96302121f79b7a443e2c117e1f124bb7a6e1285e691078e14701df814c',
    'demonic.female.figure': '59d11ba2b14b386d8d397403226883ca51cf61aed9f62dc2b600555494772679',
    'demonic.female.portrait': 'e6ab7c801c4622b41facef412f08b3e7d262c9a3448c193255552c9995285325',
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
