param([string]$Serial='emulator-5580')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'android_environment.ps1')
$techniqueRoot=Split-Path $PSScriptRoot -Parent
$techniqueVersion=(Get-Content (Join-Path $techniqueRoot 'cultivation_life/version.py') | Select-String 'BASE_GAME_VERSION = "([^"]+)"').Matches[0].Groups[1].Value
$techniqueTag=$techniqueVersion.Replace('.','')
foreach($orientation in @('portrait','landscape')) {
    $path=Join-Path $techniqueRoot "build/android-techniques-$orientation-$techniqueTag.log"
    & $androidAdb -s $Serial shell am instrument -w -r -e phase techniques -e orientation $orientation com.fusheng.wendao.test/com.fusheng.wendao.ReleaseSmokeInstrumentation *> $path
    $result=Get-Content -LiteralPath $path -Raw
    if($result -notmatch 'status=passed' -or $result -match 'status=failed' -or $result -notmatch 'techniques_scope'){throw "Technique $orientation native verification failed; see $path"}
    Write-Output "Technique $orientation passed"
}
