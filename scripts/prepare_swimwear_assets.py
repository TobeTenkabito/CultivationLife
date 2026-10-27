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


def separate(source, rows, count=12):
    pixels = np.array(Image.open(source).convert('RGBA'))
    for threshold in (8, 64, 128, 192):
        labels, _ = ndimage.label(pixels[:, :, 3] >= threshold, np.ones((3, 3)))
        sizes = np.bincount(labels.ravel())
        ids = [i for i in range(1, len(sizes)) if sizes[i] > 1000]
        if len(ids) == count:
            break
    assert len(ids) == count, (source, len(ids), count)
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
        gun = row.get('layout') == 'gunslinger'
        parts = separate(source, row['rows'], 16 if gun else 12)
        figure_index, portrait_index = (12, 13) if gun else (9, 10)
        records = {}
        for kind, size, index in [('figure', (256, 288), figure_index), ('portrait', (128, 128), portrait_index), ('thumbnail', (128, 144), figure_index)]:
            art, box = parts[index]
            scale = min((size[0]-12)/art.width, (size[1]-16)/art.height)
            art = art.resize((round(art.width*scale), round(art.height*scale)), Image.Resampling.NEAREST)
            canvas = Image.new('RGBA', size)
            canvas.paste(art, ((size[0]-art.width)//2, size[1]-8-art.height))
            target = OUT / f'{ident}-{kind}.png'
            canvas.save(target, optimize=True)
            assets[static+'.'+kind] = dict(file=URL+target.name, size=list(size), sha256=sha(target), requires=[])
            records[kind] = dict(source_rect=box, scale=scale)
        action_parts = parts[:12] + parts[14:] if gun else parts[:9] + parts[11:]
        poses = (['idle','gather','aim','release','recoil','recover','guard','brace',
                  'hit','stagger','kneel','down','domain','holster'] if gun else POSES)
        scale = min(176/action_parts[0][0].height, 282/max(a.width for a, _ in action_parts), 180/max(a.height for a, _ in action_parts))
        frames = []
        for pose, (art, box) in zip(poses, action_parts):
            art = art.resize((round(art.width*scale), round(art.height*scale)), Image.Resampling.NEAREST)
            canvas = Image.new('RGBA', (384, 288))
            offset = (192-art.width//2, 256-art.height)
            canvas.paste(art, offset)
            frames.append(canvas)
            records[pose] = dict(source_rect=box, scale=scale, offset=offset)
        packed = pack(frames, OUT / f'{ident}-actions.png')
        packed['sheet'] = URL + f'{ident}-actions.png'
        actor = copy.deepcopy(template)
        if gun:
            # Painted draw/aim/fire/recoil/recover/holster sequence on the existing
            # 4-second attack clock; the one authoritative contact stays at 2.1s.
            attack = actor['animations']['attack']
            stages = [(0.4,'idle'),(1.2,'gather'),(2.,'aim'),(2.15,'release'),
                      (2.45,'recoil'),(2.85,'recover'),(3.5,'holster'),(4.1,'idle')]
            attack['poses'] = [next(p for end,p in stages if i/20<end) for i in range(81)]
            actor['cast_effect'] = 'revolver'
            shot = frames[poses.index('release')]
            bounds = shot.getbbox()
            uv = row.get('muzzle_uv', [.98,.28])
            actor['release_point'] = [round(bounds[0]+(bounds[2]-bounds[0])*uv[0]),
                                      round(bounds[1]+(bounds[3]-bounds[1])*uv[1])]
        for mode, clip in actor['animations'].items():
            clip.update(packed, rects=[packed['rects'][poses.index(pose)] for pose in clip['poses']])
        if gun:
            actor['attack_action'] = 'revolver'
            actor['animations']['revolver'] = actor['animations'].pop('attack')
        actor.update(name=name, faction='cosmetic', sex=row['gender'], energy_color='#8adbd0' if row['min_realm_index'] == 0 else '#c5d4ff')
        if row.get('holiday_effect'):
            actor['holiday_effect'] = row['holiday_effect']
        actors[ident] = actor
        forms.append(dict(name=name, gender=row['gender'], role='hero', scope='all_paths',
                          min_realm_index=row['min_realm_index'], static=static, combat=ident,
                          unlock_label={0:'全道途通用 · 默认解锁',5:'全道途通用 · 化神期解锁',7:'全道途通用 · 合体期解锁'}[row['min_realm_index']]))
        assets[ident+'.actions'] = dict(file=packed['sheet'], size=packed['size'], sha256=packed['sha256'], requires=[])
        sources.append(dict(id=ident, source=row['file'], sha256=sha(source), rows=row['rows'], exports=records))
    manifest = OUT / 'manifest.json'
    actions = dict(attack=dict(name='结印施法', duration=4.0, contacts=[2.1]))
    if any(row.get('layout') == 'gunslinger' for row in prompts):
        actions['revolver'] = dict(name='拔枪射击', duration=4.0, contacts=[2.1])
    write(manifest, dict(schema_version=1, fps=20, actors=actors, actions=actions))
    assets[manifest_key] = dict(file=URL+manifest.name, sha256=sha(manifest), requires=[],
                                           combat_actors=list(actors), skin_forms=forms)
    catalog = read(ROOT / 'content/visual_assets.json')
    catalog['assets'].update(assets)
    write(ROOT / 'content/visual_assets.json', catalog)
    pose_count = sum(14 if row.get('layout') == 'gunslinger' else 10 for row in prompts)
    write(OUT / 'provenance.json', dict(generator='OpenAI built-in image_gen',
          export='Original painted RGBA, nearest-neighbour packing; no anatomy reconstruction',
          forms=len(prompts), static_images=len(prompts)*3, painted_keyposes=pose_count, animation_clips=len(prompts)*7, sources=sources,
          prompts=[dict(row, source_sha256=sha(SOURCE / row['file'])) for row in prompts]))
    print(f'Exported {manifest_key}: {len(prompts)} forms, {pose_count} keyposes')


if __name__ == '__main__':
    main()
