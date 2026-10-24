"""Offline promotion of flora originals; shipped assets never depend on design."""
import math
from pathlib import Path
from PIL import Image
from scripts.prepare_monster_static_assets import export,read,write,sha,OWNER

ROOT=Path(__file__).resolve().parents[1]
STATIC=ROOT/'design/flora-growth-alpha4-20261024'
ACTION=ROOT/'design/flora-combat-alpha4-20261024'
OUT=ROOT/'dlc/monster-bloodlines/assets/visual/flora'
URL=f'/extension-assets/{OWNER}/visual/flora/'

def identity(a):
    return 'flora-'+a['id']+'-shared'

def pack(frames,path):
    boxes=[im.getbbox() for im in frames]
    crops=[im.crop(box) for im,box in zip(frames,boxes)]
    w,h=max(im.width for im in crops),max(im.height for im in crops)
    cols=min(len(crops),2048//w)
    atlas=Image.new('RGBA',(cols*w,math.ceil(len(crops)/cols)*h))
    for i,im in enumerate(crops):atlas.paste(im,(i%cols*w,i//cols*h))
    atlas.save(path,optimize=True)
    return dict(sheet=URL+path.name,sha256=sha(path),size=list(atlas.size),
                rects=[[i%cols*w,i//cols*h,b[2]-b[0],b[3]-b[1],b[0],b[1]] for i,b in enumerate(boxes)])

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    catalog=read(ROOT/'content/visual_assets.json');assets={};actors={};sources=[]
    previous={p:sha(p) for species in ['fox','serpent','avian','ape','turtle','insect','aquatic'] for p in (OUT.parent/species).rglob('*') if p.is_file()}
    statics={a['id']:a for a in read(STATIC/'manifest.json')['actors']}
    for key,a in read(ACTION/'manifest.json')['actors'].items():
        ident=identity(a);s=statics[key];source=STATIC/s['file'];assert sha(source)==s['sha256']
        rows,boxes=export(ident,source,OUT,URL)
        for kind,row in rows.items():assets[f'actor.monster.{ident}.{kind}']=row
        sources.append(dict(kind='static',identity=ident,file=source.relative_to(ROOT).as_posix(),sha256=sha(source),subject_bounds=boxes))
        source=ACTION/a['source']['file'];assert sha(source)==a['source']['sha256']
        sources.append(dict(kind='actions',identity=ident,file=source.relative_to(ROOT).as_posix(),sha256=sha(source)))
        for pose,record in a['poses'].items():
            if 'override' in record:
                override=record['override'];source=ACTION/override['file']
                assert sha(source)==override['sha256']
                sources.append(dict(kind='pose-override',pose=pose,identity=ident,file=source.relative_to(ROOT).as_posix(),sha256=sha(source)))
        path=ACTION/a['sheet'];assert sha(path)==a['sha256'];atlas=Image.open(path).convert('RGBA')
        frames=[atlas.crop((i%4*384,i//4*288,i%4*384+384,i//4*288+288)) for i in range(a['unique_frames'])]
        packed=pack(frames,OUT/f'{ident}-actions.png')
        groups={mode:dict(packed,rects=[packed['rects'][i] for i in clip['frames']],frames=len(clip['frames']),
                         poses=clip['poses'],duration=clip['duration'],facing=1,cell=[384,288],
                         body_sample_fps=0 if a['beast'] else 10) for mode,clip in a['animations'].items()}
        groups['flora_spell']=groups['attack'];box=frames[2].getbbox()
        # Botanical core/crown focus; plants never emit a humanoid palm/fish-mouth spell.
        point=[box[0]+round((box[2]-box[0])*.72),box[1]+round((box[3]-box[1])*.42)] if a['beast'] else [235,152]
        actors[ident]=dict(name=a['name'],role='hero',faction='flora',creature=a['beast'],sex=None,
            cell=[384,288],anchor=[192,256],attack_action='flora_spell',domain_action='idle' if a['beast'] else 'domain',
            release_point=point,energy_color=a['colors'][0],hit_offset=[25,-65] if a['beast'] else [23,-85],
            guard_shape=dict(cx=0,cy=-66,rx=98,ry=78) if a['beast'] else dict(cx=4,cy=-86,rx=70,ry=94),animations=groups)
        assets[ident+'.actions']=dict(file=packed['sheet'],size=packed['size'],sha256=packed['sha256'],requires=[OWNER])
    direct={a['node']:identity(a) for a in statics.values() if a['beast']}
    nascent={'FLORA_SHAPED_SOVEREIGN':'ancient','FLORA_FLOWER_SOVEREIGN':'flower',
             'FLORA_THORN_SOVEREIGN':'thorn','FLORA_WORLD_TREE_LORD':'world'}
    explicit={f'FLORA_{prefix}_{realm}':route for prefix,route in [('ANCIENT','ancient'),('FLOWER','flower'),('THORN','thorn')] for realm in range(5,9)}
    explicit.update(FLORA_ANCESTRAL_WORLD_TREE='world',FLORA_MAHAYANA_ORIGIN_TREE='world')
    rules={}
    for n in read(ROOT/'dlc/monster-bloodlines/content/monster_bloodlines.json')['evolutions']:
        if n['species']!='flora' or n['realm_index']>8:continue
        node=n['id'];realm=n['realm_index'];rule=dict(realm=realm)
        if realm<3:rule.update(static='flora-spirit-shared',combat='flora-spirit-shared')
        elif realm==3:rule.update(static=direct[node],combat=direct[node])
        elif node in nascent:rule.update(stage='nascent',route=nascent[node])
        elif node in explicit:rule.update(stage='integration' if realm>=7 else 'nascent',route=explicit[node])
        elif node in ['FLORA_EVERGREEN_EMPEROR','FLORA_WORLD_CANOPY']:rule.update(stage='nascent')
        else:raise AssertionError(('Unreviewed flora node',node))
        rules[node]=rule
    # Only ancient/world Nascent nodes can legally feed the old merged route.
    history={node:route for node,route in nascent.items() if route in ['ancient','world']}
    data=dict(schema_version=1,owner=OWNER,version='4.18.0',fps=20,gender_shared=True,actors=actors,nodes=rules,history_routes=history,
              actions=dict(flora_spell=dict(name='木息',duration=4.0,contacts=[2.1])))
    write(OUT/'manifest.json',data)
    assets['monster.flora.combat_manifest']=dict(file=URL+'manifest.json',requires=[OWNER],sha256=sha(OUT/'manifest.json'))
    write(OUT/'registry.json',dict(assets=assets));catalog['assets'].update(assets);None  # Registry is assembled inside the DLC, never written into core content.
    write(OUT/'provenance.json',dict(generator='OpenAI built-in image_gen',authorization='仿照原有流程完成草木属；元婴开始化人形；所有阶段及分支男女共用立绘，游戏性别与血脉规则不变',
        export='Nearest-neighbour with original soft alpha; common action scale; self-contained DLC runtime files',
        static_forms=15,combat_forms=15,painted_keyposes=135,animation_clips=98,sources=sources,
        prompts=['design/flora-growth-alpha4-20261024/prompts.json','design/flora-combat-alpha4-20261024/prompts.json']))
    assert all(sha(p)==digest for p,digest in previous.items())
    print('15 flora forms, 45 static PNGs, 15 action atlases; existing seven species preserved')

    from scripts.prepare_monster_release_assets import assemble
    assemble()

if __name__=='__main__':main()
