"""Pack original hunting beasts; preserve painted anatomy and existing combat clock."""
import copy
from PIL import Image
from scripts.prepare_swimwear_assets import ROOT, separate
from scripts.prepare_monster_static_assets import read, write, sha
from scripts.prepare_monster_flora_assets import pack

SOURCE = ROOT / 'design/hunt-beasts-20261029'
OUT = ROOT / 'web/assets/pixel/hunt-beasts'
URL = '/assets/pixel/hunt-beasts/'
POSES = ['idle', 'windup', 'attack_a', 'attack_b', 'guard', 'hit', 'retreat', 'down']


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    base = read(ROOT / 'web/assets/pixel/combat/manifest.json')
    catalog = read(ROOT / 'content/visual_assets.json')
    actors, assets, sources = {}, {}, []
    prompts = read(SOURCE / 'prompts.json')
    for row in prompts:
        ident, kind = row['id'], row['kind']
        source = SOURCE / (ident + '.png')
        parts = separate(source, 2, 8)
        scale = min(160/parts[0][0].height, 284/max(p.width for p, _ in parts), 200/max(p.height for p, _ in parts))
        frames, records = [], []
        for pose, (art, box) in zip(POSES, parts):
            art = art.resize((round(art.width*scale), round(art.height*scale)), Image.Resampling.LANCZOS)
            frame = Image.new('RGBA', (384,384))
            frame.paste(art, (192-art.width//2, 320-art.height))
            frames.append(frame)
            bounds = frame.getbbox()
            records.append(dict(pose=pose, anchor=[192,320], bounds=list(bounds), point=[bounds[2]-1, bounds[1]+round(art.height*.45)]))
        packed = pack(frames, OUT / (ident+'-actions.png'))
        packed['sheet'] = URL+ident+'-actions.png'
        actor = copy.deepcopy(base['actors'][kind])
        for key in ['poses','review','scale_reference','parts']:
            actor.pop(key, None)
        actor.update(name=row['name'], anchor=[192,320], beast_style=kind,
                     attack_action=kind, height=round(parts[0][0].height*scale),
                     hit_offset=[25,-round(parts[0][0].height*scale*.55)])
        actor['guard_shape'] = dict(cx=0,cy=actor['hit_offset'][1],rx=90,ry=max(55,round(actor['height']*.6)))
        actor['release_point'] = records[2]['point']
        lookup = dict(idle=0,windup=1,attack_a=2,attack_b=3,recover=0,guard=4,absorb=4,hit=5,retreat_a=6,retreat_b=0)
        for mode, clip in actor['animations'].items():
            indices = [lookup.get(p['pose'],0) for p in clip['poses']]
            if mode == 'defeat':
                indices = [5 if i<8 else 6 if i<18 else 7 for i in range(clip['frames'])]
            clip.pop('scale_calibration',None)
            clip.update(packed, facing=1, cell=[384,384], body_sample_fps=0,
                        rects=[packed['rects'][i] for i in indices], poses=[records[i] for i in indices])
        actors[ident] = actor
        assets[ident+'.actions'] = dict(file=packed['sheet'],size=packed['size'],sha256=packed['sha256'],requires=[])
        for name, size in [('figure',(256,288)),('thumbnail',(128,144)),('portrait',(128,128))]:
            art = parts[0][0].copy()
            art.thumbnail((size[0]-12,size[1]-16),Image.Resampling.LANCZOS)
            canvas = Image.new('RGBA',size)
            canvas.paste(art,((size[0]-art.width)//2,size[1]-8-art.height))
            path = OUT / (ident+'-'+name+'.png'); canvas.save(path,optimize=True)
            assets['actor.beast.'+ident+'.'+name] = dict(file=URL+path.name,size=list(size),sha256=sha(path),requires=[])
        sources.append(dict(id=ident,source=source.relative_to(ROOT).as_posix(),sha256=sha(source),scale=scale,source_rects=[b for _,b in parts]))
    path = OUT / 'manifest.json'
    write(path,dict(schema_version=1,fps=20,actors=actors,actions={}))
    assets['base.hunt_beasts_manifest'] = dict(file=URL+path.name,sha256=sha(path),requires=[],combat_actors=list(actors))
    catalog['assets'].update(assets); write(ROOT / 'content/visual_assets.json',catalog)
    write(OUT / 'provenance.json',dict(generator='OpenAI built-in image_gen',painted_keyposes=32,sources=sources,prompts=prompts))


if __name__ == '__main__':
    main()
