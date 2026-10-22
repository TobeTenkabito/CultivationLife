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
    parser.add_argument('--characters', type=Path)
    parser.add_argument('--scene-atlas', type=Path)
    parser.add_argument('--demonic-characters', type=Path,
                        help='Reviewed demonic-basic-variants-20261021 pack; copy final assets unchanged')
    args = parser.parse_args()
    if bool(args.characters) != bool(args.scene_atlas):
        parser.error('--characters and --scene-atlas must be supplied together')
    if not args.characters and not args.demonic_characters:
        parser.error('Supply the Daoist/scene sources or --demonic-characters')
    target = ROOT / 'web/assets/pixel/v1'
    target.mkdir(parents=True, exist_ok=True)
    catalog_path, provenance_path = target / 'catalog.js', target / 'provenance.json'
    assets = json.loads(catalog_path.read_text(encoding='utf-8').removeprefix(
        'window.PixelAssetCatalog = ').strip().removesuffix(';'))['assets'] if catalog_path.exists() else {}
    provenance = json.loads(provenance_path.read_text(encoding='utf-8')) if provenance_path.exists() else {}
    if args.characters:
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
        provenance.update(generator='OpenAI built-in image_gen', approval='User approved C v2 and character pack v1 with female v2',
                          character_source='pixel-assets-v1-20261020', scene_source='pixel-ui-concepts-20261020/assets/atlas-cultivator-v2.png',
                          scene_crop=[0, 0, 768, 300], usage='Illustrative human-world reverie, not literal geography or an accessible temple',
                          source_hashes={str(p.name): hashlib.sha256(p.read_bytes()).hexdigest() for p in [
                              args.scene_atlas, args.characters / 'manifest.json', args.characters / 'provenance.json']})
    if args.demonic_characters:
        source_root = args.demonic_characters
        manifest = json.loads((source_root / 'manifest.json').read_text(encoding='utf-8'))
        imported = {}
        # Validate all four selected files before copying; never reconstitute discarded drafts.
        for gender in ('male', 'female'):
            actor = manifest['actors'][gender]
            for kind, source_key in [('atlas', 'sheet'), ('portrait', 'portrait')]:
                source = source_root / actor[source_key]
                digest = hashlib.sha256(source.read_bytes()).hexdigest()
                if digest != actor[source_key + '_sha256']:
                    raise ValueError(f'Reviewed asset hash mismatch: {source}')
                size = [384, 384] if kind == 'atlas' else [96, 96]
                with Image.open(source) as image:
                    if image.mode != 'RGBA' or list(image.size) != size:
                        raise ValueError(f'Unexpected reviewed asset format: {source}')
                imported[f'actor.human.demonic.{gender}.{kind}'] = (
                    source, dict(file=f'demonic-{gender}-{kind}.png', size=size, sha256=digest))
        for identity, (source, row) in imported.items():
            shutil.copyfile(source, target / row['file'])
            if identity.endswith('.atlas'):
                row['frames'] = manifest['pose_order']
            assets[identity] = row
        provenance['demonic_characters'] = dict(
            source='demonic-basic-variants-20261021',
            approval='2026-10-22 user requested existing demonic protagonists in HUD and character details',
            processing='Byte-for-byte copy of selected final atlases and same-source portraits; no redraw',
            manifest_sha256=hashlib.sha256((source_root / 'manifest.json').read_bytes()).hexdigest(),
            source_hashes={row['file']: row['sha256'] for _, row in imported.values()},
            reserved_empty_slots=manifest['reserved_empty_slots'],
            usage='Base-game human demonic male/female; static idle_s only, no combat animation adoption')
    for row in assets.values():
        row['sha256'] = hashlib.sha256((target / row['file']).read_bytes()).hexdigest()
    catalog = dict(version=1, base='/assets/pixel/v1/', cell=[96, 96], anchor=[48, 84],
                   frames=FRAMES, assets=assets)
    (target / 'catalog.js').write_text('window.PixelAssetCatalog = ' + json.dumps(catalog, ensure_ascii=False, indent=2) + ';\n', encoding='utf-8')
    (target / 'provenance.json').write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
