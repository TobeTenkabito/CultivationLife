"""Export the approved base character sheets without altering painted anatomy."""
import importlib.util
import json
from pathlib import Path

from PIL import Image
import numpy as np
from scipy import ndimage
from scripts.prepare_monster_static_assets import read, write, sha
from scripts.prepare_monster_flora_assets import pack

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / 'design/characters-301'
OUT = ROOT / 'web/assets/pixel/characters-301'
URL = '/assets/pixel/characters-301/'
POSES = ['idle', 'gather', 'release', 'guard', 'brace', 'hit', 'stagger', 'kneel', 'down', 'domain']


def separate_sheet(source):
    pixels = np.array(Image.open(source).convert('RGBA'))
    # Ignore translucent contact specks only while IDENTIFYING separate poses.
    # Export pixels keep their original RGBA, including the soft edge alpha.
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
    parts.sort(key=lambda p: (min(3, int((p[1][1] + p[1][3]) / 2 / (pixels.shape[0] / 4))), p[1][0]))
    return parts


def main():
    spec = importlib.util.spec_from_file_location('character_pose_tools', ROOT / 'design/flora-combat-alpha4-20261024/prepare.py')
    motion = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(motion)
    OUT.mkdir(parents=True, exist_ok=True)
    assets, actors, forms, sources = {}, {}, [], []
    for row in read(DESIGN / 'adopted-prompts.json'):
        source = DESIGN / row['file']
        path, stage, gender = row['id'].split('-')
        ident = f'{path}-{stage}-hero-{gender}'
        static = 'actor.path.' + ident
        name = ('元婴' if stage == 'nascent' else '合体') + ('道修' if path == 'dao' else '魔修') + ('·男' if gender == 'male' else '·女')
        parts = separate_sheet(source)
        records = {}
        for kind, size, index in [('figure', (256, 288), 9), ('portrait', (128, 128), 10), ('thumbnail', (128, 144), 9)]:
            art, box = parts[index]
            scale = min((size[0] - 12) / art.width, (size[1] - 16) / art.height)
            art = art.resize((round(art.width * scale), round(art.height * scale)), Image.Resampling.NEAREST)
            canvas = Image.new('RGBA', size)
            canvas.paste(art, ((size[0] - art.width) // 2, size[1] - 8 - art.height))
            target = OUT / f'{ident}-{kind}.png'
            canvas.save(target, optimize=True)
            assets[static + '.' + kind] = dict(file=URL + target.name, size=list(size), sha256=sha(target), requires=[])
            records[kind] = dict(source_rect=box, scale=scale)
        action_parts = parts[:9] + parts[11:]
        scale = min(176 / action_parts[0][0].height, 282 / max(a.width for a, _ in action_parts), 180 / max(a.height for a, _ in action_parts))
        frames = []
        for pose, (art, box) in zip(POSES, action_parts):
            art = art.resize((round(art.width * scale), round(art.height * scale)), Image.Resampling.NEAREST)
            canvas = Image.new('RGBA', (384, 288))
            offset = (192 - art.width // 2, 256 - art.height)
            canvas.paste(art, offset)
            target = DESIGN / 'poses' / ident / f'{pose}.png'
            target.parent.mkdir(parents=True, exist_ok=True)
            canvas.save(target, optimize=True)
            frames.append(canvas)
            records[pose] = dict(source_rect=box, scale=scale, offset=offset)
        packed = pack(frames, OUT / f'{ident}-actions.png')
        packed['sheet'] = URL + f'{ident}-actions.png'
        clips = json.loads(json.dumps(motion.CLIPS))
        clips['domain']['keys'][2][1] = 'domain'
        animations = {}
        for action, clip in clips.items():
            indices = [POSES.index(next(p for start, p in reversed(clip['keys']) if at / 20 >= start)) for at in range(round(clip['duration'] * 20) + 1)]
            animations[action] = dict(packed, rects=[packed['rects'][i] for i in indices], frames=len(indices), poses=[POSES[i] for i in indices], duration=clip['duration'], facing=1, cell=[384, 288], body_sample_fps=10)
        actors[ident] = dict(name=name, role='hero', faction=path, creature=False, sex=gender, cell=[384, 288], anchor=[192, 256], attack_action='attack', domain_action='domain', release_point=[235, 152], energy_color='#8adbd0' if path == 'dao' else '#db717f', energy_effect=True, hit_offset=[23, -85], guard_shape=dict(cx=4, cy=-86, rx=70, ry=94), animations=animations)
        forms.append(dict(name=name, path=path, race='human', gender=gender, role='hero', min_realm_index=4 if stage == 'nascent' else 7, static=static, combat=ident))
        assets[ident + '.actions'] = dict(file=packed['sheet'], size=packed['size'], sha256=packed['sha256'], requires=[])
        sources.append(dict(id=ident, source=row['file'], sha256=sha(source), exports=records))
    manifest = OUT / 'manifest.json'
    write(manifest, dict(schema_version=1, version='3.0.1', fps=20, actors=actors,
                         actions=dict(attack=dict(name='结印施法', duration=4.0, contacts=[2.1]))))
    base_skins = []
    for path in ['dao', 'demonic']:
        for gender in ['male', 'female']:
            ident = f'{path}-{gender}'
            static = f'actor.path.{path}-base-hero-{gender}'
            for kind, size in [('figure', (256, 288)), ('portrait', (128, 128)), ('thumbnail', (128, 144))]:
                source = ROOT / f'web/assets/pixel/v1/{ident}-static-{ "figure" if kind == "thumbnail" else kind}.png'
                target = OUT / f'{ident}-{kind}.png'
                art = Image.open(source).convert('RGBA')
                if kind == 'thumbnail':
                    art = art.resize(size, Image.Resampling.NEAREST)
                art.save(target, optimize=True)
                assets[static + '.' + kind] = dict(file=URL + target.name, size=list(art.size), sha256=sha(target), requires=[])
            base_skins.append(dict(name=('道修' if path == 'dao' else '魔修') + '·初行' + ('·男' if gender == 'male' else '·女'), path=path, race='human', gender=gender, role='hero', static=static, combat=ident))
    assets['base.character_manifest'] = dict(file=URL + manifest.name, sha256=sha(manifest), requires=[], combat_actors=list(actors), character_forms=forms, skin_forms=base_skins)
    catalog = read(ROOT / 'content/visual_assets.json')
    for path in ['dao', 'demonic']:
        for gender in ['male', 'female']:
            for kind in ['portrait', 'figure', 'thumbnail']:
                catalog['assets'].pop(f'actor.{path}-{gender}.{kind}', None)
    catalog['assets'].update(assets)
    write(ROOT / 'content/visual_assets.json', catalog)
    write(OUT / 'provenance.json', dict(generator='OpenAI built-in image_gen', prompts=['design/characters-301/adopted-prompts.json'], forms=8, painted_keyposes=80, animation_clips=56, sources=sources))
    print('Exported 8 forms, 80 keyposes, 56 clips and 12 base static images')


if __name__ == '__main__':
    main()
