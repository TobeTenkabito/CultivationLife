"""Shipped assets, public ownership and safe optional extension routes."""
import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image
from cultivation_life.visual_assets import catalog, public_catalog, extension_asset
from cultivation_life.errors import NotFoundError

ROOT=Path(__file__).resolve().parents[1]


def test_shipped_reviewed_assets_are_self_contained():
    from cultivation_life.content_registry import EXTENSION_REPORT
    source=dict(catalog(ROOT), assets=public_catalog(ROOT,EXTENSION_REPORT)['assets'])
    assert len(source['assets'])==1497 and len(source['maps'])==11
    assert len(source['items'])==1165
    packages={json.loads(p.read_text(encoding='utf-8'))['id']:p.parent for p in (ROOT/'dlc').glob('*/manifest.json')}
    for identity,row in source['assets'].items():
        if row['file'].startswith('/extension-assets/'):
            _,_,owner,relative=row['file'].split('/',3)
            path=packages[owner]/'assets'/relative
            assert owner in row['requires']
            assert not (ROOT/f'web/assets/pixel/v2/icons/{identity}.png').exists()
        else:path=ROOT/'web'/row['file'].lstrip('/')
        assert path.is_file(), identity
        assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256']
        if path.suffix=='.json':
            data=json.loads(path.read_text(encoding='utf-8'))
            if row.get('domain_styles'):
                assert data['styles']==row['domain_styles'] and all(r['owner']==owner for r in data['styles'])
            elif row.get('domain_controls'):
                assert data['controls']==row['domain_controls'] and all(r['owner']==owner for r in data['controls'])
            else:assert data['owner']==owner and set(data['actors'])==set(row['combat_actors'])
            continue
        with Image.open(path) as image:
            assert list(image.size)==row['size']
            if row.get('domain_art'):
                assert image.mode=='RGBA' and image.getchannel('A').histogram()[0]/(image.width*image.height)>.60
            elif 'official.monster-bloodlines' in row.get('requires',[]):
                assert image.mode=='RGBA'
                assert identity.startswith(('actor.monster.fox-','fox-','actor.monster.serpent-','serpent-',
                                            'actor.monster.avian-','avian-','actor.monster.ape-','ape-','actor.monster.turtle-','turtle-','actor.monster.insect-','insect-','actor.monster.aquatic-','aquatic-','actor.monster.flora-','flora-'))
            elif any(p in row.get('requires',[]) for p in ['official.ghost-reincarnation','official.sage-way','official.buddhist-dharma','official.asura-manifestation']):
                assert image.mode=='RGBA' and image.getextrema()[-1][0]==0
                if identity.startswith('actor.path.'):
                    assert image.size=={'portrait':(128,128),'figure':(256,288),'thumbnail':(128,144)}[identity.rsplit('.',1)[1]]
                else:assert identity.endswith('.actions') and max(image.size)<=2048
            elif identity.startswith('map.'):assert image.size==(768,576)
            else:
                assert image.mode=='RGBA' and image.size==(32,32)
                assert set(image.getchannel('A').getdata()) <= {0,255}
    for row in source['maps'].values():
        assert row['asset'] in source['assets']
        for p in row['places'].values():assert 0<=p['x']<=100 and 0<=p['y']<=100
    assert set(public_catalog(ROOT,[])['maps'])==set(source['maps'])


def test_exclusive_treasure_source_overrides_shared_definition_location():
    source=catalog(ROOT)
    pools=json.loads((ROOT/'dlc/guixu-tide/content/guixu_tide.json').read_text(encoding='utf-8'))
    exclusive={row['content_id'] for dungeon in pools['dungeons'] for row in dungeon['treasure_pool'] if row.get('exclusive_source')=='guixu_tide'}
    private=set(source['items'])&exclusive
    assert len(private)==440
    disabled=public_catalog(ROOT,[])
    loaded=[{'id':'official.guixu-tide','status':'loaded'}]
    enabled=public_catalog(ROOT,loaded)
    for identity in private:
        assert source['items'][identity]['requires']==['official.guixu-tide']
        assert identity not in disabled['items'] and identity in enabled['items']
    identity=source['items']['guixu_canghai_equipment_01']['asset']
    url=source['assets'][identity]['file']
    assert url.startswith('/extension-assets/official.guixu-tide/')
    assert extension_asset(ROOT,ROOT,loaded,url).is_file()
    with pytest.raises(NotFoundError):extension_asset(ROOT,ROOT,[],url)
    assert 'healing_pill' in disabled['items'] and len(disabled['maps'])==11


