"""Mechanically pack painted casting and VFX keyframes; no generated geometry."""
import copy
from pathlib import Path
from PIL import Image
from scripts.prepare_swimwear_assets import separate
from scripts.prepare_monster_static_assets import read, write, sha
from scripts.prepare_monster_flora_assets import pack

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'design/historical-effects-20261029'
OUT = ROOT / 'web/assets/pixel/historical'
URL = '/assets/pixel/historical/'
SPECS = [('nobunaga', 'nobunaga_command', '烈扇军令', 'nobunaga-fx.png'),
         ('seimei', 'seimei_lunar', '月华引符', 'seimei-fx-v2.png')]


def main():
    manifest = read(OUT / 'manifest.json')
    catalog = read(ROOT / 'content/visual_assets.json')
    records = []
    for name, action, label, fxfile in SPECS:
        identity = name + '-male'
        actor = manifest['actors'][identity]
        original = actor['animations']['idle']
        rect = original['rects'][0]
        atlas = Image.open(ROOT / ('web' + original['sheet'])).convert('RGBA')
        idle = Image.new('RGBA', (384, 288))
        idle.paste(atlas.crop((rect[0],rect[1],rect[0]+rect[2],rect[1]+rect[3])), tuple(rect[4:]))
        source = SOURCE / f'{name}-cast.png'
        parts = separate(source, 2, 6)
        scale = min((idle.getbbox()[3]-idle.getbbox()[1])/parts[0][0].height,
                    280/max(im.width for im, _ in parts), 220/max(im.height for im, _ in parts))
        frames = [idle]
        for art, _ in parts:
            art = art.resize((round(art.width*scale),round(art.height*scale)), Image.Resampling.NEAREST)
            frame = Image.new('RGBA', (384,288))
            frame.paste(art, (192-art.width//2,256-art.height))
            frames.append(frame)
        packed = pack(frames, OUT / f'{identity}-casting.png')
        packed['sheet'] = URL + f'{identity}-casting.png'
        clip = copy.deepcopy(actor['animations'].get('attack') or actor['animations'][actor['attack_action']])
        ends = [.35,.7,1.1,1.45,2.35,2.8,3.5,4.1] if name == 'nobunaga' else [.35,.75,1.15,1.45,2.35,3.,3.65,4.1]
        indices = [next(index for end,index in zip(ends,[0,1,2,3,4,5,6,0]) if i/20 < end) for i in range(81)]
        names = ['idle','fan_draw','fan_windup','fan_open','fan_release','fan_follow','fan_close']
        clip.update(packed, frames=81, duration=4., facing=1, body_sample_fps=20,
                    rects=[packed['rects'][i] for i in indices], poses=[names[i] for i in indices])
        actor['animations'].pop('attack', None)
        actor['animations'][action] = clip
        actor.update(attack_action=action, cast_effect=action)
        # Release anchor is the painted fan tip, not the former generic palm.
        b = frames[4].getbbox()
        uv = [.95,.65] if name == 'nobunaga' else [.94,.24]
        actor['release_point'] = [round(b[0]+(b[2]-b[0])*uv[0]),round(b[1]+(b[3]-b[1])*uv[1])]
        points = ([[.48,.51],[.37,.13],[.92,.16],uv,[.94,.29],[.44,.66]] if name == 'nobunaga'
                  else [[.54,.53],[.56,.28],[.96,.06],uv,[.96,.46],[.60,.52]])
        actor['release_points'] = {}
        for pose, frame, (u,v) in zip(names[1:], frames[1:], points):
            left,top,right,bottom = frame.getbbox()
            actor['release_points'][pose] = [round(left+(right-left)*u),round(top+(bottom-top)*v)]
        manifest['actions'][action] = dict(name=label,duration=4.,contacts=[2.1])
        catalog['assets'][identity+'.casting'] = dict(file=packed['sheet'],size=packed['size'],sha256=packed['sha256'],requires=[])

        fxsource = SOURCE / fxfile
        effects = separate(fxsource, 3, 12)
        factor = min(344/max(im.width for im, _ in effects),248/max(im.height for im, _ in effects))
        effect_atlas = Image.new('RGBA', (1536,864))
        for i, (art, _) in enumerate(effects):
            art = art.resize((round(art.width*factor),round(art.height*factor)), Image.Resampling.LANCZOS)
            effect_atlas.paste(art, (i%4*384+(384-art.width)//2,i//4*288+(288-art.height)//2))
        target = OUT / f'{name}-fx.png'
        effect_atlas.save(target, optimize=True)
        catalog['assets'][f'effect.{action}.keyframes'] = dict(file=URL+target.name,size=[1536,864],sha256=sha(target),requires=[])
        records.append(dict(actor=identity, cast_source=source.name, cast_sha256=sha(source),
            cast_rects=[box for _,box in parts], cast_scale=scale, effect_source=fxfile,
            effect_sha256=sha(fxsource), effect_rects=[box for _,box in effects], effect_scale=factor))
    write(OUT / 'manifest.json', manifest)
    catalog['assets']['base.historical_manifest']['sha256'] = sha(OUT / 'manifest.json')
    write(ROOT / 'content/visual_assets.json', catalog)
    write(OUT / 'effects-provenance.json', dict(generator='OpenAI built-in image_gen',
        painted_cast_keyposes=12, painted_effect_keyframes=24, export='RGBA component crops and proportional atlas packing only',
        sources=records, prompts=read(SOURCE/'prompts.json')))
    print('Historical effects: 12 painted cast poses, 24 VFX keyframes, two dedicated attack clips')


if __name__ == '__main__': main()
