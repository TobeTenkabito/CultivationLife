param([string]$Serial='emulator-5580',[switch]$Visits)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'android_environment.ps1')
$root=Split-Path $PSScriptRoot -Parent
$version=(Get-Content (Join-Path $root 'cultivation_life/version.py') | Select-String 'BASE_GAME_VERSION = "([^"]+)"').Matches[0].Groups[1].Value
$tag=$version.Replace('.','')
$buildingPhase=if($Visits){'building-visits'}else{'buildings'}
foreach($phase in @($buildingPhase,'economy-enterprises')) {
    foreach($orientation in @('portrait','landscape')) {
        $path=Join-Path $root "build/android-$phase-$orientation-$tag.log"
        & $androidAdb -s $Serial shell am instrument -w -r -e phase $phase -e orientation $orientation com.fusheng.wendao.test/com.fusheng.wendao.ReleaseSmokeInstrumentation *> $path
        $result=Get-Content -LiteralPath $path -Raw
        if($result -notmatch 'status=passed' -or $result -match 'status=failed'){throw "$phase $orientation native acceptance failed; see $path"}
        Write-Output "$phase $orientation passed"
    }
}