def test_real_http_disabled_pack_cannot_serve_installed_exclusive_image(monkeypatch):
    import threading
    import urllib.request
    import urllib.error
    from http.server import ThreadingHTTPServer
    from cultivation_life import server
    monkeypatch.setattr(server,'ENGINE_ROOT',ROOT)
    monkeypatch.setattr(server,'APP_ROOT',ROOT)
    monkeypatch.setattr(server,'EXTENSION_REPORT',[{'id':'official.guixu-tide','status':'disabled'}])
    class Handler(server.Handler):
        def log_message(self,*args):pass
    http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=http.serve_forever,daemon=True).start()
    identity=catalog(ROOT)['items']['guixu_canghai_equipment_01']['asset']
    row=catalog(ROOT)['assets'][identity]
    base=f'http://127.0.0.1:{http.server_port}'
    try:
        with urllib.request.urlopen(base+'/api/visual-assets') as response:assert identity not in json.load(response)['assets']
        with pytest.raises(urllib.error.HTTPError) as failure:urllib.request.urlopen(base+row['file'])
        assert failure.value.code==404
        monkeypatch.setattr(server,'EXTENSION_REPORT',[{'id':'official.guixu-tide','status':'loaded'}])
        with urllib.request.urlopen(base+row['file']) as response:assert hashlib.sha256(response.read()).hexdigest()==row['sha256']
    finally:http.shutdown();http.server_close()


def test_dlc_exclusive_assets_require_actual_loaded_package_and_safe_path(tmp_path):
    (tmp_path/'content').mkdir()
    package=tmp_path/'dlc/example';(package/'assets/visual').mkdir(parents=True)
    (package/'manifest.json').write_text(json.dumps({'id':'example'}))
    bitmap=package/'assets/visual/only.png';bitmap.write_bytes(b'fixture')
    url='/extension-assets/example/visual/only.png'
    document=dict(schema_version=1,assets={'only':{'file':url,'requires':['example']}},
        items={'private':{'asset':'only','requires':['example']}},molds={},plants={},crafting_materials={},maps={})
    manifest=tmp_path/'content/visual_assets.json';manifest.write_text(json.dumps(document))
    for extensions in [[],[{'id':'example','status':'disabled'}],[{'id':'unrelated','status':'loaded'}]]:
        assert not public_catalog(tmp_path,extensions)['assets']
        assert not public_catalog(tmp_path,extensions)['items']
        with pytest.raises(NotFoundError):extension_asset(tmp_path,tmp_path,extensions,url)
    loaded=[{'id':'example','status':'loaded'}]
    assert extension_asset(tmp_path,tmp_path,loaded,url)==bitmap.resolve()
    with pytest.raises(NotFoundError):extension_asset(tmp_path,tmp_path,loaded,'/extension-assets/example/../../manifest.json')
    document['assets']['only']['file']='/extension-assets/example/../manifest.json'
    manifest.write_text(json.dumps(document));catalog.cache_clear()
    with pytest.raises(NotFoundError):extension_asset(tmp_path,tmp_path,loaded,document['assets']['only']['file'])


def test_default_mode_and_no_battle_animation_or_state_fields():
    from cultivation_life.ui_preferences import DEFAULTS
    assert DEFAULTS['pixel_art'] is False
    html=(ROOT/'web/index.html').read_text(encoding='utf-8')
    assert html.count('<b>启用新版界面</b>')==2
    for name in ['pixel-library.js','pixel-inventory.js','pixel-map.js','pixel-natal.js']:
        source=(ROOT/'web'/name).read_text(encoding='utf-8')
        assert 'setInterval(' not in source and 'Math.random(' not in source
        assert '/map-travel' not in source and '/choice' not in source


def test_balanced_release_scheduling_runs_all_modules_once(tmp_path):
    from scripts.verify_scoped_release import balanced_test_shards
    modules=['tests/test_slow.py','tests/test_fast.py','tests/test_new.py']
    history=tmp_path/'old.xml'
    history.write_text('<testsuites><testsuite><testcase classname="tests.test_slow" time="100"/><testcase classname="tests.test_fast" time="1"/></testsuite></testsuites>')
    shards=balanced_test_shards(modules,2,[history])
    assert sorted(name for shard in shards for name in shard)==sorted(modules)
    assert shards[0]==['tests/test_slow.py']
    assert shards[1]==['tests/test_fast.py','tests/test_new.py']
