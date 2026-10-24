"""Offline promotion of aquatic originals; shipped assets never depend on design."""
import math
from pathlib import Path
from PIL import Image
from scripts.prepare_monster_static_assets import export,read,write,sha,OWNER

ROOT=Path(__file__).resolve().parents[1]
STATIC=ROOT/'design/aquatic-growth-alpha4-20261024'
ACTION=ROOT/'design/aquatic-combat-alpha4-20261024'
OUT=ROOT/'dlc/monster-bloodlines/assets/visual/aquatic'
URL=f'/extension-assets/{OWNER}/visual/aquatic/'

def identity(a):
    return 'aquatic-'+a['id']+('-shared' if a['beast'] else '')

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
    previous={p:sha(p) for species in ['fox','serpent','avian','ape','turtle','insect'] for p in (OUT.parent/species).rglob('*') if p.is_file()}
    statics={a['id']:a for a in read(STATIC/'manifest.json')['actors']}
    for key,a in read(ACTION/'manifest.json')['actors'].items():
        ident=identity(a);s=statics[key];source=STATIC/s['file'];assert sha(source)==s['sha256']
        rows,boxes=export(ident,source,OUT,URL)
        for kind,row in rows.items():assets[f'actor.monster.{ident}.{kind}']=row
        sources.append(dict(kind='static',identity=ident,file=source.relative_to(ROOT).as_posix(),sha256=sha(source),subject_bounds=boxes))
        source=ACTION/a['source']['file'];assert sha(source)==a['source']['sha256']
        sources.append(dict(kind='actions',identity=ident,file=source.relative_to(ROOT).as_posix(),sha256=sha(source)))
        path=ACTION/a['sheet'];assert sha(path)==a['sha256'];atlas=Image.open(path).convert('RGBA')
        frames=[atlas.crop((i%4*384,i//4*288,i%4*384+384,i//4*288+288)) for i in range(a['unique_frames'])]
        packed=pack(frames,OUT/f'{ident}-actions.png')
        groups={mode:dict(packed,rects=[packed['rects'][i] for i in clip['frames']],frames=len(clip['frames']),
                         poses=clip['poses'],duration=clip['duration'],facing=1,cell=[384,288],
                         body_sample_fps=0 if a['beast'] else 10) for mode,clip in a['animations'].items()}
        groups['aquatic_spell']=groups['attack'];box=frames[2].getbbox()
        # Reviewed mouth height in each painted release pose, relative to its bounds.
        mouth_height={'spirit':.24,'dragon-koi':.32,'golden-leaper':.32,'young-kun':.16,
                      'abyss-whale':.14,'glacial-whale':.14,'mirage-whale':.14}
        point=[box[2]-8,box[1]+round((box[3]-box[1])*mouth_height[key])] if a['beast'] else [235,152]
        actors[ident]=dict(name=a['name'],role='hero',faction='aquatic',creature=a['beast'],sex=None if a['beast'] else a['gender'],
            cell=[384,288],anchor=[192,256],attack_action='aquatic_spell',domain_action='idle' if a['beast'] else 'domain',
            release_point=point,energy_color=a['colors'][0],hit_offset=[25,-65] if a['beast'] else [23,-85],
            guard_shape=dict(cx=0,cy=-66,rx=98,ry=78) if a['beast'] else dict(cx=4,cy=-86,rx=70,ry=94),animations=groups)
        assets[ident+'.actions']=dict(file=packed['sheet'],size=packed['size'],sha256=packed['sha256'],requires=[OWNER])
    direct={a['node']:identity(a) for a in statics.values() if a['beast']}
    nascent={'AQUATIC_SEA_SOVEREIGN':'koi','AQUATIC_WHALE_SOVEREIGN':'whale','AQUATIC_KUN_SOVEREIGN':'kun'}
    integration={'AQUATIC_KOI_7':'koi','AQUATIC_KOI_8':'koi','AQUATIC_WHALE_7':'whale','AQUATIC_WHALE_8':'whale',
                 'AQUATIC_ANCESTRAL_KUN':'kun','AQUATIC_MAHAYANA_KUN':'kun'}
    rules={}
    for n in read(ROOT/'dlc/monster-bloodlines/content/monster_bloodlines.json')['evolutions']:
        if n['species']!='aquatic' or n['realm_index']>8:continue
        node=n['id'];realm=n['realm_index'];rule=dict(realm=realm)
        if realm<3:rule.update(static='aquatic-spirit-shared',combat='aquatic-spirit-shared')
        elif realm==3:rule.update(static=direct[node],combat=direct[node])
        elif node in integration:rule.update(stage='integration',route=integration[node])
        elif node in nascent:rule.update(stage='nascent',route=nascent[node])
        elif node in ['AQUATIC_KOI_5','AQUATIC_KOI_6']:rule.update(stage='nascent',route='koi')
        elif node in ['AQUATIC_WHALE_5','AQUATIC_WHALE_6']:rule.update(stage='nascent',route='whale')
        elif node in ['AQUATIC_OCEAN_EMPEROR','AQUATIC_WORLD_KUN']:rule.update(stage='nascent')
        else:raise AssertionError(('Unreviewed aquatic node',node))
        rules[node]=rule
    # The two old merged nodes descend only from koi or kun Nascent nodes.
    history={node:route for node,route in nascent.items() if route!='whale'}
    data=dict(schema_version=1,owner=OWNER,version='4.18.0',fps=20,actors=actors,nodes=rules,history_routes=history,
              actions=dict(aquatic_spell=dict(name='水息',duration=4.0,contacts=[2.1])))
    write(OUT/'manifest.json',data)
    assets['monster.aquatic.combat_manifest']=dict(file=URL+'manifest.json',requires=[OWNER],sha256=sha(OUT/'manifest.json'))
    write(OUT/'registry.json',dict(assets=assets));catalog['assets'].update(assets);None  # Registry is assembled inside the DLC, never written into core content.
    write(OUT/'provenance.json',dict(generator='OpenAI built-in image_gen',authorization='仿照前面的流程一次性完成水属；天海神鲲路线江南水乡风格，鲤鱼路线和式锦鲤风格；合体锦鲤按用户要求重设计以体现修为差距',
        export='Nearest-neighbour with original soft alpha; common action scale; self-contained DLC runtime files',
        static_forms=19,combat_forms=19,painted_keyposes=171,animation_clips=126,sources=sources,
        prompts=['design/aquatic-growth-alpha4-20261024/prompts.json','design/aquatic-combat-alpha4-20261024/prompts.json']))
    assert all(sha(p)==digest for p,digest in previous.items())
    print('19 aquatic forms, 57 static PNGs, 19 action atlases; existing six species preserved')

    from scripts.prepare_monster_release_assets import assemble
    assemble()

if __name__=='__main__':main()
