"""Publish the exact signed APK after release and Android 12 checks."""
import hashlib
import io
import json
import re
import runpy
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.android_css import compile_css
from scripts.release_evidence import require
from scripts.android_provenance import validate_apk_inputs
from cultivation_life.save_schema import SAVE_SCHEMA_VERSION
VERSION = runpy.run_path(str(ROOT / 'cultivation_life/version.py'))['BASE_GAME_VERSION']
RELEASE_ID = VERSION.replace('.', '')
VERSION_CODE = int(re.search(r'versionCode (\d+)', (ROOT/'android/app/build.gradle').read_text(encoding='utf-8'))[1])
ANDROID_VERSION = f'{VERSION}-android.{VERSION_CODE}'

def main():
    def log(name):
        return (ROOT/'build'/name).read_text(encoding='utf-8', errors='replace')
    tests = log(f'release-{RELEASE_ID}-tests.log')
    passed = re.search(r'(\d+) passed in', tests)
    require(bool(passed) and 'failed' not in tests.lower() and 'ERROR' not in tests, 'Full regression suite must pass')
    require('1980 dossier checks' in log(f'heavens-ui-{RELEASE_ID}.log') and 'Traceback' not in log(f'heavens-ui-{RELEASE_ID}.log'), 'Eleven-world UI acceptance must pass')
    knowledge = log(f'heavens-knowledge-ui-{RELEASE_ID}.log')
    require('Knowledge UI passed:' in knowledge and 'Traceback' not in knowledge, 'Knowledge and settings UI must pass')
    workbench = log(f'heavens-workbench-ui-{RELEASE_ID}.log')
    require('real isolated execution and snapshot restore passed' in workbench and 'Traceback' not in workbench, 'Heavens workbench UI must pass')
    for name in (f'android-experience-{RELEASE_ID}.log', f'android-institutions-{RELEASE_ID}.log', f'android-governance-{RELEASE_ID}.log', f'android-economy-{RELEASE_ID}.log', f'android-upper-{RELEASE_ID}.log', f'android-trials-{RELEASE_ID}.log', f'android-save-transfer-{RELEASE_ID}.log', f'android-initial-{RELEASE_ID}.log', f'android-immortal-{RELEASE_ID}.log', f'android-minor-{RELEASE_ID}.log', f'android-tutorial-{RELEASE_ID}.log'):
        require('status=passed' in log(name) and 'status=failed' not in log(name), name)
    require('status=passed' in log(f'android-bulk-{RELEASE_ID}.log') and 'status=failed' not in log(f'android-bulk-{RELEASE_ID}.log'), 'Android bulk checks must pass')
    require('status=passed' in log(f'android-upper-voisinage-{RELEASE_ID}.log') and 'status=failed' not in log(f'android-upper-voisinage-{RELEASE_ID}.log'), 'Android upper voisinage checks must pass')
    require('roundtrip passed' in log(f'save-crossplatform-{RELEASE_ID}.log'), 'Cross-platform save roundtrip must pass')
    require('status=passed' in log(f'android-fusion-{RELEASE_ID}.log') and 'status=failed' not in log(f'android-fusion-{RELEASE_ID}.log'), 'Android fusion checks must pass')
    for phase in ('civilizations-i-only','civilizations-ii-only','civilizations-neither'):
        result=log(f'android-{phase}-{RELEASE_ID}.log')
        require('status=passed' in result and 'status=failed' not in result, f'Android independent DLC check must pass: {phase}')
    for orientation in ('portrait', 'landscape'):
        for phase in ('civilizations', 'organizations', 'custom-start', 'war-logistics', 'economy-governance', 'economy-enterprises', 'economy-expansion'):
            result = log(f'android-{phase}-{orientation}-{RELEASE_ID}.log')
            require('status=passed' in result and 'status=failed' not in result, f'Android {phase} {orientation} must pass')
        result = log(f'android-heavens-{orientation}-{RELEASE_ID}.log')
        require('status=passed' in result and 'status=failed' not in result, f'Heavens {orientation} must pass')
        result = log(f'android-spatial-talisman-{orientation}-{RELEASE_ID}.log')
        require('status=passed' in result and 'status=failed' not in result, f'Android spatial talisman {orientation} checks must pass')
        result = log(f'android-start-layout-{orientation}-{RELEASE_ID}.log')
        require('status=passed' in result and 'status=failed' not in result, f'Android start layout {orientation} checks must pass')
        result = log(f'android-asura-{orientation}-{RELEASE_ID}.log')
        require('status=passed' in result and 'status=failed' not in result, f'Android Asura {orientation} checks must pass')
        result = log(f'android-debug-console-{orientation}-{RELEASE_ID}.log')
        require('status=passed' in result and 'status=failed' not in result, f'Android Debug console {orientation} checks must pass')
    require('passed' in log(f'civilizations-ui-{RELEASE_ID}.log') and 'Traceback' not in log(f'civilizations-ui-{RELEASE_ID}.log'), 'Civilizations browser checks must pass')
    require('Verifies' in log(f'android-signature-{RELEASE_ID}.log'), 'Android APK signature must verify')
    metadata = log(f'android-metadata-{RELEASE_ID}.log')
    require(f"versionCode='{VERSION_CODE}'" in metadata and f"versionName='{ANDROID_VERSION}'" in metadata, 'Android version metadata must match the release')
    require("sdkVersion:'31'" in metadata and 'application-debuggable' not in metadata, 'Android APK must target the expected minimum SDK and be non-debuggable')
    require((ROOT/'android/app/build/reports/lint-results-release.txt').read_text(encoding='utf-8').strip() == 'No issues found.', 'Android release lint must pass')
    require('Quick-start regression passed' in log(f'quick-start-ui-{RELEASE_ID}.log'), 'Quick-start UI checks must pass')
    require('Start layout passed' in log(f'start-layout-ui-{RELEASE_ID}.log'), 'Start layout UI checks must pass')
    require('Release 250 UI passed:' in log(f'world-life-ui-{RELEASE_ID}.log'), 'World life UI checks must pass')
    require('Release 251 UI passed:' in log(f'true-form-ui-{RELEASE_ID}.log'), 'True form UI checks must pass')
    source = ROOT/'android/app/build/outputs/apk/release/app-release.apk'
    apk_bytes = source.read_bytes()
    digest = hashlib.sha256(apk_bytes).hexdigest()
    require(digest in log(f'android-installed-sha256-{RELEASE_ID}.log').lower(), 'APK hash must match the installed and tested APK')
    with zipfile.ZipFile(io.BytesIO(apk_bytes)) as apk:
        require(apk.testzip() is None, 'APK ZIP integrity check failed')
        for abi in ('arm64-v8a', 'x86_64'):
            require(f'lib/{abi}/libpython3.13.so' in apk.namelist(), f'Missing Python library for {abi}')
        with zipfile.ZipFile(io.BytesIO(apk.read('assets/game-assets.zip'))) as assets:
            require(assets.read('web/app.js') == (ROOT/'web/app.js').read_bytes(), 'Packaged web/app.js differs from source')
            require(assets.read('web/npc-contacts.js') == (ROOT/'web/npc-contacts.js').read_bytes(), 'Packaged web/npc-contacts.js differs from source')
            require(assets.read('web/map-directory.js') == (ROOT/'web/map-directory.js').read_bytes(), 'Packaged web/map-directory.js differs from source')
            require(assets.read('web/npc-contacts.css') == compile_css((ROOT/'web/npc-contacts.css').read_text(encoding='utf-8')).encode('utf-8'), 'Packaged NPC stylesheet differs from compiled source')
            for name in ('web/heavens-atlas.js', 'web/debug-heavens.js', 'web/heavens-incidents.js', 'web/heavens-panel.js', 'web/heavens-panel.css', 'web/heavens-frontier.js', 'web/heavens-campaign.js', 'web/upper-institution-panel.js', 'web/upper-voisinage-panel.js', 'web/immortal-economy-panel.js', 'web/ui-panels.js', 'web/asura-panel.js', 'web/asura-meridians.js', 'web/meridian-atlas.js', 'web/meridian-atlas.css', 'web/assets/asura-anatomy.png', 'web/assets/immortal-anatomy.png', 'web/asura-panel.css', 'web/puppet-workshop.js', 'web/handbook-content.js', 'web/doctrine-panel.css', 'web/tutorial.js', 'web/tutorial-steps.js', 'web/tutorial-content.js', 'web/tutorial.css', 'web/index.html', 'web/combat-plan-panel.js', 'web/doctrine-panel.js', 'web/immortal-aperture-panel.js', 'web/theme-manager.js', 'web/theme-composition.js', 'content/crafting.json', 'content/formations.json', 'content/techniques.json', 'content/market.json', 'content/factions.json', 'content/doctrines.json', 'content/maps.json', 'content/items.json', 'content/world.json'):
                expected = (ROOT/name).read_bytes()
                if name.endswith('.css'):
                    expected = compile_css(expected.decode('utf-8')).encode('utf-8')
                if name == 'web/index.html':
                    expected = expected.decode('utf-8').replace('</head>', '<link rel="stylesheet" href="/android/mobile.css"></head>').replace('</body>', '<script src="/android/mobile.js"></script></body>').encode('utf-8')
                require(assets.read(name) == expected, name)
            require(assets.read('web/save-transfer.js') == (ROOT/'web/save-transfer.js').read_bytes(), 'Packaged save-transfer script differs from source')
            for theme in 'abdf':
                require(f'web/themes/{theme}.css' in assets.namelist(), f'Missing theme {theme}')
            manifests = [n for n in assets.namelist() if n.startswith('dlc/') and n.endswith('/manifest.json')]
            require(len(manifests) == len(list((ROOT/'dlc').glob('*/manifest.json'))), 'Packaged DLC manifest count differs from source')
            dlcs = {n.split('/')[1]: json.loads(assets.read(n))['version'] for n in manifests}
            require(not any(n.startswith('data/') for n in assets.namelist()), 'Player data must not be included in the APK')
        provenance = validate_apk_inputs(ROOT, apk)
    target = ROOT/f'dist/浮生问道-v{VERSION}-Android12.apk'
    target.write_bytes(apk_bytes)
    report = ROOT/f'dist/release-{ANDROID_VERSION}.json'
    manifest = {
        'base_version': VERSION, 'android_version': ANDROID_VERSION, 'version_code': VERSION_CODE,
        'application_id': 'com.fusheng.wendao', 'min_sdk': 31, 'target_sdk': 31,
        'included_abis': ['arm64-v8a', 'x86_64'], 'tested_android': 'Android 12 / API 31',
        'tested_abi': 'x86_64', 'physical_device_tested': False,
        'apk': target.name, 'apk_sha256': digest, 'apk_bytes': target.stat().st_size,
        'inputs_sha256': hashlib.sha256(json.dumps(provenance['inputs'], sort_keys=True).encode()).hexdigest(),
        'dlc_versions': dlcs, 'heavens_worlds': 11, 'heavens_incident_branches': 66, 'heavens_anomalies': 13, 'heavens_conflict_cases': 12,
        'themes': list('abdf'), 'save_schema': SAVE_SCHEMA_VERSION,
        'save_import_export': True, 'offline': True, 'release_debuggable': False,
        'validation': [
            'Four-theme native military logistics, delayed depot approval/collection and paid immortal/Asura conversion verified in both orientations',
            'Observer-relative intelligence, merchant snapshots, same-tier system wars and four named themes verified',
            'Organization inheritance, contribution-backed requisitions, outsider clan succession, owner-funded local teleport arrays and temporary activity navigation verified',
            'Eleven-world dossiers: four themes, 1980 browser checks including short landscape, real touch and persisted outcomes',
            f'{passed.group(1)} Python regressions passed',
            'Signed Android 12 release: four-theme start layout, folding, tutorial, Buddhist DLC label and native quick start in portrait and landscape',
            'Four-theme native gameplay: court, institutions, upper worlds, economy, bulk controls, fusion, trials and meridians',
            'Talisman portrait and landscape: native tiered crafting, materials, sales, experience, category entry and multiple realm-gated map rifts',
            'Asura portrait and landscape: realm gate, native vein opening, power acquisition, controls and persistence',
            'Live tutorial actions, native back and persisted progress',
            'Save transfer: four themes, native clipboard, large and segmented saves, confirmation and lossless Windows to Android to Windows roundtrip',
            'Debug console portrait and landscape: isolated writes, snapshots, DLC commands, native document callbacks and configuration-independent opening',
            'Signature, version metadata, installed APK hash, source provenance, archive integrity and release lint verified',
        ],
    }
    report.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    archive = ROOT/f'dist/浮生问道-v{VERSION}-Android12.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as package:
        for path, name in [(target,target.name), (report,report.name), (ROOT/'android/README.md','安卓说明.md'),
                           (ROOT/'docs/three-corpses-1512.md','三尸复测与合练.md'),
                           (ROOT/'docs/immortal-vein-balance.md','仙脉费用校准.md'),
                           (ROOT/'docs/upper-voisinages-1522.md','三界邻域说明.md'), (ROOT/'docs/experience-1520.md','修行与天庭体验更新.md'), (ROOT/'docs/institutions-1513.md','机构势力说明.md'), (ROOT/'CHANGELOG.md','CHANGELOG.md'), (ROOT/'android/app/src/main/mobile/NOTICE.txt','NOTICE.txt')]:
            package.write(path, name)
        for name in ('debug-development.md', 'debug-base-coverage.md', 'debug-dlc-coverage.md',
                     'war-logistics.md', 'organizations-290.md', 'monster-civilizations-development.md',
                     'spatial-talismans.md', 'asura-court-1530.md', 'heavens-implementation.md',
                     'world-transition-development.md', 'world-transition-audit.md', 'world-transition-state-contract.json'):
            package.write(ROOT/'docs'/name, 'docs/'+name)
    with zipfile.ZipFile(archive) as package:
        require(package.testzip() is None, 'Release ZIP integrity check failed')
    print(json.dumps({'apk':str(target), 'bytes':target.stat().st_size, 'sha256':digest,
                      'archive':str(archive)}, ensure_ascii=False))

if __name__ == '__main__':
    main()
