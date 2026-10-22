param([string]$Serial='emulator-5580')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'android_environment.ps1')
$root=Split-Path $PSScriptRoot -Parent
$version=(Get-Content (Join-Path $root 'cultivation_life/version.py') | Select-String 'BASE_GAME_VERSION = "([^"]+)"').Matches[0].Groups[1].Value
$tag=$version.Replace('.','')
foreach($orientation in @('portrait','landscape')) {
    $path=Join-Path $root "build/android-combat-alpha-$orientation-$tag.log"
    & $androidAdb -s $Serial shell am instrument -w -r -e phase combat-alpha -e orientation $orientation com.fusheng.wendao.test/com.fusheng.wendao.ReleaseSmokeInstrumentation *> $path
    $result=Get-Content -LiteralPath $path -Raw
    if($result -notmatch 'status=passed' -or $result -match 'status=failed'){throw "combat-alpha $orientation failed; see $path"}
    Write-Output "combat-alpha $orientation passed"
}
