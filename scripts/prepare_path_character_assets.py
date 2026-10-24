"""Offline export of generated ghost/Confucian/Buddhist full-character originals."""
import importlib.util
import json
from pathlib import Path
from PIL import Image
from scripts.prepare_monster_static_assets import paired_parts, sha, read, write
from scripts.prepare_monster_flora_assets import pack

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT/'design/three-paths-alpha5-20261025'
PACKAGES = {'ghost': ('ghost-reincarnation','3.10.0','#a1bce5'),
            'confucian': ('sage-way','1.6.0','#91c7d5'),
            'buddhist': ('buddhist-dharma','1.2.0','#e9c77f')}
POSES = ['idle','gather','release','guard','brace','hit','stagger','kneel','down']


def main():
    # Reuse the established nine-pose splitter and battle timing, not its species rules.
    spec = importlib.util.spec_from_file_location('path_pose_tools', ROOT/'design/flora-combat-alpha4-20261024/prepare.py')
    motion = importlib.util.module_from_spec(spec);spec.loader.exec_module(motion)
    sources = read(DESIGN/'prompts.json');by_id = {row['id']:row for row in sources}
    preview=[]
    for path,(package,version,color) in PACKAGES.items():
        owner='official.'+package;out=ROOT/'dlc'/package/'assets/visual/characters';out.mkdir(parents=True,exist_ok=True)
        url=f'/extension-assets/{owner}/visual/characters/'
        assets={};actors={};forms=[];provenance=[]
        for s in sources:
            if s.get('reference') or not s['id'].startswith(path+'-'):continue
            ident=s['id'];role=ident.split('-')[1];gender=ident.split('-')[2]
            donor={'ghost-hero-female':'ghost-npc-female','ghost-npc-female':'ghost-hero-female'}.get(ident,ident)
            s=by_id[donor]
            static='actor.path.'+ident
            source=DESIGN/s['file'];parts=paired_parts(source)
            for kind,size in [('portrait',(128,128)),('figure',(256,288)),('thumbnail',(128,144))]:
                art=parts[1 if kind=='portrait' else 0][0]
                scale=min((size[0]-12)/art.width,(size[1]-16)/art.height)
                art=art.resize((round(art.width*scale),round(art.height*scale)),Image.Resampling.NEAREST)
                canvas=Image.new('RGBA',size);canvas.paste(art,((size[0]-art.width)//2,size[1]-8-art.height))
                target=out/f'{ident}-{kind}.png';canvas.save(target,optimize=True)
                assets[static+'.'+kind]=dict(file=url+target.name,size=list(size),sha256=sha(target),requires=[owner])
            action=by_id[donor+'-actions'];parts=motion.split_parts(DESIGN/action['file'],9,3)
            factor=min(176/parts[0][0].height,282/max(im.width for im,_ in parts),180/max(im.height for im,_ in parts))
            frames=[];records={}
            for i,(pose,(art,box)) in enumerate(zip(POSES,parts)):
                scale=factor
                override=next((r for r in sources if r.get('override_for')==action['id'] and r.get('override_pose')==pose),None)
                if override:
                    fixed,fixed_box=motion.split_parts(DESIGN/override['file'],1,1)[0]
                    scale=art.height*factor/fixed.height;art=fixed;box=fixed_box
                art=art.resize((round(art.width*scale),round(art.height*scale)),Image.Resampling.NEAREST)
                # The reviewed scholar's defeat source faces left; normalize this single pose.
                if ident=='confucian-npc-female' and pose=='down':art=art.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                canvas=Image.new('RGBA',(384,288));offset=(192-art.width//2,256-art.height);canvas.paste(art,offset)
                target=DESIGN/'poses'/ident/(pose+'.png');target.parent.mkdir(parents=True,exist_ok=True);canvas.save(target,optimize=True)
                frames.append(canvas);records[pose]=dict(source=(override or action)['file'],source_rect=box,scale=scale,offset=offset,sha256=sha(target))
            packed=pack(frames,out/f'{ident}-actions.png');packed['sheet']=url+f'{ident}-actions.png'
            groups={}
            for mode,clip in motion.CLIPS.items():
                indices=[POSES.index(next(p for start,p in reversed(clip['keys']) if at/20>=start)) for at in range(round(clip['duration']*20)+1)]
                groups[mode]=dict(packed,rects=[packed['rects'][i] for i in indices],frames=len(indices),
                    poses=[POSES[i] for i in indices],duration=clip['duration'],facing=1,cell=[384,288],body_sample_fps=10)
            spell=path+'_spell';groups[spell]=groups['attack']
            actors[ident]=dict(name=s['name'],role=role,faction=path,creature=False,sex=gender,cell=[384,288],anchor=[192,256],
                attack_action=spell,domain_action='domain',release_point=[235,152],energy_color=color,energy_effect=True,
                hit_offset=[23,-85],guard_shape=dict(cx=4,cy=-86,rx=70,ry=94),animations=groups)
            forms.append(dict(path=path,race='human',gender=gender,role=role,static=static,combat=ident))
            assets[ident+'.actions']=dict(file=packed['sheet'],size=packed['size'],sha256=packed['sha256'],requires=[owner])
            provenance.append(dict(identity=ident,static_source=s['file'],static_sha256=sha(source),actions_source=action['file'],
                                   actions_sha256=sha(DESIGN/action['file']),poses=records))
            preview.append(dict(id=ident,name=s['name'],static_file=s['file'],actions_file=action['file'],poses=records,
                                figure=f'../../dlc/{package}/assets/visual/characters/{ident}-figure.png',
                                portrait=f'../../dlc/{package}/assets/visual/characters/{ident}-portrait.png'))
        assert len(actors)==4
        manifest=dict(schema_version=1,owner=owner,version=version,fps=20,actors=actors,
                      actions={path+'_spell':dict(name={'ghost':'幽魂术','confucian':'浩然气','buddhist':'莲华印'}[path],duration=4,contacts=[2.1])})
        write(out/'manifest.json',manifest)
        assets[path+'.character_manifest']=dict(file=url+'manifest.json',sha256=sha(out/'manifest.json'),requires=[owner],
                                               combat_actors=list(actors),character_forms=forms)
        write(out.parent/'registry.json',dict(assets=assets))
        write(out/'provenance.json',dict(generator='OpenAI built-in image_gen',prompts='design/three-paths-alpha5-20261025/prompts.json',
            static_forms=4,painted_keyposes=36,animation_clips=28,export='nearest-neighbour, original soft alpha, common scale and foot anchor',sources=provenance))
        p=ROOT/'dlc'/package/'manifest.json';data=read(p);data.update(version=version,visual_registry='visual/registry.json');write(p,data)
    write(DESIGN/'manifest.json',dict(actors=preview,poses=POSES,clips=motion.CLIPS))
    (DESIGN/'data.js').write_text('window.PathArt='+json.dumps(read(DESIGN/'manifest.json'),ensure_ascii=False)+';\n',encoding='utf-8')
    print('12 forms, 36 static PNGs, 108 keyposes, 84 animation clips, 3 isolated DLC registries')


if __name__=='__main__':main()
