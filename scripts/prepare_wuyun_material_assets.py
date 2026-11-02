"""Mechanical exports of the five reference-matched image_gen material sources."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
OWNER='official.asura-manifestation'
DIRECTORY=ROOT/'dlc/asura-manifestation/assets/visual/wuyun-materials'
DESIGN=ROOT/'design/wuyun-materials-20261102'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main():
    global OWNER,DIRECTORY,DESIGN
    parser=argparse.ArgumentParser()
    parser.add_argument('--family',choices=['wuyun','monster-body'],default='wuyun')
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--write',action='store_true');mode.add_argument('--check',action='store_true')
    args=parser.parse_args()
    if args.family=='monster-body':
        OWNER='official.monster-bloodlines'
        DIRECTORY=ROOT/'dlc/monster-bloodlines/assets/visual/body-materials'
        DESIGN=ROOT/'design/monster-body-20261102'
    registry_path=DIRECTORY.parent/'registry.json'
    mapping_path=ROOT/'content/visual_assets.json'
    registry=json.loads(registry_path.read_text(encoding='utf-8'))
    mapping=json.loads(mapping_path.read_text(encoding='utf-8'))
    if args.write:
        DIRECTORY.mkdir(parents=True,exist_ok=True)
        prompts=json.loads((DESIGN/'prompts.json').read_text(encoding='utf-8'))
        provenance=dict(method=prompts['method'],reference=prompts['reference'],
            reference_sha256=digest(ROOT/prompts['reference']),
            prompt_file=(DIRECTORY/'prompts.json').relative_to(ROOT).as_posix(),
            normalization='Alpha>=128 crop; longest edge 26px; centered 32px binary alpha; 128px nearest-neighbor portrait.',
            exporter='scripts/prepare_wuyun_material_assets.py',assets=[])
        for row in prompts['assets']:
            key=row['id'];source=DESIGN/'source'/f'{key}-pixel-v1.png'
            with Image.open(source) as original:
                image=original.convert('RGBA')
            image=image.crop(image.getchannel('A').point(lambda v:255 if v>=128 else 0).getbbox())
            scale=26/max(image.size)
            image=image.resize(tuple(max(1,round(v*scale)) for v in image.size),Image.Resampling.NEAREST)
            icon=Image.new('RGBA',(32,32))
            icon.alpha_composite(image,((32-image.width)//2,(32-image.height)//2))
            icon.putalpha(icon.getchannel('A').point(lambda v:255 if v>=128 else 0))
            icon.save(DIRECTORY/f'{key}-icon.png')
            icon.resize((128,128),Image.Resampling.NEAREST).save(DIRECTORY/f'{key}-portrait.png')
            provenance['assets'].append(dict(id=key,name=row['name'],source=source.relative_to(ROOT).as_posix(),source_sha256=digest(source)))
            for suffix,kind,size in [('', 'icon',32),('.portrait','portrait',128)]:
                file=DIRECTORY/f'{key}-{kind}.png'
                registry['assets']['material.'+key+suffix]=dict(
                    file=f'/extension-assets/{OWNER}/visual/{DIRECTORY.name}/{file.name}',
                    size=[size,size],sha256=digest(file),requires=[OWNER])
            mapping['items'][key]=dict(asset='material.'+key,requires=[OWNER])
        save(DIRECTORY/'prompts.json',dict(method=prompts['method'],reference=prompts['reference'],
            assets=[{k:v for k,v in row.items() if k!='generated_source'} for row in prompts['assets']]))
        save(DIRECTORY/'provenance.json',provenance);save(registry_path,registry);save(mapping_path,mapping)
    provenance=json.loads((DIRECTORY/'provenance.json').read_text(encoding='utf-8'))
    assert len(provenance['assets'])==5
    for row in provenance['assets']:
        key=row['id'];icon_path=DIRECTORY/f'{key}-icon.png';portrait_path=DIRECTORY/f'{key}-portrait.png'
        with Image.open(icon_path) as icon,Image.open(portrait_path) as portrait:
            assert icon.mode==portrait.mode=='RGBA' and icon.size==(32,32) and portrait.size==(128,128)
            assert set(icon.getchannel('A').getdata())<={0,255}
            bounds=icon.getchannel('A').getbbox()
            assert bounds and max(bounds[2]-bounds[0],bounds[3]-bounds[1])<=26
            assert portrait.tobytes()==icon.resize((128,128),Image.Resampling.NEAREST).tobytes()
        assert mapping['items'][key]==dict(asset='material.'+key,requires=[OWNER])
        for suffix,file in [('',icon_path),('.portrait',portrait_path)]:
            entry=registry['assets']['material.'+key+suffix]
            assert entry['sha256']==digest(file) and entry['requires']==[OWNER]
            assert entry['file']==f'/extension-assets/{OWNER}/visual/{DIRECTORY.name}/{file.name}'
    print('Five DLC-owned material icons and portraits: dimensions, alpha, pixel identity, mappings and SHA-256 passed')


if __name__=='__main__':main()
