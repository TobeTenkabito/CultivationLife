"""Verify exact shipped beast and pending cosmetic assets through compiled HTTP."""
import hashlib
import json
import urllib.request
from pathlib import Path


def verify_hunt(base):
    root = Path(__file__).resolve().parents[1]
    def read(url):
        with urllib.request.urlopen(base+url,timeout=40) as response:
            return response.read()
    public = json.loads(read('/api/visual-assets'))['assets']
    names = {'hunt-rock-wolf','hunt-jade-eagle','hunt-gold-ape','hunt-jade-mantis'}
    manifest = json.loads(read(public['base.hunt_beasts_manifest']['file']))
    assert set(manifest['actors']) == names
    for key, row in public.items():
        if row['file'].startswith(('/assets/pixel/hunt-beasts/','/assets/pixel/historical/')) or key == 'effect.christmas.keyframes':
            data = read(row['file'])
            assert hashlib.sha256(data).hexdigest() == row['sha256']
            assert data == (root/'web'/row['file'].lstrip('/')).read_bytes()
    for script in ('historical-effects.js','christmas-effects.js','combat-beasts.js'):
        assert read('/'+script) == (root/'web'/script).read_bytes()
