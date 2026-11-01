"""Check shipped art, or mechanically export the selected image_gen pixel sources."""
import argparse,hashlib,json,sys
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
DIRECTORY=ROOT/'web/assets/pixel/immortal-refinement'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=ROOT/'design/immortal-artifacts-20261101/source')
    mode=parser.add_mutually_exclusive_group();mode.add_argument('--write',action='store_true');mode.add_argument('--check',action='store_true')
    args=parser.parse_args()
    provenance=json.loads((DIRECTORY/'provenance.json').read_text(encoding='utf-8'))
    path=ROOT/'content/visual_assets.json';catalog=json.loads(path.read_text(encoding='utf-8'))
    for row in provenance['assets']:
        key=row['id'];icon_path=DIRECTORY/f'{key}-icon.png';portrait_path=DIRECTORY/f'{key}-portrait.png'
        if args.write:
            source=args.source/f'{key}-pixel-v1.png'
            if hashlib.sha256(source.read_bytes()).hexdigest()!=row['source_sha256']:raise ValueError('选稿哈希变化，先人工核对来源：'+key)
            image=Image.open(source).convert('RGBA')
            image=image.crop(image.getchannel('A').point(lambda n:255 if n>=128 else 0).getbbox())
            factor=26/max(image.size)
            image=image.resize((max(1,round(image.width*factor)),max(1,round(image.height*factor))),Image.Resampling.NEAREST)
            icon=Image.new('RGBA',(32,32));icon.alpha_composite(image,((32-image.width)//2,(32-image.height)//2))
            icon.putalpha(icon.getchannel('A').point(lambda n:255 if n>=128 else 0))
            icon.save(icon_path);icon.resize((128,128),Image.Resampling.NEAREST).save(portrait_path)
        with Image.open(icon_path) as icon,Image.open(portrait_path) as portrait:
            assert icon.mode==portrait.mode=='RGBA' and icon.size==(32,32) and portrait.size==(128,128)
            assert set(icon.getchannel('A').getdata()) <= {0,255}
            box=icon.getchannel('A').getbbox();assert box and max(box[2]-box[0],box[3]-box[1])<=26
            assert list(portrait.getdata())==list(icon.resize((128,128),Image.Resampling.NEAREST).getdata())
        for suffix,file in (('',icon_path),('.portrait',portrait_path)):
            record=catalog['assets']['material.'+key+suffix]
            digest=hashlib.sha256(file.read_bytes()).hexdigest()
            if args.write:record['sha256']=digest
            assert record['sha256']==digest and record['requires']==[]
    if args.write:path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Four reference-matched material icons and portraits: size, alpha, source bounds, pixel identity and catalog SHA-256 passed')


if __name__=='__main__':main()
