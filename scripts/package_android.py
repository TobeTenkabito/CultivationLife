"""Publish locally only after exact signed APK and Android 12 acceptance succeed."""
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1]
VERSION='1.41.0'


def main():
    logs={name:(ROOT/'build'/name).read_text(encoding='utf-8',errors='replace') for name in (
        'release-1410-tests.log','release-1410-final-targeted.log','browser-world-1410.log','transition-rng-1410.log','android-world-1410.log',
        'android-signed-upgrade-1410.log','android-signed-initial-1410.log',
        'android-signature-1410.log','android-metadata-1410.log')}
    passed=re.search(r'(\d+) passed in',logs['release-1410-tests.log'])
    assert passed and 'failed' not in logs['release-1410-tests.log']
    assert '80 passed' in logs['release-1410-final-targeted.log']
    assert 'state isolation passed' in logs['browser-world-1410.log']
    assert 'passed' in logs['transition-rng-1410.log']
    for name in ('android-world-1410.log','android-signed-upgrade-1410.log','android-signed-initial-1410.log'):
        assert 'status=passed' in logs[name] and 'status=failed' not in logs[name],name
    assert 'Verifies' in logs['android-signature-1410.log']
    assert "sdkVersion:'31'" in logs['android-metadata-1410.log']
    assert "versionName='1.41.0-android.4'" in logs['android-metadata-1410.log']
    assert "versionCode='4'" in logs['android-metadata-1410.log']
    assert 'application-debuggable' not in logs['android-metadata-1410.log']
    lint=(ROOT/'android/app/build/reports/lint-results-release.txt').read_text(encoding='utf-8')
    assert lint.strip()=='No issues found.'
    source=ROOT/'android/app/build/outputs/apk/release/app-release.apk'
    installed_log=(ROOT/'build/android-installed-sha256-1410.log').read_text(encoding='utf-8').lower()
    assert hashlib.sha256(source.read_bytes()).hexdigest() in installed_log, 'Verify the exact installed APK'
    with zipfile.ZipFile(source) as apk:
        assert apk.testzip() is None
        for abi in ('arm64-v8a','x86_64'):
            assert f'lib/{abi}/libpython3.13.so' in apk.namelist()
        with zipfile.ZipFile(io.BytesIO(apk.read('assets/game-assets.zip'))) as resources:
            for theme in 'abcdef': assert f'web/themes/{theme}.css' in resources.namelist()
            manifests=[n for n in resources.namelist() if n.startswith('dlc/') and n.endswith('/manifest.json')]
            assert len(manifests)==6
            dlcs={n.split('/')[1]:json.loads(resources.read(n))['version'] for n in manifests}
            assert not any(n.startswith('data/') for n in resources.namelist())
    target=ROOT/f'dist/浮生问道-v{VERSION}-Android12.apk'
    shutil.copy2(source,target)
    manifest={
        'base_version':VERSION,'android_version':'1.41.0-android.4','version_code':4,
        'application_id':'com.fusheng.wendao','min_sdk':31,'target_sdk':31,
        'included_abis':['arm64-v8a','x86_64'],'tested_android':'Android 12 / API 31',
        'tested_abi':'x86_64','tested_webview':'91.0.4472.114','physical_device_tested':False,
        'apk':target.name,'apk_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
        'apk_bytes':target.stat().st_size,'dlc_versions':dlcs,'themes':list('abcdef'),
        'save_schema':5,'save_import_export':False,'offline':True,'release_debuggable':False,
        'validation':[
            f'{passed.group(1)} Python regressions passed',
            '80 final targeted regressions passed, including war-encounter cooldown after save/reload',
            'Twelve world-transition RNG scenarios match v1.40.0',
            'Android asset parity, private root and loopback authentication passed',
            'Chromium: faction map and technique upgrade API, six themes at four widths passed',
            'Signed Android 12 release: faction map, war notices and technique growth in all six themes passed',
            'Signed release APK: six themes, real advance and native back passed',
            'v1.40.0 to v1.41.0 same-signature upgrade: offline saved character, progress and theme retained',
            'APK signature verified; release Android Lint: no issues found',
        ],
    }
    report=ROOT/'dist/release-1.41.0-android.4.json'
    report.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    archive=ROOT/f'dist/浮生问道-v{VERSION}-Android12.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as package:
        for path,name in [(target,target.name),(report,report.name),(ROOT/'android/README.md','安卓说明.md'),
                          (ROOT/'CHANGELOG.md','CHANGELOG.md'),(ROOT/'android/app/src/main/mobile/NOTICE.txt','NOTICE.txt')]:
            package.write(path,name)
    with zipfile.ZipFile(archive) as package: assert package.testzip() is None
    # Share the exact release screenshots, after waiting for WebView's visual-state fence.
    gallery=ROOT/'design/android-1.41.0';gallery.mkdir(parents=True,exist_ok=True)
    names=['松烟书院','月下观星','青玉留白','丹砂金阙','江山行卷','竹简纪年']
    cards=[]
    for theme,name in zip('abcdef',names):
        filename=f'world-1410-map-{theme}.png'
        shutil.copy2(ROOT/'build/android-1410-final/verification'/filename,gallery/filename)
        cards.append(f'<figure><figcaption>{theme.upper()} · {name}</figcaption><a href="{filename}"><img src="{filename}" alt="{name}安卓截图" loading="lazy"></a></figure>')
    (gallery/'index.html').write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>浮生问道 · Android 12 山河与界壁更新</title><style>body{margin:0;padding:36px;background:#eeeae0;color:#283c32;font:16px/1.7 system-ui}h1{font:32px Georgia,serif}p{color:#697065}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:24px}figure{margin:0;padding:16px;background:#f9f6ed;border:1px solid #d5d9ca;border-radius:16px}figcaption{margin-bottom:12px}img{width:100%;height:auto;display:block;border-radius:12px}a{color:inherit}</style><h1>浮生问道 · Android 12 山河与界壁更新</h1><p>本体 v1.41.0 · 正式签名 APK · 六主题独立布局<br>截图来自 Android 12 / WebView 91 模拟器；点击查看原图。</p><div class="grid">'''+''.join(cards)+'</div></html>',encoding='utf-8')
    print(json.dumps({'apk':str(target),'bytes':manifest['apk_bytes'],'sha256':manifest['apk_sha256'],
                      'archive':str(archive),'preview':str(gallery/'index.html')},ensure_ascii=False))


if __name__=='__main__': main()
