"""Offline, mechanical sprite extraction; runtime never depends on design files."""
import hashlib
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'design/alpha6-map-events-20261025'
OUT = ROOT / 'web/assets/pixel/buildings'
# Reviewed source rectangles: the generated sheets have uneven gutters. Do not
# divide the whole image into equal cells and cut roofs or pick up nearby sprites.
BOUNDS = {
    'buildings-source.png': [
        [(24,81,323,269),(336,32,682,281),(697,5,1082,293),(1091,74,1406,292)],
        [(18,292,325,543),(342,280,666,555),(681,293,1085,566),(1090,301,1406,556)],
        [(19,596,311,814),(331,547,677,822),(690,566,1085,818),(1103,585,1404,817)],
        [(7,853,276,1075),(331,841,657,1088),(679,814,1072,1104),(1089,814,1415,1088)],
    ],
    'industries-source.png': [
        [(23,62,217,199),(256,33,474,199),(502,18,737,210),(763,5,999,211),(1020,11,1264,209)],
        [(10,254,213,405),(246,229,475,407),(493,216,736,416),(751,222,1011,425),(1016,201,1269,426)],
        [(9,468,218,624),(241,440,477,626),(494,429,738,632),(755,438,1005,630),(1017,428,1269,632)],
        [(20,679,205,823),(246,642,468,834),(481,635,733,834),(742,625,1007,836),(1010,632,1276,836)],
        [(26,865,215,1028),(249,860,470,1039),(487,823,734,1037),(747,830,1004,1044),(1010,836,1276,1048)],
        [(17,1057,216,1205),(246,1052,470,1221),(485,1053,732,1219),(743,1050,1001,1222),(1010,1048,1278,1230)],
    ],
}


def export():
    OUT.mkdir(parents=True, exist_ok=True)
    records = {}
    for filename, families, columns in [
        ('buildings-source.png', ['city', 'cave', 'industry', 'temple'], ['1', '2', '3', 'ruin']),
        ('industries-source.png', ['farm', 'mine', 'hunt', 'alchemy', 'forge', 'shop'], ['1', '2', '3', '4', '5']),
    ]:
        source = SOURCE / filename
        image = Image.open(source).convert('RGBA')
        w, h = image.size
        for row, family in enumerate(families):
            for col, stage in enumerate(columns):
                bounds = BOUNDS[filename][row][col]
                sprite = image.crop(bounds)
                box = sprite.getchannel('A').getbbox()
                if not box:
                    raise ValueError(f'Empty sprite {family}/{stage}')
                sprite = sprite.crop(box)
                scale = min(88/sprite.width, 88/sprite.height)
                sprite = sprite.resize((max(1,round(sprite.width*scale)),max(1,round(sprite.height*scale))), Image.Resampling.NEAREST)
                tile = Image.new('RGBA', (96,96))
                tile.alpha_composite(sprite, ((96-sprite.width)//2,92-sprite.height))
                target = OUT / f'{family}-{stage}.png'
                tile.save(target, optimize=True)
                records[target.name] = dict(source=filename, source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    crop=list(bounds), sha256=hashlib.sha256(target.read_bytes()).hexdigest(), size=[96,96])
    (OUT/'manifest.json').write_text(json.dumps(dict(schema=1, method='nearest-neighbor isolated atlas cells', assets=records),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Exported {len(records)} building sprites')


if __name__ == '__main__':
    export()
