"""Export the approved November base heroes into the existing world and replay slots."""
import json
import math
import shutil

import numpy as np
from PIL import Image
from scipy import ndimage

from scripts.prepare_monster_static_assets import ROOT, read, write, sha
from scripts.prepare_combat_assets import pack_frames, SCALE_FILE

DESIGN = ROOT / 'design/demonic-redraw-20261121/v10'
DAO_DESIGN = ROOT / 'design/dao-basic-redraw-20261121/v5'
PIXELS = ROOT / 'web/assets/pixel'
GROUPS = {
    'spell': (3, 'idle ready charge release summon recover'),
    'melee': (3, 'guard jab cross knee kick defend'),
    'response': (2, 'step_a step_b contact recoil'),
    'fall': (2, 'fall0 fall1 fall2 fall3'),
    'world': (3, 'idle_n idle_w meditate walk_a_s walk_a_n walk_a_w walk_b_s walk_b_n walk_b_w'),
    'passing': (2, 'walk_b_s walk_b_n walk_b_w walk_b_e'),
}


DAO_GROUPS = {
    'world': GROUPS['world'],
    'spell': GROUPS['spell'],
    'response': (3, 'guard absorb step_a step_b contact recoil'),
    'fall': GROUPS['fall'],
}


def drawings(sex, group, design=DESIGN):
    columns, names = (DAO_GROUPS if design == DAO_DESIGN else GROUPS)[group]
    stem = 'melee-cutout' if design == DESIGN and (sex, group) == ('female', 'melee') else group
    path = design / 'motion' / f'{sex}-{stem}.png'
    pixels = np.array(Image.open(path).convert('RGBA'))
    alpha = pixels[:, :, 3]
    labels, count = ndimage.label(alpha >= 128, np.ones((3, 3)))
    sizes = np.bincount(labels.ravel(), minlength=count + 1)
    components = [(i, sl) for i, sl in enumerate(ndimage.find_objects(labels), 1) if sizes[i] > 6500]
    names = names.split()
    if len(components) != len(names):
        raise ValueError(f'{path}: expected {len(names)} separate painted figures')
    # Sort by rows first. The last fallen figure can be entirely below the knees
    # of the first one, so splitting the source into equal grid cells clips it.
    components.sort(key=lambda item: item[1][0].start)
    ordered = []
    for start in range(0, len(components), columns):
        ordered.extend(sorted(components[start:start + columns], key=lambda item: item[1][1].start))
    result = {}
    for name, (index, (ys, xs)) in zip(names, ordered):
        x, y = max(0, xs.start-6), max(0, ys.start-6)
        box = [x, y, min(alpha.shape[1], xs.stop+6), min(alpha.shape[0], ys.stop+6)]
        region = np.s_[y:box[3], x:box[2]]
        rgba = pixels[region].copy()
        keep = ndimage.binary_dilation(labels[region] == index, iterations=6)
        rgba[~keep | (rgba[:, :, 3] < 16)] = 0
        art = Image.fromarray(rgba)
        crop = art.getbbox()
        result[name] = (art.crop(crop), dict(source=path.relative_to(ROOT).as_posix(),
                            rect=[x+crop[0], y+crop[1], x+crop[2], y+crop[3]]))
    return result


def scaled(art, factor):
    return art.resize((round(art.width*factor), round(art.height*factor)), Image.Resampling.LANCZOS)


