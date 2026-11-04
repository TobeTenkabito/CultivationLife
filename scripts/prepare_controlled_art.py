"""Mechanical export only: paired originals, nearest sampling and existing palette rules."""
import json
import hashlib
from pathlib import Path
from PIL import Image
from scripts.prepare_monster_static_assets import paired_parts

ROOT=Path(__file__).resolve().parents[1]


def main():
    folder=ROOT/'web/assets/pixel/controlled-351';folder.mkdir(parents=True,exist_ok=True)
    recipe=json.loads((ROOT/'design/controlled-351/prompts.json').read_text(encoding='utf8'))
    catalog={}
    for row in recipe['actors']:
        original=ROOT/'design/controlled-351'/row['file']
        im=Image.open(original).convert('RGBA')
        alpha=im.getchannel('A').point(lambda v:255 if v>=128 else 0)
        quantized=im.convert('RGB').quantize(colors=48,dither=Image.Dither.NONE).convert('RGBA');quantized.putalpha(alpha)
        parts=paired_parts(original,128);assets={}
        for kind,size,index in [('figure',(128,192),0),('portrait',(96,96),1)]:
            art=quantized.crop(parts[index][1]);box=art.getbbox();assert box
            art=art.crop(box);scale=min((size[0]-12)/art.width,(size[1]-16)/art.height)
            art=art.resize((round(art.width*scale),round(art.height*scale)),Image.Resampling.NEAREST)
            canvas=Image.new('RGBA',size);canvas.paste(art,((size[0]-art.width)//2,size[1]-8-art.height))
            target=folder/f'{row["id"]}-{kind}.png';canvas.save(target,optimize=True)
            assets[kind]=dict(file='/assets/pixel/controlled-351/'+target.name,size=list(size),
                sha256=hashlib.sha256(target.read_bytes()).hexdigest())
        catalog[row['id']]=assets
        row['sha256']=hashlib.sha256(original.read_bytes()).hexdigest()
        row['review']='完整双臂、双手、分开的双足；沿原细线衣饰风格，未用程序补绘人体。'
    (folder/'catalog.js').write_text('window.ControlledArtCatalog = '+json.dumps(catalog,ensure_ascii=False)+';\n',encoding='utf8')
    (folder/'provenance.json').write_text(json.dumps(recipe,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print('Exported three controlled figures and matching portraits.')


if __name__=='__main__':main()
