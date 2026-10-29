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
    architecture = '--architecture' in sys.argv[2:]
    buildings = '--buildings' in sys.argv[2:]
    visits = '--building-visits' in sys.argv[2:]
    visual = '--visual' in sys.argv[2:]
    combat = '--combat-alpha' in sys.argv[2:]
    update301 = '--update301' in sys.argv[2:]
    soul = '--soul-lifecycle' in sys.argv[2:]
    heavens = '--heavens' in sys.argv[2:]
    authored = '--authored' in sys.argv[2:]
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
    if architecture:
        phases=('upper','upper-teachings','natal-materials','asura','regional-calendar','organizations','audit-fixes')
        logs=[f'build/android-{phase}-{orientation}-{tag}.log' for phase in phases for orientation in ('portrait','landscape')]
    if buildings:
        logs=[f'build/android-{phase}-{orientation}-{tag}.log' for phase in ('buildings','economy-enterprises') for orientation in ('portrait','landscape')]
    if visits:
        logs=[f'build/android-{phase}-{orientation}-{tag}.log' for phase in ('building-visits','economy-enterprises') for orientation in ('portrait','landscape')]
    if visual:
        logs=[f'build/android-visual-ui-{orientation}-{tag}.log' for orientation in ('portrait','landscape')]
    if combat:
        logs=[f'build/android-combat-alpha-{orientation}-{tag}.log' for orientation in ('portrait','landscape')]
    if authored:
        logs=[f'build/android-authored-{orientation}-{tag}.log' for orientation in ('portrait','landscape')]
    if update301:
        logs=[f'build/android-update301-{orientation}-{tag}.log' for orientation in ('portrait','landscape')]
    if soul:logs=[f'build/android-soul-lifecycle-{orientation}-{tag}.log' for orientation in ('portrait','landscape')]
    if heavens:logs=[f'build/android-heavens-{orientation}-{tag}.log' for orientation in ('portrait','landscape')]
    for name in logs:
        text=(ROOT/name).read_text(encoding='utf-8-sig')
        if heavens:
            require((ROOT/name).stat().st_mtime >= (ROOT/'android/app/build/outputs/apk/release/app-release.apk').stat().st_mtime,'Heavens native log predates the final APK')
        require('status=passed' in text and 'status=failed' not in text,f'Native test failed: {name}')
        if heavens:require('heavens_outposts_scope' in text,f'Missing native heavens/war/return acceptance: {name}')
        if soul:require('soul_lifecycle_scope' in text,f'Missing soul native acceptance: {name}')
        if soul:require('frontier_skin_scope' in text,f'Missing frontier/swimwear native acceptance: {name}')
        if soul:require('tide_theme_scope' in text,f'Missing tide/theme native acceptance: {name}')
        if authored:require('authored_scope' in text,f'Missing authoring native acceptance: {name}')
        if update301:require('update301_scope' in text,f'Missing 3.0.1 native skin and ecology acceptance: {name}')
        if visual and BASE_GAME_VERSION=='3.0.0-alpha.4':require('monster_visual_scope' in text,f'Missing alpha.4 native monster scope: {name}')
        if visual and BASE_GAME_VERSION=='3.0.0-alpha.5':require('path_character_scope' in text,f'Missing alpha.5 native path scope: {name}')
        if visual and BASE_GAME_VERSION=='3.0.0-alpha.6':require('home_scenes_scope' in text,f'Missing alpha.6 native home scope: {name}')
        if visual and BASE_GAME_VERSION=='3.0.0':
            require(all(marker in text for marker in ('monster_visual_scope','path_character_scope','home_scenes_scope','domain_ink_scope')),f'Missing stable visual coverage: {name}')
        if visual:require(all(marker in text for marker in ('visual_ui_scope','visual_additions_scope','domain_replay_scope','protagonist_static_scope')),f'Missing native UI/social/domain/protagonist coverage: {name}')
        if combat:require('combat_alpha_scope' in text,f'Missing native combat and DLC acceptance: {name}')
        if buildings and '/android-buildings-' in name:require('buildings_scope' in text,f'Missing current native city coverage: {name}')
        if visits and '/android-building-visits-' in name:require('building_visits_scope' in text,f'Missing native illustrated visits: {name}')
        if visits and '/android-building-visits-' in name:require('city_management_scope' in text,f'Missing native city management and authored landscape: {name}')
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
        if architecture:
            markers={'upper':'upper_scope','upper-teachings':'upper_teachings_scope',
                'natal-materials':'natal_materials_scope','asura':'asura_scope',
                'regional-calendar':'regional_calendar_scope','organizations':'organizations_scope',
                'audit-fixes':'audit_fixes_scope'}
            # upper and upper-teachings share a prefix; prefer the longest phase.
            phase=max((p for p in phases if name.startswith(f'build/android-{p}-')),key=len)
            require(markers[phase] in text,f'Missing character architecture native coverage: {name}')
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
    if architecture:receipt['scope']='Seven character/region/organization phases, four themes, portrait/landscape; actual signed release APK and current native test APK'
    if buildings:receipt['scope']='Eleven-world initial cities, four-theme native construction, stale material recovery, bounded story rewards, yearly governance, ruins and rebuild, earned followup plus original production; portrait/landscape'
    if visits:receipt['scope']='Four-theme text gazetteer and expanded illustrations, real scenery/industry/temple visits, bounded insight, earned followup and original estate production; portrait/landscape'
    if visual:receipt['scope']='Optional pixel UI, original inventory commands, true natal sockets, eleven world maps, social portraits, domain editor and real domain battle replay; four themes, native portrait/landscape'
    if combat:receipt['scope']='User-requested focused combat CG, single/group defeat, Guixu factual use, true/replica intelligence, read-only replay and disposal; four themes, native portrait/landscape, not full repository'
    if soul:receipt['scope']='Soul secrets, energy, captive refinement and equipment; holiday and 1890s frontier skins, actual gun FX, Integration swimwear gate, wardrobe nested back, four themes; signed Android 12 portrait/landscape'
    if heavens:receipt['scope']='Second/third-tier original staff, independent military mandates, stale recovery, real crossing, finite local funds and physical war deployment/return; remote personal combat disabled and prepaid return; four themes, signed Android 12 portrait/landscape'
    if authored:receipt['scope']='Authored DLC create, paid manual and upgrade, one-generation inheritance, four themes and contact art text containment; native portrait/landscape, focused scope'
    if update301:receipt['scope']='3.0.1 focused four-theme skin selection, actual earlier-form figure, unchanged gameplay and ecology observation; portrait/landscape, not full repository'
    (ROOT/f'build/android-{tag}-scoped.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Signed Android native scope passed; installed APK matches artifact SHA-256')


if __name__=='__main__':main()
