"""Mechanically import reviewed design assets; never run during gameplay or builds."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
FRAMES = [f'{pose}_{direction}' for pose in ('idle', 'walk_a', 'walk_b')
          for direction in ('s', 'e', 'n', 'w')] + ['meditate', 'cast', 'hit', 'guard']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--characters', type=Path, required=True)
    parser.add_argument('--scene-atlas', type=Path, required=True)
    args = parser.parse_args()
    target = ROOT / 'web/assets/pixel/v1'
    target.mkdir(parents=True, exist_ok=True)
    assets = {}
    for gender in ('male', 'female'):
        for kind, source in [('atlas', f'sprites/dao-{gender}.png'),
                             ('portrait', f'portraits/dao-{gender}.png')]:
            name = f'dao-{gender}-{kind}.png'
            shutil.copyfile(args.characters / source, target / name)
            assets[f'actor.human.dao.{gender}.{kind}'] = dict(file=name, size=[384, 384] if kind == 'atlas' else [96, 96])
    # Only the landscape above the baked-in concept character is retained.
    with Image.open(args.scene_atlas) as atlas:
        if atlas.size != (1536, 1024):
            raise ValueError('Expected the reviewed C v2 concept atlas, 1536 x 1024')
        atlas.crop((0, 0, 768, 300)).convert('RGB').save(target / 'human-reverie.png', optimize=True)
    assets['scene.human.reverie'] = dict(file='human-reverie.png', size=[768, 300])
    for row in assets.values():
        row['sha256'] = hashlib.sha256((target / row['file']).read_bytes()).hexdigest()
    catalog = dict(version=1, base='/assets/pixel/v1/', cell=[96, 96], anchor=[48, 84],
                   frames=FRAMES, assets=assets)
    (target / 'catalog.js').write_text('window.PixelAssetCatalog = ' + json.dumps(catalog, ensure_ascii=False, indent=2) + ';\n', encoding='utf-8')
    provenance = dict(generator='OpenAI built-in image_gen', approval='User approved C v2 and character pack v1 with female v2',
                      character_source='pixel-assets-v1-20261020', scene_source='pixel-ui-concepts-20261020/assets/atlas-cultivator-v2.png',
                      scene_crop=[0, 0, 768, 300], usage='Illustrative human-world reverie, not literal geography or an accessible temple',
                      source_hashes={str(p.name): hashlib.sha256(p.read_bytes()).hexdigest() for p in [
                          args.scene_atlas, args.characters / 'manifest.json', args.characters / 'provenance.json']})
    (target / 'provenance.json').write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
