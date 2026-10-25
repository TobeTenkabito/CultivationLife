"""Normalize authored contour strokes; register base/DLC assets with their owners.

Art is generated with built-in imagegen. This is only mask/size export, no drawing.
"""
import base64
import hashlib
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
STUDY=ROOT/'design/domain-outlines-20261025'
PACKAGES=['asura-manifestation','monster-bloodlines','ghost-reincarnation']
def read(p):return json.loads(p.read_text(encoding='utf8'))
def write(p,value):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    recipes=read(STUDY/'sources.json')
    documents={None:read(ROOT/'content/domain_styles.json')}
    documents.update({pkg:read(ROOT/f'dlc/{pkg}/assets/visual/domain-styles.json') for pkg in PACKAGES})
    registries={None:read(ROOT/'content/visual_assets.json')}
    registries.update({pkg:read(ROOT/f'dlc/{pkg}/assets/visual/registry.json') for pkg in PACKAGES})
    ownership={row['id']:pkg for pkg,doc in documents.items() for row in doc['styles']}
    with sync_playwright() as pw:
        browser=pw.chromium.launch();page=browser.new_page()
        for job in recipes['jobs']:
            identity=job['id'];source=STUDY/'raw'/f'{identity}.png'
            if not source.exists():continue
            owner=ownership[identity]
            out=ROOT/(f'dlc/{owner}/assets/visual/domains' if owner else 'web/assets/pixel/domains')
            out.mkdir(parents=True,exist_ok=True);size=[320,512] if identity=='ghost-shore' else [640,320]
            value=page.evaluate('''async ({src,size})=>{
              const im=new Image();im.src=src;await im.decode();
              const c=document.createElement('canvas');c.width=im.width;c.height=im.height;
              const ctx=c.getContext('2d');ctx.drawImage(im,0,0);
              const pixels=ctx.getImageData(0,0,c.width,c.height),p=pixels.data;
              for(let i=0;i<p.length;i+=4){
                const ink=Math.max(0,Math.min(1,(130-Math.max(p[i],p[i+1],p[i+2]))/85));
                p[i+3]*=ink;p[i]=p[i+1]=p[i+2]=255;
              }
              ctx.putImageData(pixels,0,0);
              const out=document.createElement('canvas');[out.width,out.height]=size;
              const oc=out.getContext('2d');oc.imageSmoothingQuality='high';oc.drawImage(c,0,0,...size);
              const final=oc.getImageData(0,0,...size);let count=0;
              for(let i=3;i<final.data.length;i+=4){if(final.data[i]<12)final.data[i]=0;else count++;}
              oc.putImageData(final,0,0);return {png:out.toDataURL().split(',')[1],coverage:count/(size[0]*size[1])};
            }''',dict(src='data:image/png;base64,'+base64.b64encode(source.read_bytes()).decode(),size=size))
            assert .003<value['coverage']<.40,(identity,value['coverage'])
            target=out/f'{identity}-outline.png';target.write_bytes(base64.b64decode(value['png']))
            url=(f'/extension-assets/official.{owner}/visual/domains/' if owner else '/assets/pixel/domains/')+target.name
            scene=dict(file=url,size=size,sha256=digest(target),ink=True,motion=job['motion'])
            if identity=='time':scene['clock']=[.49,.59,.113]
            next(row for row in documents[owner]['styles'] if row['id']==identity)['scene']=scene
            registries[owner]['assets']['domain.ink.'+identity]=dict(file=url,size=size,sha256=scene['sha256'],requires=['official.'+owner] if owner else [],domain_art=True)
            write(out/f'{identity}-provenance.json',dict(mode=recipes['mode'],prompt=recipes['prefix']+job['subject'],source=str(source.relative_to(ROOT)).replace('\\','/'),source_sha256=digest(source),file=target.name,sha256=scene['sha256'],coverage=value['coverage'],export='Extract black authored strokes to alpha; discard light surfaces; white RGB; resize with Canvas high smoothing, zero alpha below12.'))
            print(identity,round(value['coverage'],4))
        browser.close()
    for owner,document in documents.items():
        p=ROOT/(f'dlc/{owner}/assets/visual/domain-styles.json' if owner else 'content/domain_styles.json');write(p,document)
        if owner:registries[owner]['assets'][owner+'.domain_styles'].update(domain_styles=document['styles'],sha256=digest(p))
        write(ROOT/(f'dlc/{owner}/assets/visual/registry.json' if owner else 'content/visual_assets.json'),registries[owner])

if __name__=='__main__':main()
