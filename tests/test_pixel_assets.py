"""The runtime pack must work from a clean checkout without ignored design files."""
import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / 'web/assets/pixel/v1'


def test_reviewed_runtime_catalog_and_pixels():
    source = (PACK / 'catalog.js').read_text(encoding='utf-8')
    catalog = json.loads(source.removeprefix('window.PixelAssetCatalog = ').strip().removesuffix(';'))
    assert catalog['version'] == 1
    assert catalog['cell'] == [96, 96]
    assert catalog['anchor'] == [48, 84]
    assert len(catalog['frames']) == len(set(catalog['frames'])) == 16
    assert catalog['frames'][0] == 'idle_s'
    assert catalog['frames'][12:] == ['meditate', 'cast', 'hit', 'guard']
    assert len(catalog['assets']) == 5
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
                    assert frame.getbbox() is not None
    assert 'not literal geography' in json.loads((PACK / 'provenance.json').read_text())['usage']


def test_runtime_has_no_design_dependency_or_gameplay_ports():
    assert (ROOT / 'web/assets/pixel/LUCIDE-LICENSE').is_file()
    for name in ('visual-assets.js', 'pixel-home.js'):
        source = (ROOT / 'web' / name).read_text(encoding='utf-8')
        assert 'design/' not in source
        for forbidden in ('Math.random', 'fetch(', 'setInterval', 'setTimeout', '/advance', '/choice'):
            assert forbidden not in source
