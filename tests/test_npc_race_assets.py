"""The shipped race portraits are reviewable, transparent and self-contained."""
import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def test_race_pairs_and_source_provenance():
    folder = ROOT/'web/assets/pixel/social-races'
    source = (folder/'catalog.js').read_text(encoding='utf-8')
    catalog = json.loads(source.removeprefix('window.NpcRaceCatalog = ').strip().removesuffix(';'))
    assert set(catalog) == {f'{race}.{gender}' for race in ('magnetfolk', 'frostfolk') for gender in ('male', 'female')}
    provenance = json.loads((folder/'provenance.json').read_text(encoding='utf-8'))
    assert provenance['generator'] == 'built-in image_gen'
    assert len(provenance['actors']) == 4
    for key, actor in catalog.items():
        assert key == f'{actor["race"]}.{actor["gender"]}' and actor['min_age'] == 18
        for kind in ('figure', 'portrait'):
            asset = actor[kind]
            path = ROOT/'web'/asset['file'].lstrip('/')
            assert hashlib.sha256(path.read_bytes()).hexdigest() == asset['sha256']
            with Image.open(path) as image:
                assert image.mode == 'RGBA' and list(image.size) == asset['native_size']
                assert image.getchannel('A').getextrema()[0] == 0
            record = next(row for row in provenance['actors'] if row['race']==actor['race'] and row['gender']==actor['gender'])
            assert record['assets'][kind] == asset and record[kind+'_prompt']
