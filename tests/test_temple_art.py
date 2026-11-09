"""Generated temple portraits must ship intact and support both UI backgrounds."""
import hashlib
import json
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'web/assets/building-portraits'

def test_temple_portraits_ship_with_transparency_and_provenance():
    manifest=json.loads((ART/'manifest.json').read_text(encoding='utf8'))
    assert manifest['generator']=='OpenAI built-in image_gen'
    assert {row['file'] for row in manifest['assets']}=={'land-temple-intact-361.png','land-temple-ruin-361.png'}
    hashes=set()
    for row in manifest['assets']:
        path=ART/row['file']
        assert path.resolve().parent==ART.resolve()
        hashes.add(hashlib.sha256(path.read_bytes()).hexdigest())
        assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256']
        with Image.open(path) as image:
            assert image.mode=='RGBA' and list(image.size)==row['size']
            assert image.getchannel('A').getextrema()==(0,255)
            assert image.size[0]>=256 and image.size[1]>=256
        assert row['prompt'] and 'transparent' in row['prompt'].lower()
    assert len(hashes)==2
