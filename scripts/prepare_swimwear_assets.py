"""Pack generated swimwear paintings for runtime; never redraw anatomy or alpha."""
import copy
import json
from pathlib import Path

from PIL import Image
import numpy as np
from scipy import ndimage
from scripts.prepare_monster_static_assets import read, write, sha
from scripts.prepare_monster_flora_assets import pack

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'design/swimwear-20261027'
OUT = ROOT / 'web/assets/pixel/swimwear'
URL = '/assets/pixel/swimwear/'
POSES = ['idle', 'gather', 'release', 'guard', 'brace', 'hit', 'stagger', 'kneel', 'down', 'domain']


def separate(source, rows):
    pixels = np.array(Image.open(source).convert('RGBA'))
    for threshold in (8, 64, 128, 192):
        labels, _ = ndimage.label(pixels[:, :, 3] >= threshold, np.ones((3, 3)))
        sizes = np.bincount(labels.ravel())
        ids = [i for i in range(1, len(sizes)) if sizes[i] > 1000]
        if len(ids) == 12:
            break
    assert len(ids) == 12, (source, len(ids))
    parts = []
    for index in ids:
        keep = ndimage.binary_dilation(labels == index, iterations=4)
        keep &= ~np.isin(labels, [i for i in ids if i != index])
        rgba = pixels.copy()
        rgba[~keep] = 0
        rgba[rgba[:, :, 3] == 0] = 0
        art = Image.fromarray(rgba)
        box = art.getbbox()
        parts.append((art.crop(box), list(box)))
    parts.sort(key=lambda p: (min(rows-1, int((p[1][1]+p[1][3])/2/(pixels.shape[0]/rows))), p[1][0]))
    return parts


def main(source_dir=SOURCE, output_dir=OUT, manifest_key='base.swimwear_manifest'):
    SOURCE, OUT = source_dir, output_dir
    URL = '/assets/pixel/' + OUT.name + '/'
    OUT.mkdir(parents=True, exist_ok=True)
    template = read(ROOT / 'web/assets/pixel/characters-301/manifest.json')['actors']['dao-nascent-hero-female']
    assets, actors, forms, sources = {}, {}, [], []
    prompts = read(SOURCE / 'prompts.json')
    for row in prompts:
        source = SOURCE / row['file']
        ident = row['id']
        static = 'actor.cosmetic.' + ident
        name = row['name'] + ('·男' if row['gender'] == 'male' else '·女')
        parts = separate(source, row['rows'])
        records = {}
        for kind, size, index in [('figure', (256, 288), 9), ('portrait', (128, 128), 10), ('thumbnail', (128, 144), 9)]:
            art, box = parts[index]
            scale = min((size[0]-12)/art.width, (size[1]-16)/art.height)
            art = art.resize((round(art.width*scale), round(art.height*scale)), Image.Resampling.NEAREST)
            canvas = Image.new('RGBA', size)
            canvas.paste(art, ((size[0]-art.width)//2, size[1]-8-art.height))
            target = OUT / f'{ident}-{kind}.png'
            canvas.save(target, optimize=True)
            assets[static+'.'+kind] = dict(file=URL+target.name, size=list(size), sha256=sha(target), requires=[])
            records[kind] = dict(source_rect=box, scale=scale)
        action_parts = parts[:9] + parts[11:]
        scale = min(176/action_parts[0][0].height, 282/max(a.width for a, _ in action_parts), 180/max(a.height for a, _ in action_parts))
        frames = []
        for pose, (art, box) in zip(POSES, action_parts):
            art = art.resize((round(art.width*scale), round(art.height*scale)), Image.Resampling.NEAREST)
            canvas = Image.new('RGBA', (384, 288))
            offset = (192-art.width//2, 256-art.height)
            canvas.paste(art, offset)
            frames.append(canvas)
            records[pose] = dict(source_rect=box, scale=scale, offset=offset)
        packed = pack(frames, OUT / f'{ident}-actions.png')
        packed['sheet'] = URL + f'{ident}-actions.png'
        actor = copy.deepcopy(template)
        for mode, clip in actor['animations'].items():
            clip.update(packed, rects=[packed['rects'][POSES.index(pose)] for pose in clip['poses']])
        actor.update(name=name, faction='cosmetic', sex=row['gender'], energy_color='#8adbd0' if row['min_realm_index'] == 0 else '#c5d4ff')
        if row.get('holiday_effect'):
            actor['holiday_effect'] = row['holiday_effect']
        actors[ident] = actor
        forms.append(dict(name=name, gender=row['gender'], role='hero', scope='all_paths',
                          min_realm_index=row['min_realm_index'], static=static, combat=ident,
                          unlock_label='全道途通用 · 化神期解锁' if row['min_realm_index'] else '全道途通用 · 默认解锁'))
        assets[ident+'.actions'] = dict(file=packed['sheet'], size=packed['size'], sha256=packed['sha256'], requires=[])
        sources.append(dict(id=ident, source=row['file'], sha256=sha(source), rows=row['rows'], exports=records))
    manifest = OUT / 'manifest.json'
    write(manifest, dict(schema_version=1, fps=20, actors=actors,
                         actions=dict(attack=dict(name='结印施法', duration=4.0, contacts=[2.1]))))
    assets[manifest_key] = dict(file=URL+manifest.name, sha256=sha(manifest), requires=[],
                                           combat_actors=list(actors), skin_forms=forms)
    catalog = read(ROOT / 'content/visual_assets.json')
    catalog['assets'].update(assets)
    write(ROOT / 'content/visual_assets.json', catalog)
    write(OUT / 'provenance.json', dict(generator='OpenAI built-in image_gen',
          export='Original painted RGBA, nearest-neighbour packing; no anatomy reconstruction',
          forms=4, static_images=12, painted_keyposes=40, animation_clips=28, sources=sources,
          prompts=[dict(row, source_sha256=sha(SOURCE / row['file'])) for row in prompts]))
    print(f'Exported {manifest_key}: 4 forms, 12 static images, 40 keyposes, 28 clips')


if __name__ == '__main__':
    main()