def grounded(art, width, height, floor, center_feet=True):
    pivot = art.width//2
    if center_feet:
        _, feet = np.where(np.asarray(art)[-4:, :, 3] >= 100)
        if feet.size:
            pivot = round((int(feet.min()) + int(feet.max())) / 2)
    left = max(0, min(width-art.width, width//2-pivot))
    if art.width > width or art.height > floor:
        raise ValueError(f'Painted pose {art.size} outside {width} x {floor}')
    out = Image.new('RGBA', (width, height))
    out.paste(art, (left, floor-art.height))
    return out


def combat_poses(sex, design=DESIGN):
    images, records = {}, {}
    groups = ('spell', 'response', 'fall') if design == DAO_DESIGN else ('spell', 'melee', 'response', 'fall')
    for group in groups:
        parts = drawings(sex, group, design)
        reference = next(iter(parts.values()))[0]
        # Walking/standing sheets have different resolutions. Scale each sheet
        # once; crouching, raising a hand or kicking must not resize the body.
        target = {'spell': 176, 'melee': 172, 'response': 176, 'fall': 162}[group]
        calibrated_fall = group == 'fall' and design == DAO_DESIGN
        if calibrated_fall:
            target = 140
            ref = read(SCALE_FILE)['actors'][f'dao-{sex}']['adopted']
        for name, (art, source) in parts.items():
            factor = target / reference.height
            if calibrated_fall:
                factor *= ref['reference_head'] / ref['fall_heads'][int(name[-1])]
            falling = group == 'fall'
            # Defeat clips are stored facing left. The demonic sheet's final
            # drawing already has that orientation.
            if falling and (design == DAO_DESIGN or name != 'fall3'):
                art = art.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            frame = grounded(scaled(art, factor), 384 if falling else 256, 288, 256, not falling)
            images[name] = frame
            records[name] = dict(source, scale=factor, bounds_final=list(frame.getbbox()),
                                 anchor=[frame.width//2, 256])
    return images, records


def breathe(frame, amount):
    # A sub-pixel lean in the upper body, with no motion at the floor.
    skew = amount / 176
    return frame.transform(frame.size, Image.Transform.AFFINE, (1, skew, -256*skew, 0, 1, 0),
                           resample=Image.Resampling.BICUBIC)


def update_combat(data, path='demonic'):
    design = DAO_DESIGN if path == 'dao' else DESIGN
    recipe = read(SCALE_FILE)
    data['scale_contract']['sha256'] = sha(SCALE_FILE)
    sources = data['provenance']
    for row in sources:
        if row['file'] == data['scale_contract']['file']:
            row['sha256'] = sha(SCALE_FILE)
    for sex in ('male', 'female'):
        ident = f'{path}-{sex}'
        actor = data['actors'][ident]
        images, records = combat_poses(sex, design)
        actor['poses'] = records
        release = np.asarray(images['release'])[:, :, 3]
        top = records['release']['bounds_final'][1]
        yy, xx = np.where(release[top:top+75] >= 128)
        tip = int(xx.max())
        actor['release_point'] = [tip, round(top + float(np.median(yy[xx >= tip-1])))]
        ref = recipe['actors'][ident].get('adopted', recipe['actors'][ident])
        actor['scale_reference'] = dict(ref, kind='humanoid', standing_height=176)
        sources[:] = [r for r in sources if not r['output'].startswith(ident+'-')]
        for filename in sorted({r['source'] for r in records.values()}):
            sources.append(dict(file=filename, sha256=sha(ROOT/filename), output=ident+'-combat atlases'))
        variants = {}
        for mode, clip in actor['animations'].items():
            if path == 'dao' and mode == 'treasure':
                continue
            frames = []
            for i, pose in enumerate(clip['poses']):
                name = 'fall'+str(pose['stage']) if mode == 'defeat' else pose['pose']
                # Sample fabric sway on the existing 10 Hz body clock. Once
                # grounded, the last defeat drawing is held still.
                phase = 0 if mode == 'defeat' else round(1.4*math.sin((i//2)*math.pi/11))
                key = (name, phase)
                if key not in variants:
                    variants[key] = breathe(images[name], phase) if phase else images[name]
                frame = variants[key]
                frames.append(frame)
                pose['bounds'] = list(frame.getbbox())
            target = PIXELS/'combat'/f'{ident}-{mode}.png'
            clip.update(pack_frames(frames, target))
            if mode == 'defeat':
                clip['method'] = 'Four painted fall stages with reviewed head calibration'
                clip['scale_calibration'] = [dict(scale=ref['reference_head']/ref['fall_heads'][p['stage']], stage=p['stage'],
                    reference_head=ref['reference_head'], painted_head=ref['fall_heads'][p['stage']])
                    for p in clip['poses']]
        if path == 'dao':
            actor['animations']['treasure'] = actor['animations']['dragon'].copy()


def export_world(sex, poses, world_names, path='demonic'):
    design = DAO_DESIGN if path == 'dao' else DESIGN
    parts = drawings(sex, 'world', design)
    normal = {key: scaled(art, 72 / parts['idle_n'][0].height)
              for key, (art, _) in parts.items() if path == 'dao' or not key.startswith('walk_b_')}
    if path == 'dao':
        for phase in ('walk_a', 'walk_b'):
            scale = 72 / parts[phase+'_s'][0].height
            for direction in ('s', 'n', 'w'):
                name = f'{phase}_{direction}'
                normal[name] = scaled(parts[name][0], scale)
    if path == 'demonic':
        passing = drawings(sex, 'passing')
        for key, (art, _) in passing.items():
            normal[key] = scaled(art, 72 / passing['walk_b_s'][0].height)
    side_poses = [('idle_e', 'idle'), ('walk_a_e', 'step_a')]
    if path == 'dao':
        side_poses.extend([('walk_b_e', 'step_b'), ('cast', 'release'), ('hit', 'recoil'), ('guard', 'guard')])
    for name, pose in side_poses:
        frame = poses[pose]
        normal[name] = scaled(frame.crop(frame.getbbox()), 72 / 176)
    front = Image.open(design/f'{sex}-figure.png')
    front = front.crop(front.getbbox())
    normal['idle_s'] = scaled(front, 72/front.height)
    atlas = Image.new('RGBA', (384, 384))
    for i, name in enumerate(world_names):
        cell = grounded(normal[name], 96, 96, 84)
        cell.putalpha(cell.getchannel('A').point(lambda a: 255 if a >= 110 else 0))
        atlas.paste(cell, (i%4*96, i//4*96))
    target = PIXELS/'v1'/f'{path}-{sex}-atlas.png'
    atlas.save(target, optimize=True)
    return target


def update_static_and_world(path_name='demonic'):
    design = DAO_DESIGN if path_name == 'dao' else DESIGN
    catalog_path = PIXELS/'v1/catalog.js'
    prefix = 'window.PixelAssetCatalog = '
    catalog = json.loads(catalog_path.read_text(encoding='utf-8').removeprefix(prefix).strip().removesuffix(';'))
    path = ROOT/'content/visual_assets.json'
    visuals = read(path)
    provenance = read(PIXELS/'v1/provenance.json')
    selected = provenance['protagonist_static_redraws']['assets']
    hashes = {}
    adopted = {actor['id']: actor for actor in read(design/'manifest.json')['actors']}
    for sex in ('male', 'female'):
        ident = f'{path_name}-{sex}'
        poses, _ = combat_poses(sex, design)
        world_names = catalog['frames'] if path_name == 'dao' else catalog['frames'][:13]
        atlas = export_world(sex, poses, world_names, path_name)
        hashes[atlas.name] = sha(atlas)
        catalog['assets'][f'actor.human.{path_name}.{sex}.atlas']['sha256'] = hashes[atlas.name]
        for kind in ('figure', 'portrait', 'thumbnail'):
            source = design/f'{sex}-{kind}.png'
            digest = sha(source)
            if digest != adopted[ident]['pixel'][kind]['sha256']:
                raise ValueError(f'Selected redraw changed: {source}')
            key = f'actor.path.{path_name}-base-hero-{sex}.{kind}'
            shutil.copyfile(source, PIXELS/'characters-301'/f'{ident}-{kind}.png')
            visuals['assets'][key]['sha256'] = digest
            if kind != 'thumbnail':
                key = f'actor.human.{path_name}.{sex}.{kind}'
                entry = catalog['assets'][key]
                shutil.copyfile(source, PIXELS/'v1'/entry['file'])
                entry['sha256'] = digest
                selected[key] = dict(entry, source=source.relative_to(ROOT).as_posix())
    provenance['protagonist_static_redraws'].update(
        approval='Dao base v5 and demonic base v10 adopted 2026-11-21',
        processing='Byte-for-byte selected static pixel exports')
    inputs = {f'{sex}-{group}.png' for sex in ('male', 'female')
              for group in (DAO_GROUPS if path_name == 'dao' else GROUPS)}
    if path_name == 'demonic':
        inputs.remove('female-melee.png')
        inputs.add('female-melee-cutout.png')
    provenance[path_name+'_characters'] = dict(source=design.relative_to(ROOT).as_posix(),
        source_hashes=hashes, reserved_empty_slots=list(range(len(world_names), 16)),
        static_manifest_sha256=sha(design/'manifest.json'),
        drawing_hashes={name:sha(design/'motion'/name) for name in sorted(inputs)})
    write(PIXELS/'v1/provenance.json', provenance)
    write(path, visuals)
    catalog_path.write_text(prefix+json.dumps(catalog, ensure_ascii=False, indent=2)+';\n', encoding='utf-8')


def main(path_name='demonic'):
    path = PIXELS/'combat/manifest.json'
    data = read(path)
    update_combat(data, path_name)
    write(path, data)
    update_static_and_world(path_name)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--path', choices=('dao', 'demonic'), default='demonic')
    main(parser.parse_args().path)
