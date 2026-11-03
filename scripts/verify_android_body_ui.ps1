param([string]$Serial='emulator-5580')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'android_environment.ps1')
$projectRoot=Split-Path $PSScriptRoot -Parent
$bodyVersion=(Get-Content (Join-Path $projectRoot 'cultivation_life/version.py') | Select-String 'BASE_GAME_VERSION = "([^"]+)"').Matches[0].Groups[1].Value
$bodyTag=$bodyVersion.Replace('.','')
foreach($orientation in @('portrait','landscape')) {
    $path=Join-Path $projectRoot "build/android-body-ui-$orientation-$bodyTag.log"
    & $androidAdb -s $Serial shell am instrument -w -r -e phase body-ui -e orientation $orientation com.fusheng.wendao.test/com.fusheng.wendao.ReleaseSmokeInstrumentation *> $path
    $result=Get-Content -LiteralPath $path -Raw
    if($result -notmatch 'status=passed' -or $result -match 'status=failed'){throw "Body/UI $orientation native verification failed; see $path"}
    Write-Output "Body/UI $orientation passed"
}
