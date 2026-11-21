param([string]$Serial='emulator-5580')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'android_environment.ps1')
$root=Split-Path $PSScriptRoot -Parent
Push-Location -LiteralPath $root
try {
    $tag=(python -c "from cultivation_life.version import BASE_GAME_VERSION;print(BASE_GAME_VERSION.replace('.',''))").Trim()
    $sdk=(& $androidAdb -s $Serial shell getprop ro.build.version.sdk).Trim()
    if($sdk -ne '31'){throw "Expected Android 12 API 31 on $Serial"}
    $apk='android/app/build/outputs/apk/release/app-release.apk'
    $testApk='android/app/build/outputs/apk/androidTest/release/app-release-androidTest.apk'
    foreach($file in @($apk,$testApk)){
        & $androidAdb -s $Serial install -r -t $file
        if($LASTEXITCODE){throw "Installation failed for $file"}
    }
    $aapt=(Get-ChildItem (Join-Path $env:ANDROID_HOME 'build-tools/*/aapt.exe') | Sort-Object FullName | Select-Object -Last 1).FullName
    & $aapt dump badging $apk | Out-File -Encoding utf8 "build/android-metadata-$tag.log"
    if($LASTEXITCODE){throw 'Unable to read APK metadata'}
    foreach($orientation in @('portrait','landscape')){
        $log="build/android-dungeon-art-$orientation-$tag.log"
        & $androidAdb -s $Serial shell am instrument -w -r -e phase dungeon-art -e orientation $orientation com.fusheng.wendao.test/com.fusheng.wendao.ReleaseSmokeInstrumentation *> $log
        $result=Get-Content -LiteralPath $log -Raw
        if($LASTEXITCODE -or $result -notmatch 'status=passed' -or $result -notmatch 'dungeon_art_scope' -or $result -match 'status=failed'){throw "Native $orientation failed, see $log"}
    }
    python -X utf8 scripts/verify_android_scoped.py $Serial --dungeon-art
    if($LASTEXITCODE){throw 'Device/package checks failed'}
} finally { Pop-Location }
