param([ValidateSet('Debug','Release')][string]$Configuration = 'Release')
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'android_environment.ps1')
$projectRoot = Split-Path $PSScriptRoot -Parent
if ($Configuration -eq 'Release') {
    if (-not $env:CULTIVATION_KEYSTORE) { $env:CULTIVATION_KEYSTORE = Join-Path $androidTools 'signing\wendao-release.jks' }
    if (-not $env:CULTIVATION_KEYSTORE_PASSWORD) {
        $env:CULTIVATION_KEYSTORE_PASSWORD = [System.IO.File]::ReadAllText((Join-Path $androidTools 'signing\release-password.txt'))
    }
}
try {
    & $androidGradle -p (Join-Path $projectRoot 'android') --no-daemon "assemble$Configuration" "lint$Configuration"
    if ($LASTEXITCODE -ne 0) { throw "Android $Configuration build failed ($LASTEXITCODE)" }
} finally {
    Remove-Item Env:CULTIVATION_KEYSTORE_PASSWORD -ErrorAction SilentlyContinue
}
