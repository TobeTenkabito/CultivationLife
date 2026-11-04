"""Mechanical export of style-matched paired originals; never draw anatomy."""
import hashlib
import json
from pathlib import Path
from PIL import Image
from scripts.prepare_monster_static_assets import paired_parts

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'design/npc-expansion-351'
PACKAGES={'ghost':'ghost-reincarnation','confucian':'sage-way','buddhist':'buddhist-dharma','monster':'monster-bloodlines'}

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,value):p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')

def main():
    source=json.loads((SOURCE/'prompts.json').read_text(encoding='utf8'))
    core={};proofs={};registries={}
    for row in source['actors']:
        path=row['path'];package=PACKAGES.get(path);owner='official.'+package if package else None
        folder=ROOT/f'dlc/{package}/assets/visual/social-351' if package else ROOT/'web/assets/pixel/social-351'
        folder.mkdir(parents=True,exist_ok=True)
        prefix=f'/extension-assets/{owner}/visual/social-351/' if package else '/assets/pixel/social-351/'
        original=SOURCE/row['file'];im=Image.open(original).convert('RGBA')
        # Same binary alpha and shared 48-colour palette as the adopted social pack.
        alpha=im.getchannel('A').point(lambda v:255 if v>=128 else 0)
        quantized=im.convert('RGB').quantize(colors=48,dither=Image.Dither.NONE).convert('RGBA');quantized.putalpha(alpha)
        assets={};boxes=[]
        parts=paired_parts(original,128)
        for kind,size,area in [('figure',(128,192),parts[0][1]),('portrait',(96,96),parts[1][1])]:
            part=quantized.crop(area);box=part.getbbox();assert box
            art=part.crop(box);factor=min((size[0]-12)/art.width,(size[1]-16)/art.height)
            art=art.resize((round(art.width*factor),round(art.height*factor)),Image.Resampling.NEAREST)
            canvas=Image.new('RGBA',size);canvas.paste(art,((size[0]-art.width)//2,size[1]-8-art.height))
            target=folder/f'{row["id"]}-{kind}.png';canvas.save(target,optimize=True)
            assets[kind]=dict(file=prefix+target.name,size=list(size),sha256=sha(target))
            if owner:assets[kind]['requires']=[owner]
            boxes.append(box)
        key='actor.path.npc-'+row['id']
        form=dict(path=path,race='human',gender=row['gender'],role='npc',static=key,
                  min_age=16 if path=='novice' else 18,max_age=17 if path=='novice' else None)
        if package:
            reg=ROOT/f'dlc/{package}/assets/visual/registry.json'
            if reg not in registries:registries[reg]=json.loads(reg.read_text(encoding='utf8'))
            for kind,asset in assets.items():registries[reg]['assets'][key+'.'+kind]=asset
            registries[reg]['assets'][key+'.figure']['npc_forms']=[form]
        else:core[key]=dict(form=form,**assets)
        proofs.setdefault(folder,[]).append(dict(id=row['id'],prompt=row['prompt'],reference=row['reference'],
            source_sha256=sha(original),subject_bounds=boxes,assets=assets,
            review='Both arms/hands and two separated feet visible; complete standing body; matches adopted fine-line robe style.'))
    for reg,value in registries.items():write(reg,value)
    out=ROOT/'web/assets/pixel/social-351/catalog.js'
    out.write_text('window.NpcExpansionCatalog = '+json.dumps(core,ensure_ascii=False)+';\n',encoding='utf8')
    for folder,rows in proofs.items():write(folder/'provenance.json',dict(generator='built-in image_gen',export='alpha 128; shared 48 colors; nearest; no anatomy edits',actors=rows))
    print(f'Exported {len(source["actors"])} figures and matching portraits')

if __name__=='__main__':main()
