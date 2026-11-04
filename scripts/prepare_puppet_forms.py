"""Offline mechanical export of seven generated full-anatomy pose sheets."""
import json,hashlib,copy
from pathlib import Path
from PIL import Image
from scripts.prepare_combat_assets import pack_frames

ROOT=Path(__file__).resolve().parents[1]
POSES=['idle','gather','release','guard','brace','hit','stagger','kneel','down']
CLIPS={
 'idle':(4,[(0,'idle')]),
 'attack':(4,[(0,'idle'),(.4,'gather'),(1.25,'release'),(2.35,'gather'),(3.05,'idle')]),
 'hit':(2.4,[(0,'idle'),(.55,'hit'),(1,'brace'),(1.55,'gather'),(1.95,'idle')]),
 'brace':(4,[(0,'idle'),(.25,'gather'),(.65,'guard'),(1.95,'brace'),(2.55,'guard'),(3.05,'idle')]),
 'defeat':(2.6,[(0,'hit'),(.3,'stagger'),(.8,'kneel'),(1.35,'down')])}

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8')

def main():
    source=ROOT/'design/controlled-352';out=ROOT/'web/assets/pixel/controlled-352';out.mkdir(exist_ok=True)
    recipe=json.loads((source/'prompts.json').read_text(encoding='utf8'))
    manifest=ROOT/'web/assets/pixel/combat/manifest.json';data=json.loads(manifest.read_text(encoding='utf8'))
    catalog={};provenance=[]
    for row in recipe['actors']:
        identity='mechanical-'+row['id'];original=source/row['file'];im=Image.open(original).convert('RGBA')
        alpha=im.getchannel('A').point(lambda v:255 if v>=128 else 0)
        im=im.convert('RGB').quantize(colors=48,dither=Image.Dither.NONE).convert('RGBA');im.putalpha(alpha)
        import numpy as np
        from scipy import ndimage
        pixels=np.array(im);labels,_=ndimage.label(pixels[:,:,3]>=128,np.ones((3,3)))
        sizes=np.bincount(labels.ravel());ids=[i for i in range(1,len(sizes)) if sizes[i]>1000]
        assert len(ids)==9,(identity,len(ids))
        pieces=[]
        for i in ids:
            rgba=pixels.copy();rgba[labels!=i]=0;part=Image.fromarray(rgba);bounds=part.getbbox()
            assert bounds[0]>0 and bounds[1]>0 and bounds[2]<im.width and bounds[3]<im.height
            pieces.append((part.crop(bounds),list(bounds)))
        pieces.sort(key=lambda p:(min(2,int((p[1][1]+p[1][3])/2/(im.height/3))),p[1][0]))
        parts=[p[0] for p in pieces];boxes=[p[1] for p in pieces]
        static={}
        for kind,size in [('figure',(128,192)),('portrait',(96,96))]:
            art=parts[0]
            if kind=='portrait':art=art.crop((0,0,art.width,max(1,round(art.height*.4))))
            scale=min((size[0]-12)/art.width,(size[1]-16)/art.height)
            art=art.resize((round(art.width*scale),round(art.height*scale)),Image.Resampling.NEAREST)
            canvas=Image.new('RGBA',size);canvas.paste(art,((size[0]-art.width)//2,size[1]-8-art.height))
            target=out/f'{identity}-{kind}.png';canvas.save(target,optimize=True)
            static[kind]=dict(file='/assets/pixel/controlled-352/'+target.name,size=list(size),sha256=sha(target))
        catalog[identity]=static
        factor=min(176/parts[0].height,282/max(p.width for p in parts),180/max(p.height for p in parts))
        frames=[]
        for art in parts:
            art=art.resize((round(art.width*factor),round(art.height*factor)),Image.Resampling.NEAREST)
            canvas=Image.new('RGBA',(384,288));canvas.paste(art,(192-art.width//2,256-art.height));frames.append(canvas)
        target=ROOT/f'web/assets/pixel/combat/{identity}-352.png';packed=pack_frames(frames,target)
        groups={}
        for mode,(duration,keys) in CLIPS.items():
            indices=[POSES.index(next(p for at,p in reversed(keys) if t/20>=at)) for t in range(round(duration*20)+1)]
            groups[mode]=dict(packed,rects=[packed['rects'][i] for i in indices],frames=len(indices),duration=duration,
                poses=[dict(pose='defeat' if mode=='defeat' and i>=6 else POSES[i],painted_pose=POSES[i],anchor=[192,256]) for i in indices],facing=1,cell=[384,288],body_sample_fps=0)
        data['actors'][identity]=dict(name=row['name'],role='npc',faction='mechanical',sex=None,
            scale_reference=dict(kind='common-pose-sheet',source_sha256=sha(original),common_scale=factor,pose_scales=[factor]*9),
            creature=row['id'] in ('dragon','serpent','bird'),cell=[384,288],anchor=[192,256],
            attack_action='puppet_form',release_point=[235,152],energy_color='#b9b096',energy_effect=True,
            hit_offset=[23,-85],guard_shape=dict(cx=4,cy=-86,rx=70,ry=94),animations=groups)
        provenance.append(dict(id=identity,file=original.relative_to(ROOT).as_posix(),sha256=sha(original),
            prompt=row['prompt'],source_rects=boxes,scale=factor,output=target.name,output_sha256=sha(target)))
    data['actions']['puppet_form']=dict(name='枢纹冲击',duration=4,contacts=[2.1])
    data['provenance']=[r for r in data['provenance'] if not r.get('file','').startswith('design/controlled-352/')]+provenance
    write(manifest,data)
    (out/'catalog.js').write_text('Object.assign(window.ControlledArtCatalog, '+json.dumps(catalog,ensure_ascii=False)+');\n',encoding='utf8')
    write(out/'provenance.json',dict(generator=recipe['generator'],reference=recipe['reference'],sources=provenance,
        review='逐形态检查九姿态：人形双手双足、龙四爪、鸟双翼双足、蛇单体单尾；等比裁切与48色导出，不程序补绘解剖。'))
    print('7 figures, 7 portraits, 63 painted poses, 35 timed clips exported.')

if __name__=='__main__':main()
