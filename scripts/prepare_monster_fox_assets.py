"""Offline promotion of approved fox artwork to DLC1; never runs at game startup.

Mechanical extraction/nearest-neighbour export only. Painted originals and prompts
remain in design; the installed DLC contains all runtime derivatives and provenance.
"""
import hashlib
import importlib.util
import json
import math
import shutil
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / 'design'
OUT = ROOT / 'dlc/monster-bloodlines/assets/visual/fox'
OWNER = 'official.monster-bloodlines'
URL = f'/extension-assets/{OWNER}/visual/fox/'
CELL, ANCHOR, FPS = (384, 288), (192, 256), 20


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module(path):
    spec = importlib.util.spec_from_file_location('fox_export_helpers', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


HELPER = module(DESIGN/'fox-integration-combat-alpha4-20261023/prepare.py')
POSES, CLIPS = HELPER.POSES, HELPER.CLIPS


def pack(frames, path):
    unique, lookup, records = [], {}, []
    for frame in frames:
        box = frame.getbbox()
        assert box
        crop = frame.crop(box)
        key = (crop.size, crop.tobytes())
        if key not in lookup:
            lookup[key] = len(unique)
            unique.append(crop)
        records.append((lookup[key], box))
    tw, th = max(i.width for i in unique), max(i.height for i in unique)
    cols = min(len(unique), max(1, 2048 // tw))
    atlas = Image.new('RGBA', (cols*tw, math.ceil(len(unique)/cols)*th))
    for i, frame in enumerate(unique):
        atlas.paste(frame, (i % cols*tw, i//cols*th))
    atlas.save(path, optimize=True)
    return dict(sheet=URL+path.name, sha256=sha(path), size=list(atlas.size),
                rects=[[i % cols*tw, i//cols*th, b[2]-b[0], b[3]-b[1], b[0], b[1]] for i,b in records])


def beast_frames(source):
    parts = HELPER.split_parts(source, 9, 3)
    # Quadruped body scale, shared by every pose (never enlarge a fallen pose).
    factor = min(112/parts[0][0].height, 282/max(p.width for p,_ in parts),
                 180/max(p.height for p,_ in parts))
    frames = []
    for art, _ in parts:
        im = art.resize((round(art.width*factor), round(art.height*factor)), Image.Resampling.NEAREST)
        frame = Image.new('RGBA', CELL)
        frame.paste(im, (ANCHOR[0]-im.width//2, ANCHOR[1]-im.height))
        frames.append(frame)
    clips = {}
    for mode, spec in CLIPS.items():
        indices = [POSES.index(next(p for t,p in reversed(spec['keys']) if i/FPS>=t))
                   for i in range(round(spec['duration']*FPS)+1)]
        clips[mode] = dict(spec, frames=indices,
                           poses=[dict(pose=POSES[i], anchor=list(ANCHOR)) for i in indices])
    return frames, clips


def static_exports(identity, source, existing=None, parts=None):
    result = {}
    if existing:
        for kind, item in existing.items():
            path = OUT/f'{identity}-{kind}.png'
            assert sha(item[0]) == item[1]
            shutil.copyfile(item[0], path)
            result[kind] = dict(file=URL+path.name, size=list(Image.open(path).size), sha256=sha(path), requires=[OWNER])
        return result
    if parts is not None:
        pass  # Caller supplied a verified split of its own paired source.
    elif source.name == 'fox-nine-female-v2.png' and 'fox-integration' in str(source):
        # The two approved figures almost touch. Cut only their faint alpha gap,
        # using a continuous least-alpha seam; do not threshold the spirit tails.
        rgba=np.asarray(Image.open(source).convert('RGBA'))
        lo,hi=870,1100
        cost=(rgba[:,lo:hi,3].astype(float)/8)**2 + abs(np.arange(lo,hi)-970)*.0001
        total=cost[0].copy(); previous=[]
        for y in range(1,len(cost)):
            candidates=np.array([np.roll(total,d) for d in range(-10,11)])
            for i,d in enumerate(range(-10,11)):
                if d<0:candidates[i,d:]=np.inf
                if d>0:candidates[i,:d]=np.inf
            choice=candidates.argmin(0);previous.append(choice-10)
            total=cost[y]+candidates.min(0)
        x=int(total.argmin());seam=[x]
        for delta in reversed(previous):
            x-=int(delta[x]);seam.append(x)
        seam=np.array(seam[::-1])+lo
        assert rgba[np.arange(len(seam)),seam,3].max()<128, 'Seam must not cut opaque artwork'
        parts=[]
        for left in [True,False]:
            keep=np.arange(rgba.shape[1])[None,:]<seam[:,None]
            if not left:keep=~keep
            labels,_=ndimage.label(keep&(rgba[:,:,3]>=8),np.ones((3,3)))
            sizes=np.bincount(labels.ravel());sizes[0]=0
            keep &= ndimage.binary_dilation(labels==sizes.argmax(),iterations=4)
            pixels=rgba.copy();pixels[~keep]=0;pixels[pixels[:,:,3]==0]=0
            im=Image.fromarray(pixels);box=im.getbbox();parts.append((im.crop(box),box))
    elif source.name == 'fox-nine-tail-v2.png' and 'fox-growth' in str(source):
        # This approved source has a faint alpha bridge between its two figures.
        # Use 64 only to identify the figures; retain original alpha in each mask.
        rgba=np.asarray(Image.open(source).convert('RGBA'))
        labels,_=ndimage.label(rgba[:,:,3]>=64,np.ones((3,3)))
        sizes=np.bincount(labels.ravel())
        ids=sorted(range(1,len(sizes)),key=lambda i:-sizes[i])[:2]
        assert min(sizes[i] for i in ids)>1000
        parts=[]
        for i in ids:
            keep=ndimage.binary_dilation(labels==i,iterations=4)&~np.isin(labels,[j for j in ids if j!=i])
            pixels=rgba.copy();pixels[~keep]=0;pixels[pixels[:,:,3]==0]=0
            im=Image.fromarray(pixels);box=im.getbbox();parts.append((im.crop(box),box))
        parts.sort(key=lambda p:p[1][0])
    else:
        parts = HELPER.split_parts(source, 2, 1)
    for kind, size, art in [('figure',(256,288),parts[0][0]), ('portrait',(128,128),parts[1][0]),
                            ('thumbnail',(128,144),parts[0][0])]:
        factor = min((size[0]-12)/art.width, (size[1]-16)/art.height)
        scaled = art.resize((round(art.width*factor),round(art.height*factor)), Image.Resampling.NEAREST)
        im = Image.new('RGBA',size)
        im.paste(scaled,((size[0]-scaled.width)//2,size[1]-8-scaled.height))
        path = OUT/f'{identity}-{kind}.png'
        im.save(path,optimize=True)
        result[kind] = dict(file=URL+path.name,size=list(size),sha256=sha(path),requires=[OWNER])
    return result


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    catalog = read(ROOT/'content/visual_assets.json')
    actors, statics, provenance = {}, {}, []
    low = DESIGN/'fox-growth-alpha4-20261023'
    beast = DESIGN/'fox-beast-combat-alpha4-20261023'
    sources = read(beast/'sources.json')
    for a in read(low/'manifest.json')['actors'][:8]:
        path = low/a['file']; assert sha(path)==a['sha256']
        identity = 'fox-'+a['id'][4:].lower().replace('_','-')+'-shared'
        statics[identity] = static_exports(identity,path)
        provenance.append(dict(kind='static',file=path.relative_to(ROOT).as_posix(),sha256=sha(path),identity=identity))
    jobs = []
    for a in sources['actors']:
        path = beast/a['file']; assert sha(path)==a['sha256']
        identity = 'fox-'+a['id'][4:].lower().replace('_','-')+'-shared'
        frames, clips = beast_frames(path)
        jobs.append((identity,a['name'],True,frames,clips,path,a['id']))
    for stage, dirname in [('nascent','fox-combat-alpha4-20261023'),('integration','fox-integration-combat-alpha4-20261023')]:
        folder = DESIGN/dirname
        manifest = read(folder/'manifest.json')
        static_folder = DESIGN/('fox-nascent-alpha4-20261023' if stage=='nascent' else 'fox-integration-alpha4-20261023')
        original = {a['id']:a for a in read(static_folder/'manifest.json')['actors']}
        for key,a in manifest['actors'].items():
            identity = f'fox-{stage}-{key}'
            atlas_path = folder/a['sheet']; assert sha(atlas_path)==a['sha256']
            atlas = Image.open(atlas_path).convert('RGBA')
            frames = [atlas.crop((i%4*384,i//4*288,i%4*384+384,i//4*288+288)) for i in range(a['unique_frames'])]
            source = folder/a['source']['file']; assert sha(source)==a['source']['sha256']
            jobs.append((identity,a['name'],False,frames,a['animations'],source,a['node']))
            ref = static_folder/original[key]['file']; assert sha(ref)==original[key]['sha256']
            existing = {k:(folder/v['file'],v['sha256']) for k,v in a.get('pixel',{}).items() if isinstance(v,dict) and 'file' in v}
            statics[identity] = static_exports(identity,ref,existing)
            provenance.append(dict(kind='static',file=ref.relative_to(ROOT).as_posix(),sha256=sha(ref),identity=identity))
    for identity,name,creature,frames,clips,source,node in jobs:
        packed = pack(frames,OUT/f'{identity}-actions.png')
        groups = {}
        for mode,clip in clips.items():
            groups[mode] = dict(packed,rects=[packed['rects'][i] for i in clip['frames']],
                frames=len(clip['frames']),poses=clip['poses'],duration=clip['duration'],facing=1,
                cell=list(CELL),body_sample_fps=10 if not creature else 0)
        groups['fox_spell'] = groups['attack']
        release = frames[2].getbbox()
        point = [release[2]-8,release[1]+round((release[3]-release[1])*.24)] if creature else [235,152]
        color = '#baabe2' if 'moon' in identity else '#eed8aa' if 'nine' in identity else '#d5a47e'
        actors[identity] = dict(name=name,role='hero',faction='fox',creature=creature,
            sex=None if creature else identity.rsplit('-',1)[1],cell=list(CELL),anchor=list(ANCHOR),
            attack_action='fox_spell',domain_action='domain',release_point=point,energy_color=color,
            hit_offset=[25,-55] if creature else [23,-85],
            guard_shape=dict(cx=0,cy=-57,rx=86,ry=65) if creature else dict(cx=4,cy=-86,rx=70,ry=94),
            animations=groups)
        provenance.append(dict(kind='actions',file=source.relative_to(ROOT).as_posix(),sha256=sha(source),identity=identity,node=node))
        catalog['assets'][identity+'.actions'] = dict(file=packed['sheet'],size=packed['size'],sha256=packed['sha256'],requires=[OWNER])
    for identity,rows in statics.items():
        for kind,row in rows.items():
            catalog['assets'][f'actor.monster.{identity}.{kind}'] = row
    # Explicit content nodes; shared late nodes retain the latest known branch.
    routes = {
        'mystic':['FOX_MYSTIC','FOX_KING','FOX_MOUNTAIN_KING','FOX_MYSTIC_5','FOX_MYSTIC_6','FOX_MYSTIC_7','FOX_MYSTIC_8'],
        'moon':['FOX_MOON','FOX_DREAM','FOX_MOON_DREAM','FOX_MOON_ORACLE','FOX_DREAM_WEAVER','FOX_MOON_SOVEREIGN','FOX_MOON_5','FOX_MOON_6','FOX_MOON_7','FOX_MOON_8'],
        'nine':['FOX_NINE_TAIL','FOX_NINE_FLAME_SOVEREIGN','FOX_ANCESTRAL_DREAM','FOX_MAHAYANA_HEAVENLY'],
    }
    nodes = {}
    for n in read(ROOT/'dlc/monster-bloodlines/content/monster_bloodlines.json')['evolutions']:
        if n['species']!='fox' or n['realm_index']>8: continue
        node,realm=n['id'],n['realm_index']
        route=next((k for k,ids in routes.items() if node in ids),None)
        row=dict(realm=realm,route=route)
        if realm<4:
            art = node if node in {a['id'] for a in read(low/'manifest.json')['actors'][:8]} else ('FOX_KING' if route=='mystic' else 'FOX_MOON_DREAM')
            row['static']='fox-'+art[4:].lower().replace('_','-')+'-shared'
            action=art if realm==3 else 'FOX_SPIRIT'
            row['combat']='fox-'+action[4:].lower().replace('_','-')+'-shared'
        else:
            row['stage']='nascent' if realm<7 else 'integration'
        nodes[node]=row
    data=dict(schema_version=1,owner=OWNER,version='4.17.0',fps=FPS,actors=actors,nodes=nodes,
        history_routes={node:route for route,ids in routes.items() for node in ids},
        actions=dict(fox_spell=dict(name='血脉灵息',duration=4.0,contacts=[2.1])))
    write(OUT/'manifest.json',data)
    catalog['assets']['monster.fox.combat_manifest']=dict(file=URL+'manifest.json',requires=[OWNER],sha256=sha(OUT/'manifest.json'))
    write(OUT/'registry.json',{'assets':{k:v for k,v in catalog['assets'].items() if v['file'].startswith(URL)}})
    None  # Registry is assembled inside the DLC, never written into core content.
    write(OUT/'provenance.json',dict(generator='OpenAI built-in image_gen',authorization='再补充狐狸时期的各个动作，然后将这一部分素材并入妖修dlc1中，并更新妖修dlc版本，暂不打包。',
        export='nearest-neighbour; original soft alpha; nascent approved pixel files copied byte-for-byte',
        painted_keyposes=144,animation_clips=112,static_forms=20,combat_forms=16,sources=provenance,
        prompts=['design/fox-beast-combat-alpha4-20261023/prompts.json','design/fox-integration-combat-alpha4-20261023/prompts.json','design/fox-combat-alpha4-20261023/prompts.json']))
    print(f'{len(actors)} combat forms, {len(statics)} static forms promoted to {OUT}')


    from scripts.prepare_monster_release_assets import assemble
    assemble()

if __name__=='__main__':
    main()
