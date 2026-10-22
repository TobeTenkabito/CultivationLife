"""Promote the four selected static redraws without touching action atlases."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main():
    target = ROOT / 'web/assets/pixel/v1'
    catalog_path = target / 'catalog.js'
    catalog = json.loads(catalog_path.read_text(encoding='utf-8').removeprefix(
        'window.PixelAssetCatalog = ').strip().removesuffix(';'))
    provenance_path = target / 'provenance.json'
    provenance = json.loads(provenance_path.read_text(encoding='utf-8'))
    selected = []
    for path in ('dao', 'demonic'):
        source_root = ROOT / f'design/{path}-basic-redraw-20261022'
        manifest = json.loads((source_root / 'manifest.json').read_text(encoding='utf-8'))
        for actor in manifest['actors']:
            identity = actor['id']
            for kind, size in [('figure', [256, 288]), ('portrait', [128, 128])]:
                source = source_root / actor['pixel'][kind]['file']
                digest = hashlib.sha256(source.read_bytes()).hexdigest()
                if digest != actor['pixel'][kind]['sha256']:
                    raise ValueError(f'Selected redraw changed: {source}')
                with Image.open(source) as image:
                    if image.mode != 'RGBA' or list(image.size) != size:
                        raise ValueError(f'Invalid selected redraw: {source}')
                selected.append((source, f'actor.human.{identity.replace("-", ".")}.{kind}',
                    dict(file=f'{identity}-static-{kind}.png', size=size, sha256=digest,
                         source=source.relative_to(ROOT).as_posix())))
    for source, identity, row in selected:
        shutil.copyfile(source, target / row['file'])
        catalog['assets'][identity] = {k: v for k, v in row.items() if k != 'source'}
    provenance['protagonist_static_redraws'] = dict(
        approval='2026-10-23 user explicitly requires the new protagonist portraits and full-body art',
        processing='Byte-for-byte selected pixel exports; separate static figures, action atlases unchanged',
        assets={identity: row for _, identity, row in selected})
    catalog_path.write_text('window.PixelAssetCatalog = ' + json.dumps(catalog, ensure_ascii=False, indent=2) + ';\n', encoding='utf-8')
    provenance_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Imported {len(selected)} selected static protagonist assets')


if __name__ == '__main__':
    main()
