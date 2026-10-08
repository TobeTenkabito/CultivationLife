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
    tag=BASE_GAME_VERSION.replace('.','')
    logs=[f'build/android-soul-{orientation}-{tag}.log' for orientation in ('portrait','landscape')]+[f'build/android-upper-{tag}.log']
    for name in logs:
        text=(ROOT/name).read_text(encoding='utf-8-sig')
        require('status=passed' in text and 'status=failed' not in text,f'Native test failed: {name}')
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
    receipt=dict(version=BASE_GAME_VERSION,apk_sha256=digest,status='passed',signed=True,
                 device=serial,android=command('shell','getprop','ro.build.version.release'),
                 sdk=command('shell','getprop','ro.build.version.sdk'),logs=logs,
                 log_hashes={name:file_digest(ROOT/name) for name in logs})
    (ROOT/f'build/android-{tag}-scoped.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Signed Android native scope passed; installed APK matches artifact SHA-256')


if __name__=='__main__':main()
