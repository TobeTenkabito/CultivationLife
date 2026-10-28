"""Pack sixteen original painted snow frames with transparent gutters."""
from pathlib import Path
from PIL import Image
from scripts.prepare_swimwear_assets import separate
from scripts.prepare_monster_static_assets import read, write, sha

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'design/christmas-effects-20261029'
OUT = ROOT / 'web/assets/pixel/holiday'


def main():
    source = SOURCE / 'snow-keyframes.png'
    # The final small melting shard deliberately has fewer than 1000 pixels.
    parts = separate(source, 4, 16, min_pixels=500)
    scale = min(344/max(im.width for im, _ in parts),248/max(im.height for im, _ in parts))
    atlas = Image.new('RGBA', (1536,1152))
    for i,(art,_) in enumerate(parts):
        art = art.resize((round(art.width*scale),round(art.height*scale)),Image.Resampling.LANCZOS)
        atlas.paste(art,(i%4*384+(384-art.width)//2,i//4*288+(288-art.height)//2))
    target = OUT/'christmas-keyframes.png'
    atlas.save(target,optimize=True)
    catalog = read(ROOT/'content/visual_assets.json')
    catalog['assets']['effect.christmas.keyframes'] = dict(file='/assets/pixel/holiday/'+target.name,
        size=list(atlas.size),sha256=sha(target),requires=[])
    write(ROOT/'content/visual_assets.json',catalog)
    write(OUT/'christmas-effects-provenance.json',dict(generator='OpenAI built-in image_gen',
        source=source.relative_to(ROOT).as_posix(),source_sha256=sha(source),sha256=sha(target),
        frames=16,grid=[4,4],cell=[384,288],source_rects=[box for _,box in parts],scale=scale,
        export='Original RGBA component crops and proportional atlas packing; no procedural snow painting',
        prompt=read(SOURCE/'prompt.json')))
    print('Christmas effects: 16 painted snow keyframes, shared by male/female Christmas costumes')


if __name__ == '__main__': main()
