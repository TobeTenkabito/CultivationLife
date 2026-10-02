param([string]$Serial='emulator-5580')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'android_environment.ps1')
$projectRoot=Split-Path $PSScriptRoot -Parent
$baseVersion=(Get-Content (Join-Path $projectRoot 'cultivation_life/version.py') | Select-String 'BASE_GAME_VERSION = "([^"]+)"').Matches[0].Groups[1].Value
$releaseId=$baseVersion.Replace('.','')
foreach($orientation in @('portrait','landscape')) {
    $resultPath=Join-Path $projectRoot "build/android-asura-$orientation-$releaseId.log"
    & $androidAdb -s $Serial shell am instrument -w -r -e phase asura -e orientation $orientation com.fusheng.wendao.test/com.fusheng.wendao.ReleaseSmokeInstrumentation *> $resultPath
    $result=Get-Content -LiteralPath $resultPath -Raw
    if($result -notmatch 'status=passed' -or $result -match 'status=failed'){throw "Asura $orientation verification failed"}
    Write-Output "Asura $orientation passed"
}
