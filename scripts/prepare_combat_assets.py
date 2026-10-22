"""Export reviewed combat bitmaps; never run during startup or packaging."""
import hashlib
import json
import math
from pathlib import Path

from PIL import Image
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'web/assets/pixel/combat'
SCALE_FILE = ROOT/'scripts/combat_asset_scale.json'
SCALES = json.loads(SCALE_FILE.read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_fall(identity, frames, poses):
    """Correct painted scale once per key pose, keeping the floor anchor fixed."""
    reference = SCALES['actors'][identity]
    output, records = [], []
    for frame, pose in zip(frames, poses):
        stage = pose.get('stage', 0)
        # Short hit lead-ins already use the normal, calibrated combat body.
        factor = (reference['reference_head']/reference['fall_heads'][stage]
                  if pose['pose'] == 'defeat' else 1.)
        if factor == 1:
            output.append(frame)
        else:
            anchor = pose['anchor']
            bounds = frame.getbbox()
            crop = frame.crop(bounds)
            small = crop.resize((round(crop.width*factor), round(crop.height*factor)), Image.Resampling.NEAREST)
            offset = [round(anchor[i]+(bounds[i]-anchor[i])*factor) for i in range(2)]
            # Round from the common floor, not independently from the top edge.
            offset[1] = anchor[1]-small.height if bounds[3] == anchor[1] else offset[1]
            assert min(offset) >= 0 and offset[0]+small.width <= frame.width and offset[1]+small.height <= frame.height
            normalized = Image.new('RGBA', frame.size)
            normalized.paste(small, offset)
            output.append(normalized)
        records.append(dict(scale=factor, stage=stage, reference_head=reference['reference_head'],
                            painted_head=reference['fall_heads'][stage] if pose['pose']=='defeat' else reference['reference_head']))
    return output, records


def body_sample(index, count, poses=None):
    # Local pixel breathing/cloth motion is sampled at 10 Hz; the timeline and
    # effects remain 20 Hz. Keep every painted pose/anchor transition exactly.
    if index % 2 == 0 or index == count - 1:
        return index
    if poses and any(poses[index].get(key) != poses[index-1].get(key) for key in ('pose', 'stage', 'anchor')):
        return index
    return index - 1


def pack_frames(frames, target):
    unique, lookup, records = [], {}, []
    for frame in frames:
        box = frame.getbbox() or (0, 0, 1, 1)
        crop = frame.crop(box)
        key = (crop.size, crop.tobytes())
        if key not in lookup:
            lookup[key] = len(unique)
            unique.append(crop)
        records.append((lookup[key], box))
    tw, th = max(im.width for im in unique), max(im.height for im in unique)
    columns = min(len(unique), max(1, 2048 // tw))
    atlas = Image.new('RGBA', (columns*tw, math.ceil(len(unique)/columns)*th))
    for i, im in enumerate(unique):
        atlas.paste(im, (i % columns*tw, i//columns*th))
    atlas.save(target, optimize=True)
    return dict(rects=[[i % columns*tw, i//columns*th, b[2]-b[0], b[3]-b[1], b[0], b[1]] for i, b in records],
                sheet='/assets/pixel/combat/'+target.name, size=list(atlas.size), sha256=digest(target))


def add_defeats(actors, data, sources):
    fall_root = ROOT/'design/defeat-animation-study-20261022'
    falls = json.loads((fall_root/'animation.json').read_text(encoding='utf-8'))
    roster_root = ROOT/'design/defeat-roster-20261022'
    roster = json.loads((roster_root/'manifest.json').read_text(encoding='utf-8'))
    roster = {actor['id']: actor for actor in roster['actors']}
    for identity, actor in actors.items():
        target = OUT/f'{identity}-defeat.png'
        if identity in falls['actors']:
            item = falls['actors'][identity]
            path = fall_root/item['sheet']
            assert digest(path) == item['sha256']
            for key in item['keys']:
                assert digest(ROOT/'design'/key['file']) == key['sha256']
            original = Image.open(path).convert('RGBA')
            frames = [original.crop((i % 8*384, i//8*288, i % 8*384+384, i//8*288+288)) for i in range(len(item['frames']))]
            poses = [dict(pose='defeat', anchor=[192,256], stage=sample['stage']) for sample in item['frames']]
            sources.append(dict(file=path.relative_to(ROOT).as_posix(), sha256=digest(path), output=target.name))
            duration = falls['duration']
            method = 'selected painted fall stages with bounded local pixel motion'
        else:
            # NPCs keep their own complete painted down pose. The short impact
            # lead-in reuses their own hit clip, never a protagonist's anatomy.
            item = roster[identity]
            source = roster_root/item['source']
            assert digest(source) == item['source_sha256']
            path = roster_root/item['pose']
            assert digest(path) == item['pose_sha256']
            down = Image.open(path).convert('RGBA')
            group = actor['animations']['hit']
            hit = Image.open(ROOT/'web'/group['sheet'].lstrip('/')).convert('RGBA')
            cw, ch = actor.get('cell', data['cell'])
            frames, poses = [], []
            for i in range(25):
                if i < 4:
                    at = min(group['frames']-1, 12+i)
                    x,y,w,h,dx,dy = group['rects'][at]
                    frame = Image.new('RGBA', (384,288))
                    full = Image.new('RGBA', (cw,ch))
                    full.paste(hit.crop((x,y,x+w,y+h)), (dx,dy))
                    full = full.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                    frame.paste(full, (192-(cw-actor.get('anchor',data['anchor'])[0]), 0))
                else:
                    raw = np.asarray(down)
                    y,x = np.indices(raw.shape[:2], dtype=float)
                    age = (i-4)/data['fps']
                    envelope = max(0,1-age/.65)**2
                    torso = np.exp(-((x-160)/56)**2-((y-217)/25)**2)
                    dy = 2.5*math.sin(age*14)*envelope*torso*np.clip((254-y)/16,0,1)
                    sy = np.clip(np.floor(y-dy+.5).astype(int),0,287)
                    pixels = raw[sy,np.arange(384)[None,:]].copy()
                    pixels[pixels[:,:,3]==0] = 0
                    frame = Image.fromarray(pixels)
                frames.append(frame)
                poses.append(dict(pose='hit' if i<4 else 'defeat', anchor=[192,256]))
            sources.extend([dict(file=path.relative_to(ROOT).as_posix(), sha256=digest(path), output=target.name),
                            dict(file=source.relative_to(ROOT).as_posix(), sha256=digest(source), output=target.name)])
            duration = 1.2
            method = 'own hit lead-in and own painted down pose, limited impact settling; no invented intermediate anatomy'
        indices = [body_sample(i, len(frames), poses) for i in range(len(frames))]
        frames, poses = [frames[i] for i in indices], [poses[i] for i in indices]
        frames, calibration = normalize_fall(identity, frames, poses)
        actor['animations']['defeat'] = dict(**pack_frames(frames,target), frames=len(frames), poses=poses,
            cell=[384,288], facing=-1, duration=duration, method=method, scale_calibration=calibration)


def add_support(actors, data, sources):
    base = ROOT/'design/support-cast-study-20261022'
    support = json.loads((base/'manifest.json').read_text(encoding='utf-8'))
    for identity, item in support['actors'].items():
        path = base/item['sheet']
        assert digest(path) == item['sha256']
        source = Image.open(path).convert('RGBA')
        cw, ch = support['cell']
        frames = [source.crop((i%8*cw, i//8*ch, i%8*cw+cw, i//8*ch+ch)) for i in range(item['unique_frames'])]
        sampled = {}
        critical = {round(t*support['fps']) for t in [.25,.4,.55,.65,1.25,1.35,1.85,1.95,2.35,2.55,3.05,3.45,3.6]}
        for mode in ('idle', 'attack', 'hit', 'brace'):
            clip = item['animations'][mode]['frames']
            sampled[mode] = [clip[i if i in critical else body_sample(i,len(clip))] for i in range(len(clip))]
        used = sorted({index for indices in sampled.values() for index in indices})
        packed = pack_frames([frames[i] for i in used], OUT/f'{identity}.png')
        lookup = {old: packed['rects'][new] for new,old in enumerate(used)}
        clips = {}
        for mode in ('idle', 'attack', 'hit', 'brace'):
            clip = item['animations'][mode]
            clips[mode] = dict(packed, rects=[lookup[i] for i in sampled[mode]],
                frames=len(clip['frames']), duration=clip['duration'],
                poses=[dict(pose=mode, anchor=support['anchor']) for _ in clip['frames']])
        # A finite hit lead-in and the selected down endpoint, never a fabricated
        # skeleton fall or replacement of the complete painted lower body.
        down = frames[item['animations']['down']['frames'][0]]
        hit = item['animations']['hit']['frames']
        fall_frames = [frames[hit[12+i]] if i < 4 else down for i in range(25)]
        target = OUT/f'{identity}-defeat.png'
        fall_poses = [dict(pose='hit' if i<4 else 'defeat', anchor=support['anchor']) for i in range(25)]
        fall_frames, calibration = normalize_fall(identity, fall_frames, fall_poses)
        clips['defeat'] = dict(**pack_frames(fall_frames, target), frames=25, duration=1.2,
            cell=support['cell'], facing=1,
            poses=fall_poses, scale_calibration=calibration,
            method='own hit lead-in and selected complete down endpoint; no invented fall intermediates')
        release = Image.open(base/item['poses']['release']['path']).convert('RGBA')
        a = np.array(release)
        y,x = np.indices(a.shape[:2])
        top = release.getbbox()[1]
        yy,xx = np.where((a[:,:,3]>0)&(y>top+(256-top)*.15)&(y<top+(256-top)*.48)&(x>192))
        tip = int(xx.max())
        kind = item['kind']
        faction = 'mechanical' if kind == 'puppet' else kind
        actors[identity] = dict(name=item['name'], role='npc', faction=faction,
            sex=identity.rsplit('-',1)[1] if identity!='mechanical-puppet' else None,
            cell=support['cell'], anchor=support['anchor'], animations=clips,
            release_point=[tip,float(np.median(yy[xx>=tip-1]))],
            energy_color={'companion':'#89d9dc','corpse':'#a18dbe','puppet':'#e4bd73'}[kind])
        sources.append(dict(file=path.relative_to(ROOT).as_posix(), sha256=digest(path), output=f'{identity}.png'))
        for pose in item['poses'].values():
            selected = base/pose['source']
            assert digest(selected) == pose['source_sha256']
        for source_name in sorted({pose['source'] for pose in item['poses'].values()}):
            selected = base/source_name
            sources.append(dict(file=selected.relative_to(ROOT).as_posix(), sha256=digest(selected),
                                output=f'{identity}.png / {identity}-defeat.png'))
        data['actions'][faction] = dict(name=item['attack_name'], duration=4., contacts=[2.1 if kind=='companion' else 1.85])


def add_battlefields(data, sources):
    base = ROOT/'design/combat-terrain-study-20261022'
    scenes = json.loads((base/'manifest.json').read_text(encoding='utf-8'))['backgrounds']
    data['battlefields'] = {'single': {}, 'group': {}}
    names = {'open':'开阔', 'narrow':'狭窄', 'peril':'险要'}
    for identity, scene in scenes.items():
        mode, kind = identity.split('-', 1)
        path = (base/scene['file']).resolve()
        assert digest(path) == scene['sha256']
        if identity == 'single-open':
            target = OUT/'terrace.png'
            assert digest(target) == scene['sha256']
        else:
            original = base/scene['source']
            assert digest(original) == scene['source_sha256']
            target = OUT/f'terrain-{identity}.png'
            Image.open(path).save(target,optimize=True)
            sources.append(dict(file=original.relative_to(ROOT).as_posix(),sha256=digest(original),output=target.name))
        data['battlefields'][mode][names[kind]] = dict(id=identity,name=names[kind],mode=mode,
            file='/assets/pixel/combat/'+target.name,size=list(Image.open(target).size),
            sha256=digest(target),horizon=scene['horizon'],ground_ratio=scene.get('ground_ratio'),requires=[])
        sources.append(dict(file=path.relative_to(ROOT).as_posix(),sha256=digest(path),output=target.name))


def main():
    duel = ROOT / 'design/duel-study-20261021'
    beasts = ROOT / 'design/beast-combat-study-20261022'
    data = json.loads((duel / 'manifest.json').read_text(encoding='utf-8'))
    other = json.loads((beasts / 'manifest.json').read_text(encoding='utf-8'))
    OUT.mkdir(parents=True, exist_ok=True)
    sources = []
    actors = [(identity, actor, duel) for identity, actor in data['actors'].items()]
    actors.extend((identity, actor, beasts) for identity, actor in other['actors'].items() if actor.get('creature'))
    output_actors = {}
    for identity, actor, base in actors:
        actor = json.loads(json.dumps(actor))
        cw, ch = actor.get('cell', data['cell'])
        actor.pop('portrait', None)
        actor['animations'] = {key: value for key, value in actor['animations'].items()
                               if key in {'idle', 'hit', 'brace', 'attack', 'dragon', 'blast', 'shadows', 'melee'}}
        for mode, group in actor['animations'].items():
            path = (base / group['sheet']).resolve()
            original = Image.open(path).convert('RGBA')
            # Trim transparent margins and deduplicate identical frames. Frame
            # offsets preserve the original anchors, limbs and painted pixels.
            unique, lookup, frames = [], {}, []
            for index in range(group['frames']):
                sample = body_sample(index, group['frames'], group['poses'])
                frame = original.crop((sample % 8 * cw, sample // 8 * ch, sample % 8 * cw + cw, sample // 8 * ch + ch))
                box = frame.getbbox() or (0, 0, 1, 1)
                crop = frame.crop(box)
                key = (crop.size, crop.tobytes())
                if key not in lookup:
                    lookup[key] = len(unique)
                    unique.append(crop)
                frames.append((lookup[key], box))
            tile_w = max(im.width for im in unique)
            tile_h = max(im.height for im in unique)
            columns = min(len(unique), max(1, 2048 // tile_w))
            atlas = Image.new('RGBA', (columns * tile_w, math.ceil(len(unique) / columns) * tile_h))
            for i, im in enumerate(unique):
                atlas.paste(im, (i % columns * tile_w, i // columns * tile_h))
            target = OUT / f'{identity}-{mode}.png'
            atlas.save(target, optimize=True)
            group['rects'] = [[i % columns * tile_w, i // columns * tile_h, box[2]-box[0], box[3]-box[1], box[0], box[1]] for i, box in frames]
            group['sheet'] = '/assets/pixel/combat/' + target.name
            group['size'] = list(atlas.size)
            group['sha256'] = digest(target)
            group['poses'] = [group['poses'][body_sample(i,group['frames'],group['poses'])] for i in range(group['frames'])]
            group['body_sample_fps'] = 10
            sources.append(dict(file=path.relative_to(ROOT).as_posix(), sha256=digest(path), output=target.name))
        output_actors[identity] = actor
    for name in ['terrace', 'dragon', 'seal', 'shadow']:
        path = (duel / data[name]).resolve()
        target = OUT / (name + '.png')
        Image.open(path).save(target, optimize=True)
        data[name] = '/assets/pixel/combat/' + target.name
        sources.append(dict(file=path.relative_to(ROOT).as_posix(), sha256=digest(path), output=target.name))
    data['actors'] = output_actors
    data['actions'].update({key: value for key, value in other['actions'].items() if key in {'avian', 'quadruped', 'insect'}})
    data['actions']['treasure'] = dict(name='御宝坠击', duration=4.8, contacts=[2.35])
    for identity in ['dao-male', 'dao-female']:
        data['actors'][identity]['animations']['treasure'] = data['actors'][identity]['animations']['dragon']
    data['schema_version'] = 1
    data['requires'] = []
    add_defeats(output_actors, data, sources)
    add_support(output_actors, data, sources)
    add_battlefields(data, sources)
    assert set(output_actors) == set(SCALES['actors']), 'Review scale reference before adding an actor'
    data['scale_contract'] = dict(file='scripts/combat_asset_scale.json', sha256=digest(SCALE_FILE),
        humanoid_standing_height=176, method=SCALES['method'])
    for identity, actor in output_actors.items():
        actor['scale_reference'] = dict(SCALES['actors'][identity],
            kind='species' if actor.get('creature') else 'humanoid',
            standing_height=None if actor.get('creature') else 176)
    sources.append(dict(file=SCALE_FILE.relative_to(ROOT).as_posix(), sha256=digest(SCALE_FILE), output='all defeat atlases'))
    data['provenance'] = sources
    (OUT / 'manifest.json').write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    print(json.dumps(dict(actors=len(output_actors), files=len(list(OUT.glob('*.png'))), bytes=sum(p.stat().st_size for p in OUT.glob('*')))))


if __name__ == '__main__':
    main()
