"""Offline, deterministic pixel export of the selected avian/ape paired originals.

This script needs local design sources; the game only needs the shipped DLC files.
It never regenerates art or rewrites the existing fox/serpent derivatives.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
OWNER = 'official.monster-bloodlines'
RECIPE = ROOT / 'scripts/monster_static_sources.json'
SIZES = {'portrait': (128, 128), 'figure': (256, 288), 'thumbnail': (128, 144)}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def paired_parts(path, threshold=8):
    rgba = np.array(Image.open(path).convert('RGBA'))
    labels, _ = ndimage.label(rgba[:, :, 3] >= threshold, np.ones((3, 3)))
    sizes = np.bincount(labels.ravel())
    ids = [i for i in range(1, len(sizes)) if sizes[i] > 1000]
    assert len(ids) == 2, (path, len(ids))
    parts = []
    for index in ids:
        # Identify bodies with alpha, but preserve the source's soft transparency.
        keep = ndimage.binary_dilation(labels == index, iterations=4)
        keep &= ~np.isin(labels, [i for i in ids if i != index])
        pixels = rgba.copy()
        pixels[~keep] = 0
        pixels[pixels[:, :, 3] == 0] = 0
        image = Image.fromarray(pixels)
        box = image.getbbox()
        parts.append((image.crop(box), list(box)))
    parts.sort(key=lambda p: p[1][0])
    return parts


def export(identity, source, out, url, threshold=8):
    parts = paired_parts(source, threshold)
    rows = {}
    for kind, size in SIZES.items():
        art = parts[1 if kind == 'portrait' else 0][0]
        scale = min((size[0]-12)/art.width, (size[1]-16)/art.height)
        scaled = art.resize((round(art.width*scale), round(art.height*scale)), Image.Resampling.NEAREST)
        canvas = Image.new('RGBA', size)
        canvas.paste(scaled, ((size[0]-scaled.width)//2, size[1]-8-scaled.height))
        box = canvas.getbbox()
        assert box and 0 < box[0] < box[2] < size[0] and 0 < box[1] < box[3] < size[1]
        target = out / f'{identity}-{kind}.png'
        canvas.save(target, optimize=True)
        rows[kind] = dict(file=url+target.name, size=list(size), sha256=sha(target), requires=[OWNER])
    return rows, [box for _, box in parts]


def main():
    recipe = read(RECIPE)
    nodes = {n['id']: n for n in read(ROOT/'dlc/monster-bloodlines/content/monster_bloodlines.json')['evolutions']}
    catalog = read(ROOT/'content/visual_assets.json')
    previous = {p: sha(p) for species in ['fox', 'serpent']
                for p in (ROOT/f'dlc/monster-bloodlines/assets/visual/{species}').rglob('*') if p.is_file()}
    for species, spec in recipe['species'].items():
        out = ROOT/f'dlc/monster-bloodlines/assets/visual/{species}'
        out.mkdir(parents=True, exist_ok=True)
        url = f'/extension-assets/{OWNER}/visual/{species}/'
        assets, actors, sources, variants = {}, {}, [], {}
        for a in spec['sources']:
            source = ROOT/a['file']
            assert sha(source) == a['sha256'], source
            node = nodes[a['node']]
            assert node['species'] == species and node['realm_index'] == a['realm']
            rows, boxes = export(a['identity'], source, out, url, a.get('component_threshold', 8))
            for kind, row in rows.items():
                assets[f"actor.monster.{a['identity']}.{kind}"] = row
            actors[a['identity']] = dict(name=a['name'], gender=a['gender'], node=a['node'],
                                         realm=a['realm'], assets=rows)
            variants.setdefault(a['node'], {})[a['gender']] = a['identity']
            sources.append(dict(a, subject_bounds=boxes))
        rules = {}
        for node_id, node in nodes.items():
            if node['species'] != species or node['realm_index'] > 8:
                continue
            realm = node['realm_index']
            rule = dict(realm=realm)
            if realm < 3:
                rule.update(static=variants[species.upper()+'_SPIRIT']['shared'], combat=None)
            elif node_id in variants:
                if 'shared' in variants[node_id]:
                    rule.update(static=variants[node_id]['shared'], combat=None)
                else:
                    rule['variants'] = variants[node_id]
            elif node_id in spec['aliases']:
                rule['variants'] = variants[spec['aliases'][node_id]]
            elif realm in (5, 6):
                # Only actual ancestral Nascent nodes may supply the retained art.
                pending, ancestors = list(node['parents']), set()
                while pending:
                    parent = pending.pop()
                    if parent in ancestors:
                        continue
                    ancestors.add(parent)
                    pending.extend(nodes[parent]['parents'])
                rule['history_variants'] = {n: variants[n] for n in sorted(ancestors)
                                            if n in variants and nodes[n]['realm_index'] == 4}
                assert rule['history_variants'], node_id
            else:
                raise AssertionError(('Unreviewed node mapping', node_id))
            rules[node_id] = rule
        assert len(actors) == spec['count']
        write(out/'manifest.json', dict(schema_version=1, owner=OWNER, scope='static_only',
              actors=actors, nodes=rules, history_routes={}))
        assets[f'monster.{species}.static_manifest'] = dict(
            file=url+'manifest.json', requires=[OWNER], sha256=sha(out/'manifest.json'))
        write(out/'registry.json', dict(assets=assets))
        write(out/'provenance.json', dict(authorization=recipe['authorization'],
              processing='deterministic component extraction and nearest-neighbour resize; original soft alpha',
              original_generator='OpenAI built-in image_gen', new_generation=False,
              source_recipe='scripts/monster_static_sources.json', static_forms=len(actors), sources=sources))
        catalog['assets'].update(assets)
        print(f'{species}: {len(actors)} forms / {len(actors)*3} static PNGs')
    from scripts.prepare_monster_release_assets import main as promote_and_assemble
    promote_and_assemble()
    assert all(sha(p) == digest for p, digest in previous.items()), 'Existing derivatives changed'
    print('Fox/serpent files preserved byte-for-byte; approved actions reattached; DLC registry refreshed')


if __name__ == '__main__':
    main()
