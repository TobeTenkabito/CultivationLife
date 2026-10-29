"""Export original Diao Chan paintings, casting poses and petal/phoenix VFX."""
import copy
from PIL import Image
from scripts.prepare_swimwear_assets import ROOT, main as export_skin, separate
from scripts.prepare_monster_static_assets import read, write, sha
from scripts.prepare_monster_flora_assets import pack

SOURCE = ROOT / 'design/diaochan-20261029'
OUT = ROOT / 'web/assets/pixel/diaochan'
URL = '/assets/pixel/diaochan/'
IDENTITY = 'diaochan-female'
ACTION = 'diaochan_phoenix'
MANIFEST = 'base.diaochan_manifest'


def main():
    export_skin(SOURCE, OUT, MANIFEST)
    data = read(OUT / 'manifest.json')
    catalog = read(ROOT / 'content/visual_assets.json')
    form = catalog['assets'][MANIFEST]['skin_forms'][0]
    form.update(scope='path', path='demonic', unlock_label='女性魔修 · 完成成就「凤仪亭」解锁 · 无境界限制')
    actor = data['actors'][IDENTITY]
    original = actor['animations']['idle']; rect = original['rects'][0]
    atlas = Image.open(ROOT / ('web'+original['sheet'])).convert('RGBA')
    idle = Image.new('RGBA',(384,288))
    idle.paste(atlas.crop((rect[0],rect[1],rect[0]+rect[2],rect[1]+rect[3])),tuple(rect[4:]))
    parts = separate(SOURCE/'diaochan-cast.png',2,6)
    factor = min((idle.getbbox()[3]-idle.getbbox()[1])/parts[0][0].height,
                 280/max(a.width for a,_ in parts),220/max(a.height for a,_ in parts))
    frames = [idle]
    for art,_ in parts:
        art = art.resize((round(art.width*factor),round(art.height*factor)),Image.Resampling.NEAREST)
        frame = Image.new('RGBA',(384,288));frame.paste(art,(192-art.width//2,256-art.height));frames.append(frame)
    packed = pack(frames,OUT/(IDENTITY+'-casting.png'));packed['sheet']=URL+IDENTITY+'-casting.png'
    names = ['idle','fan_lift','fan_coil','fan_sweep','fan_release','fan_follow','fan_close']
    stages = [(.35,0),(.75,1),(1.15,2),(1.45,3),(2.35,4),(2.9,5),(3.6,6),(4.1,0)]
    indices = [next(j for end,j in stages if i/20<end) for i in range(81)]
    clip = copy.deepcopy(actor['animations'].pop('attack'))
    clip.update(packed,frames=81,duration=4.,facing=1,body_sample_fps=20,
                rects=[packed['rects'][i] for i in indices],poses=[names[i] for i in indices])
    actor['animations'][ACTION] = clip
    actor.update(attack_action=ACTION,cast_effect=ACTION)
    actor['release_points'] = {}
    for name,frame,(u,v) in zip(names[1:],frames[1:],[(.4,.15),(.39,.06),(.96,.18),(.95,.13),(.94,.58),(.61,.48)]):
        l,t,r,b = frame.getbbox();actor['release_points'][name]=[round(l+(r-l)*u),round(t+(b-t)*v)]
    actor['release_point'] = actor['release_points']['fan_release']
    data['actions'][ACTION] = dict(name='凤仪乱红',duration=4.,contacts=[2.1])
    catalog['assets'][IDENTITY+'.casting'] = dict(file=packed['sheet'],size=packed['size'],sha256=packed['sha256'],requires=[])
    # Grid crops retain detached painted petals which connected-component extraction would omit.
    fx = Image.open(SOURCE/'diaochan-fx.png').convert('RGBA')
    pieces,boxes = [],[]
    for i in range(12):
        box=(round(i%4*fx.width/4),round(i//4*fx.height/3),round((i%4+1)*fx.width/4),round((i//4+1)*fx.height/3))
        art=fx.crop(box);art=art.crop(art.getbbox());pieces.append(art);boxes.append(box)
    scale=min(344/max(p.width for p in pieces),248/max(p.height for p in pieces))
    sheet=Image.new('RGBA',(1536,864))
    for i,art in enumerate(pieces):
        art=art.resize((round(art.width*scale),round(art.height*scale)),Image.Resampling.LANCZOS)
        sheet.paste(art,(i%4*384+(384-art.width)//2,i//4*288+(288-art.height)//2))
    target=OUT/'diaochan-fx.png';sheet.save(target,optimize=True)
    catalog['assets']['effect.'+ACTION+'.keyframes']=dict(file=URL+target.name,size=list(sheet.size),sha256=sha(target),requires=[])
    write(OUT/'manifest.json',data);catalog['assets'][MANIFEST]['sha256']=sha(OUT/'manifest.json')
    write(ROOT/'content/visual_assets.json',catalog)
    write(OUT/'effects-provenance.json',dict(generator='OpenAI built-in image_gen',painted_cast_poses=6,painted_effect_frames=12,
          cast_sha256=sha(SOURCE/'diaochan-cast.png'),cast_source_rects=[b for _,b in parts],cast_scale=factor,
          effect_sha256=sha(SOURCE/'diaochan-fx.png'),effect_source_rects=boxes,effect_scale=scale,
          export='Transparent component/grid crops and proportional packing; no painted anatomy generated in code',
          prompts=read(SOURCE/'effect-prompts.json')))


if __name__ == '__main__':
    main()
