"""Offline promotion of user-authorized serpent art; runtime never reads design."""
import importlib.util
import json
from pathlib import Path
from PIL import Image
import numpy as np
from scipy import ndimage

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('serpent_export_helpers',ROOT/'scripts/prepare_monster_fox_assets.py')
F=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(F)
OUT=ROOT/'dlc/monster-bloodlines/assets/visual/serpent'
OWNER='official.monster-bloodlines'
URL=f'/extension-assets/{OWNER}/visual/serpent/'
F.OUT,F.URL=OUT,URL
read,write,sha=F.read,F.write,F.sha


def identity(key,beast):
    return 'serpent-'+key.removeprefix('SERPENT_').lower().replace('_','-')+'-shared' if beast else 'serpent-integration-'+key


def paired_parts(path):
    """Split a faint bridge along transparent space, never through opaque art."""
    if path.name!='dragon-male-v2.png':return F.HELPER.split_parts(path,2,1)
    rgba=np.asarray(Image.open(path).convert('RGBA'))
    lo,hi=800,1130
    cost=(rgba[:,lo:hi,3].astype(float)/8)**2+abs(np.arange(lo,hi)-990)*.0001
    total=cost[0].copy();previous=[]
    for y in range(1,len(cost)):
        candidates=np.array([np.roll(total,d) for d in range(-10,11)])
        for i,d in enumerate(range(-10,11)):
            if d<0:candidates[i,d:]=np.inf
            if d>0:candidates[i,:d]=np.inf
        choice=candidates.argmin(0);previous.append(choice-10)
        total=cost[y]+candidates.min(0)
    x=int(total.argmin());seam=[x]
    for delta in reversed(previous):x-=int(delta[x]);seam.append(x)
    seam=np.array(seam[::-1])+lo
    assert rgba[np.arange(len(seam)),seam,3].max()<128, 'No safe transparent split'
    parts=[]
    for left in [True,False]:
        region=np.arange(rgba.shape[1])[None,:]<seam[:,None]
        if not left:region=~region
        labels,_=ndimage.label(region&(rgba[:,:,3]>=8),np.ones((3,3)))
        sizes=np.bincount(labels.ravel());sizes[0]=0
        keep=region&ndimage.binary_dilation(labels==sizes.argmax(),iterations=4)
        pixels=rgba.copy();pixels[~keep]=0;pixels[pixels[:,:,3]==0]=0
        im=Image.fromarray(pixels);box=im.getbbox();parts.append((im.crop(box),box))
    return parts


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    catalog=read(ROOT/'content/visual_assets.json')
    actors,statics,provenance={}, {}, []
    for beast,static_name,action_name in [
        (True,'serpent-growth-alpha4-20261023','serpent-beast-combat-alpha4-20261023'),
        (False,'serpent-integration-alpha4-20261023','serpent-integration-combat-alpha4-20261023')]:
        static=ROOT/'design'/static_name;folder=ROOT/'design'/action_name
        refs={a['id']:a for a in read(static/'manifest.json')['actors']}
        for key,a in read(folder/'manifest.json')['actors'].items():
            actor_id=identity(key,beast)
            original=static/refs[key]['file'];assert sha(original)==refs[key]['sha256']
            statics[actor_id]=F.static_exports(actor_id,original,parts=paired_parts(original))
            provenance.append(dict(kind='static',identity=actor_id,file=original.relative_to(ROOT).as_posix(),sha256=sha(original)))
            source=folder/a['source']['file'];assert sha(source)==a['source']['sha256']
            atlas_path=folder/a['sheet'];assert sha(atlas_path)==a['sha256']
            atlas=Image.open(atlas_path).convert('RGBA')
            frames=[atlas.crop((i%4*384,i//4*288,i%4*384+384,i//4*288+288)) for i in range(a['unique_frames'])]
            packed=F.pack(frames,OUT/f'{actor_id}-actions.png')
            groups={mode:dict(packed,rects=[packed['rects'][i] for i in clip['frames']],
                frames=len(clip['frames']),poses=clip['poses'],duration=clip['duration'],facing=1,
                cell=[384,288],body_sample_fps=0 if beast else 10) for mode,clip in a['animations'].items()}
            groups['serpent_spell']=groups['attack']
            box=frames[2].getbbox()
            point=[box[2]-8,box[1]+round((box[3]-box[1])*.24)] if beast else [235,152]
            color=('#baa5dc' if 'sky' in actor_id or 'thunder' in actor_id or 'serpent-female' in actor_id
                   else '#7ebbd9' if 'abyss' in actor_id else '#c9af7d' if 'rock' in actor_id else '#8cbdac')
            actors[actor_id]=dict(name=a['name'],role='hero',faction='serpent',creature=beast,
                sex=None if beast else a['gender'],cell=[384,288],anchor=[192,256],
                attack_action='serpent_spell',domain_action='idle' if beast else 'domain',release_point=point,
                energy_color=color,hit_offset=[25,-65] if beast else [23,-85],
                guard_shape=dict(cx=0,cy=-66,rx=98,ry=78) if beast else dict(cx=4,cy=-86,rx=70,ry=94),animations=groups)
            provenance.append(dict(kind='actions',identity=actor_id,file=source.relative_to(ROOT).as_posix(),sha256=sha(source)))
            catalog['assets'][actor_id+'.actions']=dict(file=packed['sheet'],size=packed['size'],sha256=packed['sha256'],requires=[OWNER])
    for actor_id,rows in statics.items():
        for kind,row in rows.items():catalog['assets'][f'actor.monster.{actor_id}.{kind}']=row
    nodes={}
    routes={'SERPENT_ANCESTRAL_DRAGON':'dragon','SERPENT_COSMIC_ANCESTOR':'serpent',
            'SERPENT_MAHAYANA_DRAGON':'dragon','SERPENT_MAHAYANA_ORIGIN':'serpent'}
    for n in read(ROOT/'dlc/monster-bloodlines/content/monster_bloodlines.json')['evolutions']:
        if n['species']!='serpent':continue
        realm=n['realm_index'];node=n['id']
        if realm<=3:
            key='SERPENT_SPIRIT' if realm<3 else node
            actor_id=identity(key,True)
            if actor_id in actors:nodes[node]=dict(realm=realm,static=actor_id,combat=actor_id)
        elif node in routes:nodes[node]=dict(realm=realm,stage='integration',route=routes[node])
    data=dict(schema_version=1,owner=OWNER,version='4.18.0',fps=20,actors=actors,nodes=nodes,history_routes={},
        actions=dict(serpent_spell=dict(name='蛇属灵息',duration=4.0,contacts=[2.1])))
    write(OUT/'manifest.json',data)
    catalog['assets']['monster.serpent.combat_manifest']=dict(file=URL+'manifest.json',requires=[OWNER],sha256=sha(OUT/'manifest.json'))
    write(OUT/'registry.json',dict(assets={k:v for k,v in catalog['assets'].items() if v['file'].startswith(URL)}))
    None  # Registry is assembled inside the DLC, never written into core content.
    write(OUT/'provenance.json',dict(generator='OpenAI built-in image_gen',authorization='再补全先前境界的关键帧和动作动画；那就更新妖族dlc版本，并将素材放入',
        export='nearest-neighbour; original soft alpha; separate source figures; no runtime design dependency',
        painted_keyposes=99,animation_clips=70,static_forms=11,combat_forms=11,sources=provenance,
        prompts=['design/serpent-beast-combat-alpha4-20261023/prompts.json','design/serpent-integration-combat-alpha4-20261023/prompts.json'],
        unsupported_realms=[4,5,6],note='Nascent forms not drawn; preserve existing fallback, never show Integration art early.'))
    print('11 serpent forms, 33 static PNGs and 11 action atlases promoted')


    from scripts.prepare_monster_release_assets import assemble
    assemble()

if __name__=='__main__':main()
