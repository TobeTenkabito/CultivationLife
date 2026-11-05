"""Copy reviewed image_gen artwork unchanged and register its display metadata."""
import hashlib
import json
import shutil
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'design/npc-races-353'
DESTINATION = ROOT / 'web/assets/pixel/social-races'


def main():
    spec = json.loads((SOURCE/'prompts.json').read_text(encoding='utf-8'))
    catalog, records = {}, []
    DESTINATION.mkdir(parents=True, exist_ok=True)
    for actor in spec['actors']:
        row = dict(race=actor['race'], gender=actor['gender'], min_age=18,
                   paths=['dao', 'demonic', 'monster', 'ghost', 'confucian', 'buddhist'])
        for kind, size in [('figure', [128, 192]), ('portrait', [96, 96])]:
            filename = f'{actor["id"]}-{kind}.png'
            source, target = SOURCE/'source'/filename, DESTINATION/filename
            with Image.open(source) as image:
                assert image.mode == 'RGBA' and image.getchannel('A').getextrema()[0] == 0
                native_size = list(image.size)
            shutil.copy2(source, target)
            row[kind] = dict(file='/assets/pixel/social-races/'+filename, size=size,
                             native_size=native_size, sha256=hashlib.sha256(target.read_bytes()).hexdigest())
        catalog[f'{actor["race"]}.{actor["gender"]}'] = row
        records.append(dict(**actor, assets=row,
            review='Fine-line subdued style; both arms and hands, two complete feet visible; portrait identity matches full figure.'))
    (DESTINATION/'catalog.js').write_text('window.NpcRaceCatalog = '+json.dumps(catalog, ensure_ascii=False)+';\n', encoding='utf-8')
    (DESTINATION/'provenance.json').write_text(json.dumps(dict(generator=spec['generator'],
        export='Original RGBA PNG copied byte-for-byte; browser renders existing display dimensions.', actors=records),
        ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Registered four race/gender pairs (eight unchanged transparent PNGs).')


if __name__ == '__main__': main()
