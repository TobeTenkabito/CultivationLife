"""Bind scoped native logs to a signed APK actually installed on the test device."""
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.release_evidence import file_digest, require
from cultivation_life.version import BASE_GAME_VERSION


def main():
    serial=sys.argv[1] if len(sys.argv)>1 else 'emulator-5580'
    economy = '--economy' in sys.argv[2:]
    bugfix = '--bugfix' in sys.argv[2:]
    naming = '--naming' in sys.argv[2:]
    natal = '--natal' in sys.argv[2:]
    teachings = '--teachings' in sys.argv[2:]
    common = '--common-techniques' in sys.argv[2:]
    secret = '--secret-arts' in sys.argv[2:]
    goods = '--common-goods' in sys.argv[2:]
    regional = '--regional' in sys.argv[2:]
    tag=BASE_GAME_VERSION.replace('.','')
    phases=('economy-trust','economy-enterprises','economy-network') if economy else ()
    logs=([f'build/android-{phase}-{orientation}-{tag}.log' for phase in phases for orientation in ('portrait','landscape')]
          if economy else [f'build/android-soul-{orientation}-{tag}.log' for orientation in ('portrait','landscape')]+[f'build/android-upper-{tag}.log'])
    if bugfix:
        logs=[f'build/android-{phase}-{orientation}-{tag}.log' for phase in ('audit-fixes','economy-trust') for orientation in ('portrait','landscape')]
    if naming:
        logs=[f'build/android-{phase}-{orientation}-{tag}.log' for phase in ('content-naming','strategic-war') for orientation in ('portrait','landscape')]
    if natal:
        logs=[f'build/android-{phase}-{orientation}-{tag}.log' for phase in ('content-naming','natal-materials') for orientation in ('portrait','landscape')]
    if teachings:
        logs=[f'build/android-upper-teachings-{orientation}-{tag}.log' for orientation in ('portrait','landscape')]
    if common:
        logs=[f'build/android-common-techniques-{orientation}-{tag}.log' for orientation in ('portrait','landscape')]
    if secret:
        logs=[f'build/android-{phase}-{orientation}-{tag}.log' for phase in ('secret-arts','common-techniques') for orientation in ('portrait','landscape')]
    if goods:
        logs=[f'build/android-common-goods-{orientation}-{tag}.log' for orientation in ('portrait','landscape')]
    if regional:
        logs=[f'build/android-{phase}-{orientation}-{tag}.log' for phase in ('regional-calendar','economy-network') for orientation in ('portrait','landscape')]
    for name in logs:
        text=(ROOT/name).read_text(encoding='utf-8-sig')
        require('status=passed' in text and 'status=failed' not in text,f'Native test failed: {name}')
        if goods:require('common_goods_scope' in text,f'Missing common goods native coverage: {name}')
        if regional and 'regional-calendar' in name:require('regional_calendar_scope' in text,f'Missing regional native coverage: {name}')
        if secret:
            require(('secret_arts_scope' if 'secret-arts' in name else 'common_techniques_scope') in text,f'Missing secret-art native coverage: {name}')
        if common:require('common_techniques_scope' in text,f'Missing common technique native coverage: {name}')
        if bugfix and 'audit-fixes' in name:
            require('followup_fixes_scope' in text,f'Missing current followup native coverage: {name}')
        if naming:
            marker='content_naming_scope' if 'content-naming' in name else 'strategic_war_scope'
            require(marker in text,f'Missing current naming/war native coverage: {name}')
        if natal:
            marker='content_naming_scope' if 'content-naming' in name else 'natal_materials_scope'
            require(marker in text,f'Missing current naming/material native coverage: {name}')
        if teachings:
            require('upper_teachings_scope' in text,f'Missing upper DLC native coverage: {name}')
    sdk=Path('F:/CultivationLife-Android-Tools/sdk')
    signer=sorted(sdk.glob('build-tools/*/apksigner.bat'))[-1]
    apk=ROOT/'android/app/build/outputs/apk/release/app-release.apk'
    signed=subprocess.run([str(signer),'verify','--verbose',str(apk)],capture_output=True,text=True)
    (ROOT/f'build/android-signature-{tag}.log').write_text(signed.stdout+signed.stderr,encoding='utf-8')
    require(signed.returncode==0,'APK signature verification failed')
    adb=sdk/'platform-tools/adb.exe'
    def command(*args):return subprocess.check_output([str(adb),'-s',serial,*args],text=True,encoding='utf-8').strip()
    remote=command('shell','pm','path','com.fusheng.wendao').removeprefix('package:')
    installed=command('shell','sha256sum',remote).split()[0]
    digest=file_digest(apk)
    require(installed==digest,'Installed APK differs from the artifact being packaged')
    test_apk=ROOT/'android/app/build/outputs/apk/androidTest/release/app-release-androidTest.apk'
    test_remote=command('shell','pm','path','com.fusheng.wendao.test').removeprefix('package:')
    require(command('shell','sha256sum',test_remote).split()[0]==file_digest(test_apk),'Installed native test APK differs from current test build')
    receipt=dict(version=BASE_GAME_VERSION,apk_sha256=digest,status='passed',signed=True,
                 device=serial,android=command('shell','getprop','ro.build.version.release'),
                  sdk=command('shell','getprop','ro.build.version.sdk'),logs=logs,test_apk_sha256=file_digest(test_apk),
                  log_hashes={name:file_digest(ROOT/name) for name in logs},
                  scope='Annual finance, original organizational guards, trust and real production; six native orientation phases' if economy else 'Legacy soul and upper scope')
    if bugfix:receipt['scope']='Original descent/return, lifespan, remaining work, economic trust, native imprisonment, production/supply, fixed-site guard and seven inheritance branches; four orientation phases'
    if naming:receipt['scope']='Content naming and legacy identity preservation, actual native upgrade and item use, idle coalition dispatch/hold/recall; four themes and four orientation phases'
    if natal:receipt['scope']='Naming compatibility and eleven-world natal materials, native socket/return, bounded catalog and qualification; four themes and four orientation phases'
    if teachings:receipt['scope']='Four upper worlds, Buddhist wish/blessings and Confucian doctrine/classics/outer opportunity, direct advancement disabled; native clicks, four themes and portrait/landscape'
    if common:receipt['scope']='Common elemental arts, all-root eligibility, real supplement/equip/upgrade, stale shop rejection/recovery and ordinary purchase; four themes and portrait/landscape'
    if secret:receipt['scope']='Independent secret arts, actual low-rank learning and grafting, original source ownership, stale-event recovery, six-entry paging and legacy elemental-art behavior; four themes and portrait/landscape'
    if goods:receipt['scope']='Fixed core healing, original common ore forging, finite talisman conversion/toggle, paid tiered auction and stale insufficient recovery; four themes and portrait/landscape'
    if regional:receipt['scope']='Guixu interruption, persistent travel credit, real resumed arrival and fleet network native clicks; four themes and portrait/landscape'
    (ROOT/f'build/android-{tag}-scoped.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Signed Android native scope passed; installed APK matches artifact SHA-256')


if __name__=='__main__':main()
