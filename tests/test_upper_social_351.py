import hashlib
import json
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]

def test_fourteen_style_matched_pairs_ship_without_authoring_files():
    folders=[ROOT/'web/assets/pixel/social-351',*ROOT.glob('dlc/*/assets/visual/social-351')]
    total=0
    for folder in folders:
        rows=json.loads((folder/'provenance.json').read_text(encoding='utf8'))['actors'];total+=len(rows)
        for row in rows:
            assert row['reference'].endswith(('dao-male-01.png','dao-female-01.png'))
            for kind,asset in row['assets'].items():
                p=folder/asset['file'].split('/')[-1]
                assert hashlib.sha256(p.read_bytes()).hexdigest()==asset['sha256']
                im=Image.open(p)
                assert im.size==((128,192) if kind=='figure' else (96,96))
                assert im.mode=='RGBA' and set(im.getchannel('A').getdata())=={0,255}
                assert len({p[:3] for p in im.getdata() if p[3]})<=48
                box=im.getbbox();assert 0<box[0]<box[2]<im.width and 0<box[1]<box[3]<im.height
    assert total==14

def test_authored_name_matches_other_official_packages():
    j=json.loads((ROOT/'dlc/authored-techniques/manifest.json').read_text(encoding='utf8'))
    assert j['id']=='official.authored-techniques' and j['name']=='著经立道：薪火相传'
    assert all(len(part)==4 for part in j['name'].split('：'))
