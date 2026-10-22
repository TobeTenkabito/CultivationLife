"""Promote approved social art verbatim. Offline authoring only, never a build prerequisite."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixed', type=Path, required=True)
    parser.add_argument('--generic', type=Path, required=True)
    args = parser.parse_args()
    target = ROOT / 'web/assets/pixel/social'
    target.mkdir(parents=True, exist_ok=True)
    approval = read(args.fixed / 'approval.json')
    for name, digest in approval['frozen_files'].items():
        assert sha(args.fixed / name) == digest, name
    generic_approval = read(args.generic / 'approval.json')
    for name, digest in generic_approval['sources'].items():
        assert sha(args.generic / name) == digest, name
    manifest = read(args.fixed / 'manifest.json')
    actors, fixed, pools = {}, {}, {}
    def promote(source, row, key):
        entry = {field: row[field] for field in ('path', 'gender')}
        entry['race'] = row.get('race', 'human')
        for kind in ('figure', 'portrait'):
            asset = row['pixel'][kind]
            origin = source / asset['file']
            assert sha(origin) == asset['sha256'], origin
            name = f'{key}-{kind}.png'
            shutil.copyfile(origin, target / name)
            with Image.open(origin) as image:
                entry[kind] = dict(file=name, sha256=sha(origin), size=list(image.size))
        actors[key] = entry
    for row in manifest['actors']:
        if row['id'] not in approval['approved_ids']:
            continue
        assert row['status'] == 'approved'
        key = 'fixed-' + row['id']
        promote(args.fixed, row, key)
        fixed[row['id']] = key
        if row.get('art_gender_override'):
            actors[key]['art_gender_override'] = row['art_gender_override']
    for row in read(args.generic / 'pixel-manifest.json')['actors']:
        key = 'generic-' + row['id']
        promote(args.generic, row, key)
        pools.setdefault(f"human.{row['path']}.{row['gender']}", []).append(key)
    result = dict(schema=1, base='/assets/pixel/social/', actors=actors, fixed=fixed, pools=pools,
                  reserved_fixed_ids=[a['id'] for a in manifest['actors']],
                  event_participants={'EVT_XIANG_NODE_001':['xiang_zhili']})
    (target / 'catalog.js').write_text('window.NpcArtCatalog = ' + json.dumps(result, ensure_ascii=False) + ';\n', encoding='utf-8')
    (target / 'provenance.json').write_text(json.dumps(dict(
        tool='built-in image_gen', usage='Approved static social figures and portraits; no combat animation',
        fixed_approval=approval['user_statement'], clarification=approval['clarification'],
        integration_authorization=approval['runtime_authorization'],
        generic_approval=generic_approval['user_instruction'], pending_excluded=approval['pending_redraw_ids'],
        fixed_count=len(fixed), generic_count=sum(map(len,pools.values())),
        files={v[k]['file']:v[k]['sha256'] for v in actors.values() for k in ('figure','portrait')},
    ), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f'Promoted {len(fixed)} fixed and {sum(map(len,pools.values()))} generic pairs')

if __name__ == '__main__':
    main()
